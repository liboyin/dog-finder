"""Authoritative listing state for dog-finder, persisted as data/state.json.

The state file — not the Markdown index — is the source of truth for dedup and
history. Each entry is keyed by canonical URL and records the listing fields, the
LLM's qualify verdict, and first/last-seen run timestamps. Code owns this file;
the LLM only emits verdicts that ``apply_verdicts`` merges in.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile

from src.dedup import canonical
from src.parsers.base import Listing

STATE_VERSION = 1

# Cap on any single stored string field, so a hostile/oversized scraped or LLM
# value can't bloat state.json (summaries are <=25 words by contract anyway).
MAX_FIELD_LEN = 200

logger = logging.getLogger("dog_finder.store")

# Verdicts.
PENDING = "pending"
QUALIFIED = "qualified"
REJECTED = "rejected"


def empty_state() -> dict:
    """Return a fresh, empty state document."""
    return {"version": STATE_VERSION, "listings": {}}


def load_state(path: str) -> dict:
    """Load the state document, or an empty one if the file does not exist.

    Args:
        path: Path to state.json.

    Returns:
        The state dict with a "listings" mapping keyed by canonical URL.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return empty_state()


def save_state(path: str, state: dict) -> None:
    """Atomically write the state document to disk as pretty JSON.

    The authoritative record is written to a temp file in the same directory and
    then ``os.replace``-d onto ``path`` (an atomic rename on POSIX), so a crash or
    kill mid-write leaves the previous state.json intact rather than truncated.

    Args:
        path: Destination path for state.json.
        state: The state dict to serialize.
    """
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(state, out, indent=2, ensure_ascii=False, sort_keys=True)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _entry_from_listing(listing: Listing, ts: str, source_kind: str, source: str | None) -> dict:
    """Build a new state entry from a freshly-parsed listing."""
    return {
        "url": listing.url,
        "name": listing.name,
        "breed": listing.breed,
        "age": listing.age,
        "sex": listing.sex,
        "size": listing.size,
        "species": listing.species,
        "location": listing.location,
        "shelter": listing.shelter,
        "source": source,
        "fee": listing.fee,
        "status": listing.status,
        "source_kind": source_kind,
        "first_seen": ts,
        "last_seen": ts,
        "verdict": PENDING,
        "summary": None,
        "tags": [],
        "removed": False,
        "recheck": None,
        "recheck_reason": None,
    }


def upsert_listing(
    state: dict, listing: Listing, ts: str, source_kind: str = "petrescue",
    source: str | None = None,
) -> bool:
    """Insert or update a code-parsed listing in the state.

    Args:
        state: The state document (mutated in place).
        listing: The parsed listing to record.
        ts: This run's timestamp.
        source_kind: The parser's source identifier (e.g. "petrescue").
        source: The config source that found the dog (e.g. an aggregator search
            name). Distinct from ``listing.shelter``, the real organization.

    Returns:
        True if the listing was new (and therefore needs a verdict), else False.
    """
    key = canonical(listing.url)
    existing = state["listings"].get(key)
    if existing is None:
        state["listings"][key] = _entry_from_listing(listing, ts, source_kind, source)
        return True
    existing["last_seen"] = ts
    if listing.status:
        existing["status"] = listing.status
    return False


def touch(state: dict, url: str, ts: str) -> None:
    """Mark an existing listing as seen this run (updates last_seen)."""
    entry = state["listings"].get(canonical(url))
    if entry is not None:
        entry["last_seen"] = ts


def flag_stale_browser(state: dict, cutoff: str) -> list[dict]:
    """Flag qualified browser-sourced dogs unseen since the cutoff for re-check.

    Browser-discovered listings have no static parser, so the detail recheck
    (which is the vanish-detection path for static shelters) skips them —
    nothing else ever questions whether a browser-found qualified dog is still
    available, and its only exit would be the 90-day prune (a silent, unconfirmed
    drop). This flags a qualified, non-removed ``source_kind == "browser"`` entry
    with no current recheck whose ``last_seen`` predates the cutoff as
    ``maybe_adopted`` (reason "stale_browser") so the LLM re-verifies it via the
    browser path. The browser pass bumps ``last_seen`` every run it re-emits the
    dog, so a short cutoff tolerates a couple of failed passes without
    false-flagging a present dog.

    Args:
        state: The state document (mutated in place).
        cutoff: A 'YYYYMMDD-HHMMSS' timestamp; entries last seen before it are flagged.

    Returns:
        The list of entries newly flagged for re-check.
    """
    flagged = []
    for entry in state["listings"].values():
        if (
            entry.get("source_kind") == "browser"
            and entry.get("verdict") == QUALIFIED
            and not entry.get("removed")
            and not entry.get("recheck")
            and entry.get("last_seen")
            and entry["last_seen"] < cutoff
        ):
            entry["recheck"] = "maybe_adopted"
            entry["recheck_reason"] = "stale_browser"
            flagged.append(entry)
    return flagged


def prune_stale(state: dict, cutoff: str) -> list[dict]:
    """Remove listings whose last_seen predates the cutoff, bounding file growth.

    Pruning keys on ``last_seen`` only, so a still-listed dog (its last_seen is
    bumped every run) is never removed — only listings unseen since the cutoff
    age out. A pruned dog that later reappears is simply re-discovered as new.

    Args:
        state: The state document (mutated in place).
        cutoff: A 'YYYYMMDD-HHMMSS' timestamp; entries last seen before it go.

    Returns:
        The list of removed entries.
    """
    stale_keys = [
        key for key, entry in state["listings"].items()
        if entry.get("last_seen") and entry["last_seen"] < cutoff
    ]
    return [state["listings"].pop(key) for key in stale_keys]


def migrate_source_field(state: dict, aggregator_source_names: set[str]) -> None:
    """Backfill the source/shelter split on entries predating it (idempotent).

    Before this split, ``shelter`` stored the config *source* name — misleading
    when that source is an aggregator search rather than a real organization. For
    each entry lacking a ``source`` field, this copies the current ``shelter``
    into ``source`` (it recorded what found the dog), then nulls ``shelter`` when
    it named an aggregator search, so the real shelter can be backfilled from the
    detail page on the next recheck. A real-shelter name stays in both fields
    (harmless and mostly correct). Entries already carrying ``source`` are left
    untouched, so re-running is a no-op.

    Applied once to ``data/state.json`` when the split landed; every entry
    created since carries ``source``, so this is not wired into the daily run. It
    is retained (and kept idempotent) to re-migrate an old ``state.json`` restored
    from history or backup.

    Args:
        state: The state document (mutated in place).
        aggregator_source_names: Config source names that are aggregator searches,
            not shelters; their stored ``shelter`` value is cleared.
    """
    for entry in state["listings"].values():
        if "source" in entry:
            continue
        entry["source"] = entry.get("shelter")
        if entry.get("shelter") in aggregator_source_names:
            entry["shelter"] = None


def pending_listings(state: dict) -> list[dict]:
    """Return entries the LLM must judge: pending verdicts plus re-checks."""
    return [
        entry
        for entry in state["listings"].values()
        if not entry.get("removed")
        and (entry.get("verdict") == PENDING or entry.get("recheck"))
    ]


def qualified_for_render(state: dict) -> list[dict]:
    """Return qualified, non-removed listings sorted newest-first by first_seen."""
    entries = [
        entry
        for entry in state["listings"].values()
        if entry.get("verdict") == QUALIFIED and not entry.get("removed")
    ]
    return sorted(entries, key=lambda e: e.get("first_seen") or "", reverse=True)


def _valid_verdict_url(url) -> bool:
    """True if a verdict URL is a safe http(s) key with no injection characters.

    A verdict for an unknown URL creates a new state entry keyed on it and is
    rendered verbatim on the index's unsanitized URL line, so a malformed or
    hostile URL is rejected: a non-string, a non-http(s) scheme (e.g.
    ``javascript:``), or any whitespace, angle bracket, or Markdown link bracket
    (``[``/``]``) — the last would let ``…[text](evil)…`` render as a disguised
    link. Parentheses stay allowed (legal in real URLs and inert without a
    preceding ``]``).
    """
    if not isinstance(url, str):
        return False
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    return not any(char in url for char in " \t\n\r<>[]")


def _cap(value):
    """Truncate a stored string field to MAX_FIELD_LEN; pass non-strings through."""
    if isinstance(value, str) and len(value) > MAX_FIELD_LEN:
        return value[:MAX_FIELD_LEN]
    return value


def apply_verdicts(state: dict, verdicts: list[dict], ts: str) -> None:
    """Merge LLM verdicts into the state.

    Each verdict is a dict with at least ``url`` and ``verdict``. Browser-found
    dogs (URLs not yet in state) are created from the verdict's fields. A verdict
    may also set ``removed`` (e.g. confirmed adopted) and ``summary``/``tags``.
    A verdict whose ``url`` is not a clean http(s) URL is ignored (logged), and
    every stored string field is capped at ``MAX_FIELD_LEN`` — the LLM output is
    untrusted input that keys and populates the human-facing index.

    Args:
        state: The state document (mutated in place).
        verdicts: The list of verdict dicts emitted by the LLM.
        ts: This run's timestamp.
    """
    for verdict in verdicts:
        url = verdict.get("url")
        if not url:
            continue
        if not _valid_verdict_url(url):
            logger.warning("apply_verdicts: ignoring verdict with invalid url %r", url)
            continue
        key = canonical(url)
        entry = state["listings"].get(key)
        if entry is None:
            entry = {
                "url": url,
                "source_kind": verdict.get("source_kind", "browser"),
                "source": _cap(verdict.get("source")),
                "first_seen": ts,
                "removed": False,
                # Default to pending so a verdict that omits `verdict` on a new URL
                # becomes a visible candidate next run, not an invisible orphan.
                "verdict": PENDING,
            }
            for field in ("name", "breed", "age", "sex", "size", "location", "shelter", "fee", "status"):
                entry[field] = _cap(verdict.get(field))
            state["listings"][key] = entry
        entry["last_seen"] = ts
        if verdict.get("verdict") in (QUALIFIED, REJECTED, PENDING):
            entry["verdict"] = verdict["verdict"]
        if "summary" in verdict:
            entry["summary"] = _cap(verdict["summary"])
        if "tags" in verdict:
            tags = verdict["tags"]
            # Normalize to a capped list; a non-list (e.g. a bare string) would
            # otherwise render char-by-char, so drop it to an empty list.
            entry["tags"] = [_cap(str(tag)) for tag in tags] if isinstance(tags, list) else []
        if verdict.get("removed"):
            entry["removed"] = True
        # A judged listing no longer needs re-checking.
        entry["recheck"] = None
        entry["recheck_reason"] = None
