"""Run manifest: per-source fetch/parse outcomes for shelter-level observability.

Each monitored shelter produces one :class:`SourceResult`. The human reads the
manifest after a run to see which shelters were reached, which need the browser
path, and which parsers broke (PARSE_ERROR / EMPTY_OK) and need fixing.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

# Per-source status values.
STATUS_OK = "OK"
STATUS_EMPTY_OK = "EMPTY_OK"  # HTTP 200 but 0 cards — possibly a broken parser
STATUS_PARSE_ERROR = "PARSE_ERROR"  # markup drift; fix the parser
STATUS_FETCH_ERROR = "FETCH_ERROR"  # network/HTTP failure
STATUS_NEEDS_BROWSER = "NEEDS_BROWSER"  # JS-rendered or no code parser; LLM handles
STATUS_SKIPPED_DEAD = "SKIPPED_DEAD"  # render:dead — not attempted


@dataclass
class SourceResult:
    """Outcome of processing one shelter source."""

    shelter: str
    listing_url: str
    status: str
    render: str = "static"
    fetched_url: str | None = None
    http_status: int | None = None
    bytes: int | None = None
    n_cards: int | None = None
    n_new: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Return the source result as a plain dict for JSON serialization."""
        return asdict(self)


@dataclass
class Manifest:
    """The full run manifest: a run timestamp and one entry per source."""

    run_ts: str
    sources: list[SourceResult] = field(default_factory=list)

    def add(self, source: SourceResult) -> None:
        """Append a source result to the manifest."""
        self.sources.append(source)

    def write(self, path: str) -> None:
        """Serialize the manifest to a JSON file.

        Args:
            path: Destination file path for fetch_manifest.json.
        """
        payload = {
            "run_ts": self.run_ts,
            "sources": [source.to_dict() for source in self.sources],
        }
        with open(path, "w", encoding="utf-8") as out:
            json.dump(payload, out, indent=2, ensure_ascii=False)
