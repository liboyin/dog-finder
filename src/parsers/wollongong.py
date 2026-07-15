"""Parser for Wollongong Pet Connection (wollongong.nsw.gov.au council site).

The find-a-dog page lists each dog as a ``news-list__item`` card exposing its
detail URL and name. The per-dog page carries a simple ``<td>Label</td>
<td>Value</td>`` table with Breed, Gender, and Age (no size or fee).
"""
from __future__ import annotations

import re

from src.parsers.base import Listing, ParseError, clean

SOURCE_KIND = "wollongong"

_CARD_RE = re.compile(
    r'news-list__item-heading">\s*<a href="'
    r'(https://www\.wollongong\.nsw\.gov\.au/animal-adoptions/dogs/[^"]+)">([^<]+)</a>'
)
_LIST_MARKER = "news-list__item-heading"


def parse_list(html_text: str) -> list[Listing]:
    """Parse the find-a-dog page into card-level listings.

    Args:
        html_text: Raw HTML of the find-a-dog listing page.

    Returns:
        One dog Listing per card with url, name, and species set. An empty list
        means no dogs were rendered (caller treats it as EMPTY_OK).

    Raises:
        ParseError: If the list structure is present but no cards parse (drift).
    """
    listings = [
        Listing(url=url, name=clean(name), species="dog")
        for url, name in _CARD_RE.findall(html_text)
    ]
    if not listings and _LIST_MARKER in html_text:
        raise ParseError("Wollongong card list present but no items parsed (drift)")
    return listings


def _row_value(label: str, html_text: str) -> str | None:
    """Return the value cell following a ``<td>Label</td>`` row, or None."""
    match = re.search(
        r"<td>\s*" + re.escape(label) + r"\s*</td>\s*<td>(.*?)</td>",
        html_text, re.S | re.I,
    )
    if match is None:
        return None
    raw = match.group(1).split("<br")[0]  # drop trailing notes after a line break
    return clean(re.sub(r"<[^>]+>", " ", raw))


def parse_detail(html_text: str, listing: Listing) -> Listing:
    """Enrich a Listing with breed/sex/age from its detail-page table.

    Args:
        html_text: Raw HTML of a ``/animal-adoptions/dogs/<slug>`` page.
        listing: The card-level Listing to enrich (mutated in place and returned).

    Returns:
        The same Listing with breed/sex/age filled where found.

    Raises:
        ParseError: If none of the expected table rows are present (drift).
    """
    breed = _row_value("Breed", html_text)
    sex = _row_value("Gender", html_text)
    age = _row_value("Age", html_text)

    if breed is None and sex is None and age is None:
        raise ParseError(f"no detail table rows on {listing.url} (markup drift)")

    listing.breed = breed
    listing.sex = sex
    listing.age = age
    listing.status = "available"
    listing.shelter = "Wollongong Pet Connection"  # single-org council site
    return listing
