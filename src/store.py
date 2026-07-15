"""Authoritative listing state for dog-finder, persisted as data/state.json.

The state file — not the Markdown index — is the source of truth for dedup and
history. Each entry is keyed by canonical URL and records the listing fields, the
LLM's qualify verdict, and first/last-seen run timestamps. Code owns this file;
the LLM only emits verdicts that ``apply_verdicts`` merges in.
"""
from __future__ import annotations

import json
import os
import tempfile

from src.dedup import canonical
from src.parsers.base import Listing

STATE_VERSION = 1

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


def _entry_from_listing(listing: Listing, ts: str, source_kind: str) -> dict:
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


def upsert_listing(state: dict, listing: Listing, ts: str, source_kind: str = "petrescue") -> bool:
    """Insert or update a code-parsed listing in the state.

    Args:
        state: The state document (mutated in place).
        listing: The parsed listing to record.
        ts: This run's timestamp.
        source_kind: The parser's source identifier (e.g. "petrescue").

    Returns:
        True if the listing was new (and therefore needs a verdict), else False.
    """
    key = canonical(listing.url)
    existing = state["listings"].get(key)
    if existing is None:
        state["listings"][key] = _entry_from_listing(listing, ts, source_kind)
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


def apply_verdicts(state: dict, verdicts: list[dict], ts: str) -> None:
    """Merge LLM verdicts into the state.

    Each verdict is a dict with at least ``url`` and ``verdict``. Browser-found
    dogs (URLs not yet in state) are created from the verdict's fields. A verdict
    may also set ``removed`` (e.g. confirmed adopted) and ``summary``/``tags``.

    Args:
        state: The state document (mutated in place).
        verdicts: The list of verdict dicts emitted by the LLM.
        ts: This run's timestamp.
    """
    for verdict in verdicts:
        url = verdict.get("url")
        if not url:
            continue
        key = canonical(url)
        entry = state["listings"].get(key)
        if entry is None:
            entry = {
                "url": url,
                "source_kind": verdict.get("source_kind", "browser"),
                "first_seen": ts,
                "removed": False,
            }
            for field in ("name", "breed", "age", "sex", "size", "location", "shelter", "fee", "status"):
                entry[field] = verdict.get(field)
            state["listings"][key] = entry
        entry["last_seen"] = ts
        if verdict.get("verdict") in (QUALIFIED, REJECTED, PENDING):
            entry["verdict"] = verdict["verdict"]
        if "summary" in verdict:
            entry["summary"] = verdict["summary"]
        if "tags" in verdict:
            entry["tags"] = verdict["tags"]
        if verdict.get("removed"):
            entry["removed"] = True
        # A judged listing no longer needs re-checking.
        entry["recheck"] = None
        entry["recheck_reason"] = None
