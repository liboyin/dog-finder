"""Map a shelter to the parser module that can handle its listings.

A parser module exposes ``parse_list(html) -> list[Listing]`` and, when the list
page lacks fields that need a per-dog page, ``parse_detail(html, listing)``.
``resolve`` picks the first parser whose host appears in the shelter's
``listing_url`` or ``petrescue_url`` — so a JS-rendered shelter that also
cross-posts to PetRescue is still handled in code via that cross-post.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from src.parsers import petrescue, wollongong

# (registered host, parser module). First match wins. Entries are added here as
# each site parser lands.
_REGISTRY = [
    ("petrescue.com.au", petrescue),
    ("wollongong.nsw.gov.au", wollongong),
]


def _host_matches(url: str, host: str) -> bool:
    """True if url's hostname equals host or is a subdomain of it.

    Matches on the parsed hostname (not a raw substring) so a lookalike domain
    like ``sydneypetrescue.com.au`` does not match ``petrescue.com.au``.
    """
    netloc = urlsplit(url).netloc.lower()
    return netloc == host or netloc.endswith("." + host)


def resolve(shelter: dict):
    """Return (parser_module, url) for a shelter, or None if unsupported.

    Args:
        shelter: A shelter config entry.

    Returns:
        A (module, url) tuple where url is the matched listing/cross-post URL,
        or None when no registered parser matches (the pipeline then flags the
        shelter NEEDS_BROWSER).
    """
    for host, module in _REGISTRY:
        for candidate in (shelter.get("listing_url", ""), shelter.get("petrescue_url", "")):
            if candidate and _host_matches(candidate, host):
                return module, candidate
    return None


def by_source_kind(source_kind: str | None):
    """Return the parser module whose ``SOURCE_KIND`` matches, or None.

    Args:
        source_kind: A state entry's stored ``source_kind`` (e.g. "petrescue").

    Returns:
        The registered parser module, or None for an unknown kind (e.g.
        "browser", which has no static detail page to re-fetch).
    """
    for _, module in _REGISTRY:
        if getattr(module, "SOURCE_KIND", None) == source_kind:
            return module
    return None
