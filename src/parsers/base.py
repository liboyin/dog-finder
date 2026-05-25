"""Shared types and helpers for shelter listing parsers.

Every site parser produces :class:`Listing` records and raises
:class:`ParseError` on markup drift, so the pipeline can treat all parsers
uniformly. Generic size/sex/species helpers live here too, since several sites
describe a dog with the same "size sex breed species" shape PetRescue uses.
"""
from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass

_SIZES = {"small", "medium", "large"}
_SEXES = {"male", "female"}
_SPECIES_TAIL = {
    "dog", "dogs", "puppy", "puppies", "cat", "cats", "kitten", "kittens",
    "rabbit", "rabbits", "guinea", "bird", "birds", "horse", "pig",
}
DOG_SPECIES = {"dog", "dogs", "puppy", "puppies"}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class ParseError(Exception):
    """Raised when a site's markup does not match the expected structure."""


@dataclass
class Listing:
    """A single dog listing, progressively enriched as a parser learns more."""

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


def clean(text: str | None) -> str | None:
    """Collapse whitespace and unescape HTML entities, or return None if empty.

    Args:
        text: Raw text possibly containing entities and irregular whitespace.

    Returns:
        The cleaned string, or None when the result is empty.
    """
    if text is None:
        return None
    cleaned = html.unescape(_WS_RE.sub(" ", text)).strip()
    return cleaned or None


def strip_tags(html_fragment: str | None) -> str | None:
    """Remove HTML tags from a fragment and clean the remaining text."""
    if html_fragment is None:
        return None
    return clean(_TAG_RE.sub(" ", html_fragment))


def first_group(pattern: re.Pattern, text: str) -> str | None:
    """Return the first capture group of a regex match against text, or None."""
    match = pattern.search(text)
    return match.group(1) if match else None


def split_species(description: str | None) -> tuple[str | None, str | None, str | None]:
    """Split a "size sex breed species" phrase into (size, sex, breed).

    Handles phrases like "medium female Dog" (no breed) and
    "Medium Female American Staffordshire Terrier Mix Dog".

    Args:
        description: The raw species/description phrase.

    Returns:
        A (size, sex, breed) tuple; any component is None when absent. Breed
        retains qualifiers such as "Mix" but drops the trailing species noun.
    """
    cleaned = clean(description)
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
    """Return the lowercase species noun ending a phrase, or None.

    Args:
        phrase: A species phrase or description.

    Returns:
        The trailing animal noun ("dog", "cat", "rabbit", ...) if recognized.
    """
    cleaned = clean(phrase)
    if not cleaned:
        return None
    last = cleaned.split()[-1].lower()
    return last if last in _SPECIES_TAIL else None


def is_dog(listing: Listing) -> bool:
    """Return True if the listing's species is a dog (unknown counts as dog)."""
    return listing.species is None or listing.species in DOG_SPECIES
