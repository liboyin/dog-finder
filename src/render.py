"""Render the human-facing dog list from state into data/dog-index.md.

Only the region between the DOGS markers is machine-managed; the surrounding
prose (filter description, notes, monitored-shelters pointer) is human-authored
and left untouched. The ``Last refreshed`` line is updated in place.
"""
from __future__ import annotations

import re

BEGIN_MARKER = "<!-- DOGS:BEGIN (auto-generated from state.json by src/render.py — do not edit) -->"
END_MARKER = "<!-- DOGS:END -->"

_REGION_RE = re.compile(
    re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER), re.S
)
_LAST_REFRESHED_RE = re.compile(r"(- \*\*Last refreshed:\*\*\s*).*")


def _as_date(first_seen: str | None) -> str:
    """Convert a 'YYYYMMDD-HHMMSS' run timestamp to 'YYYY-MM-DD'."""
    if not first_seen or len(first_seen) < 8:
        return "unknown"
    return f"{first_seen[0:4]}-{first_seen[4:6]}-{first_seen[6:8]}"


def _value(text: str | None, fallback: str = "not stated") -> str:
    """Return text or a fallback when it is None/empty."""
    return text if text else fallback


def render_block(entry: dict) -> str:
    """Render one qualified listing as a Markdown '###' block.

    Args:
        entry: A qualified state entry.

    Returns:
        The Markdown block (no trailing newline).
    """
    date = _as_date(entry.get("first_seen"))
    headline_bits = [
        _value(entry.get("breed"), "breed unstated"),
        _value(entry.get("age")),
        _value(entry.get("sex")),
    ]
    tags = entry.get("tags") or []
    tag_suffix = f"  _({', '.join(tags)})_" if tags else ""
    return "\n".join(
        [
            f"### [NEW {date}] {_value(entry.get('name'), 'Unnamed')} — {', '.join(headline_bits)}",
            f"- **URL:** {entry.get('url')}",
            f"- **Shelter:** {_value(entry.get('shelter'), 'unknown')} ({_value(entry.get('location'), 'location unstated')})",
            f"- **Status:** {_value(entry.get('status'), 'available')} · **Fee:** {_value(entry.get('fee'))} · **Size:** {_value(entry.get('size'))}",
            f"- **date_indexed:** {date}",
            f"- {_value(entry.get('summary'), 'No summary.')}{tag_suffix}",
        ]
    )


def render_index(current_md: str, entries: list[dict], refreshed_date: str) -> str:
    """Replace the managed dog region and Last-refreshed date in the index.

    Args:
        current_md: The existing dog-index.md text (must contain the markers).
        entries: Qualified listings, already sorted newest-first.
        refreshed_date: Today's date as 'YYYY-MM-DD'.

    Returns:
        The updated Markdown text.

    Raises:
        ValueError: If the DOGS markers are absent from current_md.
    """
    if BEGIN_MARKER not in current_md or END_MARKER not in current_md:
        raise ValueError("dog-index.md is missing the DOGS:BEGIN/END markers")

    blocks = "\n\n".join(render_block(entry) for entry in entries)
    body = f"{BEGIN_MARKER}\n\n{blocks}\n\n{END_MARKER}" if blocks else f"{BEGIN_MARKER}\n\n_No current candidates._\n\n{END_MARKER}"
    updated = _REGION_RE.sub(lambda _: body, current_md)
    updated = _LAST_REFRESHED_RE.sub(rf"\g<1>{refreshed_date}", updated, count=1)
    return updated
