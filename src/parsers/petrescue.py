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
from dataclasses import asdict, dataclass

BASE_URL = "https://www.petrescue.com.au"

_SIZES = {"small", "medium", "large"}
_SEXES = {"male", "female"}
_SPECIES_TAIL = {
    "dog", "dogs", "puppy", "puppies", "cat", "cats", "kitten", "kittens",
    "rabbit", "rabbits", "guinea", "bird", "birds", "horse", "pig",
}
DOG_SPECIES = {"dog", "dogs", "puppy", "puppies"}

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


class ParseError(Exception):
    """Raised when PetRescue markup does not match the expected structure."""


@dataclass
class Listing:
    """A single dog listing, progressively enriched from card then detail page."""

    url: str
    name: str | None = None
    breed: str | None = None
    age: str | None = None
    sex: str | None = None
    size: str | None = None
    species: str | None = None
    location: str | None = None
    shelter: str | None = None
    fee: str | None = None
    status: str | None = None

    def to_dict(self) -> dict:
        """Return the listing as a plain dict for JSON serialization."""
        return asdict(self)


def _clean(text: str | None) -> str | None:
    """Collapse whitespace and unescape HTML entities, or return None if empty."""
    if text is None:
        return None
    cleaned = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return cleaned or None


def split_species(description: str | None) -> tuple[str | None, str | None, str | None]:
    """Split a PetRescue species phrase into (size, sex, breed).

    Handles both the card phrase ("medium female Dog", no breed) and the detail
    description ("Medium Female American Staffordshire Terrier Mix Dog").

    Args:
        description: The raw species/description phrase.

    Returns:
        A (size, sex, breed) tuple; any component is None when absent. Breed
        retains qualifiers such as "Mix" but drops the trailing species noun.
    """
    cleaned = _clean(description)
    if not cleaned:
        return None, None, None
    words = cleaned.split()
    size = sex = None
    index = 0
    if index < len(words) and words[index].lower() in _SIZES:
        size = words[index].capitalize()
        index += 1
    if index < len(words) and words[index].lower() in _SEXES:
        sex = words[index].capitalize()
        index += 1
    rest = words[index:]
    if rest and rest[-1].lower() in _SPECIES_TAIL:
        rest = rest[:-1]
    breed = " ".join(rest) or None
    return size, sex, breed


def species_of(phrase: str | None) -> str | None:
    """Return the lowercase species noun ending a PetRescue phrase, or None.

    Args:
        phrase: A card species phrase or detail description.

    Returns:
        The trailing animal noun ("dog", "cat", "rabbit", ...) if recognized.
    """
    cleaned = _clean(phrase)
    if not cleaned:
        return None
    last = cleaned.split()[-1].lower()
    return last if last in _SPECIES_TAIL else None


def is_dog(listing: Listing) -> bool:
    """Return True if the listing's species is a dog (or unknown, kept as dog)."""
    return listing.species is None or listing.species in DOG_SPECIES


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
        name = _clean(_first_group(_H3_RE, inner))
        if name is None:
            raise ParseError(
                f"card {href} matched but has no <h3> name (template drift)"
            )
        species_phrase = _first_group(_SPECIES_RE, inner)
        size, sex, _ = split_species(species_phrase)
        listings.append(
            Listing(
                url=BASE_URL + href,
                name=name,
                size=size,
                sex=sex,
                species=species_of(species_phrase),
                location=_clean(_first_group(_LOCATION_RE, inner)),
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
            listing.name = listing.name or _clean(data.get("name"))
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


def _first_group(pattern: re.Pattern, text: str) -> str | None:
    """Return the first capture group of a regex match against text, or None."""
    match = pattern.search(text)
    return match.group(1) if match else None
