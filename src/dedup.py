"""Extract the set of already-indexed dog URLs from dog-index.md.

URLs under both "Current candidates" and "Recently adopted" count as known, so a
re-listed or already-adopted dog is never surfaced as a new candidate.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_URL_RE = re.compile(r"https?://[^\s)<>\]]+")


def canonical(url: str) -> str:
    """Normalize a URL for set membership.

    Lowercases scheme and host, drops the fragment, and strips a trailing slash
    so equivalent URLs compare equal.

    Args:
        url: A raw URL, possibly with trailing punctuation already removed.

    Returns:
        The canonicalized URL string.
    """
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
    )


def known_urls(index_md: str) -> set[str]:
    """Collect every canonicalized dog URL already present in the index.

    Args:
        index_md: Full text of data/dog-index.md.

    Returns:
        A set of canonicalized URLs treated as already-known.
    """
    urls: set[str] = set()
    for match in _URL_RE.finditer(index_md):
        raw = match.group(0).rstrip(".,;)")
        urls.add(canonical(raw))
    return urls
