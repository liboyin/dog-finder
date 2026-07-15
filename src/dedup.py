"""URL canonicalization for dedup keys.

Listings in ``state.json`` are keyed by a canonical form of their URL so
equivalent URLs (trailing slash, host case) collapse to one entry.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def canonical(url: str) -> str:
    """Normalize a URL for set membership.

    Lowercases scheme and host and strips a trailing slash so equivalent URLs
    compare equal. The fragment is *preserved*, because a shared-listing page
    (e.g. PAWS hosting several dogs at one URL) distinguishes each dog by a
    ``#name-slug`` anchor — dropping it would collapse every dog on the page into
    one state entry and lose all but the last.

    Args:
        url: A raw URL, possibly with trailing punctuation already removed.

    Returns:
        The canonicalized URL string.
    """
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, parts.fragment)
    )
