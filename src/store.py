"""Authoritative listing state for dog-finder, persisted as data/state.json.

The state file — not the Markdown index — is the source of truth for dedup and
history. Each entry is keyed by canonical URL and records the listing fields, the
LLM's qualify verdict, and first/last-seen run timestamps. Code owns this file;
the LLM only emits verdicts that ``apply_verdicts`` merges in.
"""
from __future__ import annotations

import json
import re

from src.dedup import canonical
from src.parsers.petrescue import Listing

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
    """Write the state document to disk as pretty JSON.

    Args:
        path: Destination path for state.json.
        state: The state dict to serialize.
    """
    with open(path, "w", encoding="utf-8") as out:
        json.dump(state, out, indent=2, ensure_ascii=False, sort_keys=True)


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


def flag_disappeared(state: dict, present: set[str], ts: str) -> list[dict]:
    """Flag qualified PetRescue dogs that vanished from this run's pages.

    A qualified, non-removed PetRescue listing not seen this run is a likely
    adoption, but could also be a transient fetch gap, so it is flagged
    ``recheck = "maybe_adopted"`` for the LLM to confirm rather than removed here.

    Args:
        state: The state document (mutated in place).
        present: Canonical URLs seen on successfully-fetched pages this run.
        ts: This run's timestamp.

    Returns:
        The list of entries newly flagged for re-check.
    """
    flagged = []
    for entry in state["listings"].values():
        if (
            entry.get("source_kind") != "browser"
            and entry.get("verdict") == QUALIFIED
            and not entry.get("removed")
            and entry["url"] not in present
            and canonical(entry["url"]) not in present
            and entry.get("recheck") != "maybe_adopted"
        ):
            entry["recheck"] = "maybe_adopted"
            flagged.append(entry)
    return flagged


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


# --- One-time migration from the legacy Markdown index --------------------

_BLOCK_RE = re.compile(
    r"^### \[NEW (\d{4}-\d{2}-\d{2})\] (.+?) — (.+?)\n"
    r"- \*\*URL:\*\* (\S+)\n"
    r"- \*\*Shelter:\*\* (.+?)\n"
    r"- \*\*Status:\*\* (.+?)\n"
    r"(?:- \*\*date_indexed:\*\* .+?\n)?"
    r"- (.+?)(?=\n###|\n---|\n## |\Z)",
    re.M | re.S,
)
_ADOPTED_RE = re.compile(r"^- (https?://\S+) — (.+)$", re.M)


def _parse_headline(headline: str) -> tuple[str, str | None, str | None]:
    """Split a '{breed}, {age}, {sex}' headline into its parts."""
    parts = [p.strip() for p in headline.split(",")]
    breed = parts[0]
    rest = parts[1:]
    sex = None
    if rest and rest[-1].lower() in ("male", "female"):
        sex = rest[-1]
        rest = rest[:-1]
    age = ", ".join(rest) or None
    return breed, age, sex


def _parse_shelter_line(line: str) -> tuple[str, str | None]:
    """Split a 'Shelter Name (Location)' line into (shelter, location)."""
    if line.rstrip().endswith(")") and " (" in line:
        shelter, location = line.rstrip()[:-1].rsplit(" (", 1)
        return shelter.strip(), location.strip()
    return line.strip(), None


def _parse_status_line(line: str) -> tuple[str | None, str | None, str | None]:
    """Split a 'status · **Fee:** x · **Size:** y' line into (status, fee, size)."""
    status = fee = size = None
    for index, segment in enumerate(line.split(" · ")):
        segment = segment.strip()
        if segment.startswith("**Fee:**"):
            fee = segment[len("**Fee:**"):].strip()
        elif segment.startswith("**Size:**"):
            size = segment[len("**Size:**"):].strip()
        elif index == 0:
            status = segment
    return status, fee, size


def seed_from_index(index_md: str, ts: str) -> dict:
    """Build an initial state from the legacy dog-index.md (one-time migration).

    Current-candidate blocks become qualified entries; recently-adopted bullets
    become qualified+removed entries so their URLs stay known for dedup.

    Args:
        index_md: Full text of the legacy dog-index.md.
        ts: Timestamp to record as last_seen for migrated entries.

    Returns:
        A populated state document.
    """
    state = empty_state()
    current_section = index_md.split("## Recently adopted")[0]
    for date, name, headline, url, shelter_line, status_line, summary in _BLOCK_RE.findall(current_section):
        breed, age, sex = _parse_headline(headline)
        shelter, location = _parse_shelter_line(shelter_line)
        status, fee, size = _parse_status_line(status_line)
        state["listings"][canonical(url)] = {
            "url": url, "name": name.strip(), "breed": breed,
            "age": age, "sex": sex, "size": size, "species": "dog",
            "location": location, "shelter": shelter, "fee": fee,
            "status": status, "source_kind": "petrescue",
            "first_seen": date.replace("-", "") + "-000000", "last_seen": ts,
            "verdict": QUALIFIED, "summary": summary.strip(), "tags": [],
            "removed": False, "recheck": None,
        }
    if "## Recently adopted" in index_md:
        adopted_section = index_md.split("## Recently adopted", 1)[1].split("\n## ")[0]
        for url, label in _ADOPTED_RE.findall(adopted_section):
            key = canonical(url)
            if key in state["listings"]:
                continue
            state["listings"][key] = {
                "url": url, "name": label.split("(")[0].strip(), "breed": None,
                "age": None, "sex": None, "size": None, "species": "dog",
                "location": None, "shelter": None, "fee": None, "status": "adopted",
                "source_kind": "petrescue", "first_seen": ts, "last_seen": ts,
                "verdict": QUALIFIED, "summary": None, "tags": [],
                "removed": True, "recheck": None,
            }
    return state
