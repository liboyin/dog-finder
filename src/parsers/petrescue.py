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

import html
import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.parsers.base import (
    Listing,
    ParseError,
    clean,
    first_group,
    is_dog,
    species_of,
    split_species,
    strip_tags,
)

# Re-export shared names so callers/tests can use src.parsers.petrescue.X.
__all__ = ["Listing", "ParseError", "is_dog", "species_of", "split_species",
           "parse_list", "parse_detail", "prepare_url", "next_page_url", "BASE_URL"]

SOURCE_KIND = "petrescue"
BASE_URL = "https://www.petrescue.com.au"
# Search results paginate; group pages do not. A larger page size cuts the
# number of search requests (the site caps the effective size around 60).
SEARCH_PER_PAGE = 60

_CARD_RE = re.compile(
    r"<a class='cards-listings-preview__content' "
    r"href='((?:https?://[^']*)?/listings/\d+)'>(.*?)</a>",
    re.S,
)
# Capture only the text node after the section's icon. PetRescue search cards
# emit malformed markup (a stray </strong>, the location div left open around a
# nested "interstate" block), so matching up to the first </div> leaks adjacent
# HTML; the size/sex/location value is always the plain text before the next tag.
_H3_RE = re.compile(r"<h3>(.*?)</h3>", re.S)
_SPECIES_RE = re.compile(r"__section__species'>.*?</i>\s*([^<]*)", re.S)
_LOCATION_RE = re.compile(r"__section__location'>.*?</i>\s*([^<]*)", re.S)

_LDJSON_RE = re.compile(
    r'<script type=["\']application/ld\+json["\']>(.*?)</script>', re.S
)
_FEE_RE = re.compile(r"Adoption fee\s*</div>\s*<div[^>]*>\s*(\$[\d,.]+)", re.S)
_ONHOLD_RE = re.compile(r">\s*On hold\s*<", re.I)
_ADOPTED_RE = re.compile(r">\s*Adopted\s*<", re.I)
_NEXT_TAG_RE = re.compile(r"<a\b[^>]*\brel=['\"]next['\"][^>]*>", re.I)
_HREF_RE = re.compile(r"href=['\"]([^'\"]+)['\"]")
# The rescue group that actually holds the dog: the detail page links to it via
# an anchor tagged data-label="group-name" whose href is /groups/<id>/<Name-Slug>.
_GROUP_RE = re.compile(
    r"<a\b([^>]*\bdata-label=['\"]group-name['\"][^>]*)>(.*?)</a>", re.S | re.I
)
_GROUP_SLUG_RE = re.compile(r"/groups/\d+/([^'\"?]+)")


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
                url=href if href.startswith("http") else BASE_URL + href,
                name=name,
                size=size,
                sex=sex,
                species=species_of(species_phrase),
                location=clean(first_group(_LOCATION_RE, inner)),
            )
        )
    return listings


def parse_detail(html_text: str, listing: Listing) -> Listing:
    """Enrich a card-level Listing with breed/size/sex/fee/status/shelter.

    Args:
        html_text: Raw HTML of a ``/listings/<id>`` detail page.
        listing: The card-level Listing to enrich (mutated in place and returned).

    Returns:
        The same Listing with breed (and size/sex/fee/status/shelter) filled
        where found.

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
    listing.shelter = _group_name(html_text)
    return listing


def _group_name(html_text: str) -> str | None:
    """Return the rescue group holding the dog, or None if the page has no link.

    Prefers the group anchor's visible text; falls back to un-slugging the URL
    tail (``RSPCA-Illawarra-Shelter`` -> ``RSPCA Illawarra Shelter``). A missing
    group link is not markup drift — some listings omit it — so this returns None
    rather than raising.
    """
    match = _GROUP_RE.search(html_text)
    if match is None:
        return None
    inner = strip_tags(match.group(2))
    if inner:
        return inner
    slug = first_group(_GROUP_SLUG_RE, match.group(1))
    return clean(slug.replace("-", " ")) if slug else None


def _detect_status(html_text: str) -> str:
    """Best-effort listing status: 'adopted', 'on-hold', or 'available'."""
    if _ADOPTED_RE.search(html_text):
        return "adopted"
    if _ONHOLD_RE.search(html_text):
        return "on-hold"
    return "available"


def _with_param(url: str, key: str, value: str) -> str:
    """Return url with the query parameter key set to value (replacing any existing)."""
    parts = urlsplit(url)
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key]
    params.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


def prepare_url(url: str) -> str:
    """Enlarge the page size for a search URL to cut request count; else unchanged.

    Args:
        url: The shelter's listing URL.

    Returns:
        The search URL with ``per_page`` set; group/other URLs are returned as-is.
    """
    if "/listings/search" not in url:
        return url
    return _with_param(url, "per_page", str(SEARCH_PER_PAGE))


def next_page_url(html_text: str, current_url: str) -> str | None:
    """Return the absolute URL of the next results page, or None on the last page.

    Group pages have no ``rel="next"`` link, so this returns None and they stay
    single-page. Search pages carry a ``rel="next"`` anchor whose href preserves
    the query; the page size is re-applied so it persists across pages.

    Args:
        html_text: Raw HTML of the current page.
        current_url: The URL the current page was fetched from (unused; the next
            link is self-contained).

    Returns:
        The next page's absolute URL, or None when there is no next page.
    """
    tag = _NEXT_TAG_RE.search(html_text)
    if tag is None:
        return None
    href = _HREF_RE.search(tag.group(0))
    if href is None:
        return None
    nxt = html.unescape(href.group(1))
    if nxt.startswith("/"):
        nxt = BASE_URL + nxt
    return _with_param(nxt, "per_page", str(SEARCH_PER_PAGE))
