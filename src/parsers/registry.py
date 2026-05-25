"""Map a shelter to the parser module that can handle its listings.

A parser module exposes ``parse_list(html) -> list[Listing]`` and, when the list
page lacks fields that need a per-dog page, ``parse_detail(html, listing)``.
``resolve`` picks the first parser whose host appears in the shelter's
``listing_url`` or ``petrescue_url`` — so a JS-rendered shelter that also
cross-posts to PetRescue is still handled in code via that cross-post.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from src.parsers import doggierescue, petrescue, wollongong

# (registered host, parser module). First match wins. Entries are added here as
# each site parser lands.
_REGISTRY = [
    ("petrescue.com.au", petrescue),
    ("doggierescue.com", doggierescue),
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
