"""Parser for PetRescue group/search list pages and listing detail pages.

PetRescue (petrescue.com.au) is server-rendered, so listing cards and the
per-listing detail page can be parsed from static HTML. List cards expose
url/name/size/sex/location; breed and adoption fee live on the detail page
(in the ``application/ld+json`` ``Thing`` block and a labelled fee field).

Parsers raise :class:`ParseError` when the markup no longer matches what we
expect, so a silently-broken parser surfaces in the run manifest rather than
quietly dropping a shelter.
"""
from __future__ import annotations

import json
import re

from src.parsers.base import (
    Listing,
    ParseError,
    clean,
    first_group,
    is_dog,
    species_of,
    split_species,
)

# Re-export shared names so callers/tests can use src.parsers.petrescue.X.
__all__ = ["Listing", "ParseError", "is_dog", "species_of", "split_species",
           "parse_list", "parse_detail", "BASE_URL"]

SOURCE_KIND = "petrescue"
BASE_URL = "https://www.petrescue.com.au"

_CARD_RE = re.compile(
    r"<a class='cards-listings-preview__content' href='(/listings/\d+)'>(.*?)</a>",
    re.S,
)
_H3_RE = re.compile(r"<h3>(.*?)</h3>", re.S)
_SPECIES_RE = re.compile(
    r"__section__species'>.*?</i>\s*(.*?)\s*</div>", re.S
)
_LOCATION_RE = re.compile(
    r"__section__location'>.*?</i>\s*(.*?)\s*</div>", re.S
)

_LDJSON_RE = re.compile(
    r'<script type=["\']application/ld\+json["\']>(.*?)</script>', re.S
)
_FEE_RE = re.compile(r"Adoption fee\s*</div>\s*<div[^>]*>\s*(\$[\d,.]+)", re.S)
_ONHOLD_RE = re.compile(r">\s*On hold\s*<", re.I)
_ADOPTED_RE = re.compile(r">\s*Adopted\s*<", re.I)


def parse_list(html_text: str) -> list[Listing]:
    """Parse a PetRescue group or search page into card-level listings.

    Args:
        html_text: Raw HTML of a ``/groups/...`` or ``/listings/search`` page.

    Returns:
        One Listing per card with url, name, size, sex, and location populated.
        An empty list means the page rendered no cards (the caller treats this
        as EMPTY_OK), which is distinct from a parse failure.

    Raises:
        ParseError: If a card matches but yields no name, indicating the card
            template changed (markup drift).
    """
    listings: list[Listing] = []
    for href, inner in _CARD_RE.findall(html_text):
        name = clean(first_group(_H3_RE, inner))
        if name is None:
            raise ParseError(
                f"card {href} matched but has no <h3> name (template drift)"
            )
        species_phrase = first_group(_SPECIES_RE, inner)
        size, sex, _ = split_species(species_phrase)
        listings.append(
            Listing(
                url=BASE_URL + href,
                name=name,
                size=size,
                sex=sex,
                species=species_of(species_phrase),
                location=clean(first_group(_LOCATION_RE, inner)),
            )
        )
    return listings


def parse_detail(html_text: str, listing: Listing) -> Listing:
    """Enrich a card-level Listing with breed/size/sex/fee/status from its page.

    Args:
        html_text: Raw HTML of a ``/listings/<id>`` detail page.
        listing: The card-level Listing to enrich (mutated in place and returned).

    Returns:
        The same Listing with breed (and size/sex/fee/status) filled where found.

    Raises:
        ParseError: If the page lacks the ``Thing`` ld+json description used to
            derive breed (markup drift).
    """
    description = None
    for match in _LDJSON_RE.finditer(html_text):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Thing":
            description = data.get("description")
            listing.name = listing.name or clean(data.get("name"))
            if description:
                break
    if not description:
        raise ParseError(f"no Thing ld+json description on {listing.url}")

    size, sex, breed = split_species(description)
    listing.size = listing.size or size
    listing.sex = listing.sex or sex
    listing.breed = breed
    listing.species = listing.species or species_of(description)

    fee_match = _FEE_RE.search(html_text)
    listing.fee = fee_match.group(1) if fee_match else None
    listing.status = _detect_status(html_text)
    return listing


def _detect_status(html_text: str) -> str:
    """Best-effort listing status: 'adopted', 'on-hold', or 'available'."""
    if _ADOPTED_RE.search(html_text):
        return "adopted"
    if _ONHOLD_RE.search(html_text):
        return "on-hold"
    return "available"
