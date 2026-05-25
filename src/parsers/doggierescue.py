"""Parser for Doggie Rescue (doggierescue.com).

The individual-dogs page is a server-rendered Beaver Builder post grid: each dog
is a ``post-<id> mdr_dog`` item exposing only its detail URL and name. Breed,
sex, age, size, and fee live on the per-dog detail page, where each field is an
``<h5>`` label followed by an ``fl-rich-text`` value module.
"""
from __future__ import annotations

import html
import re

from src.parsers.base import Listing, ParseError, clean

SOURCE_KIND = "doggierescue"
DOG_URL = "https://www.doggierescue.com/dogs/{id}/"

_CARD_RE = re.compile(r"post-(\d+) mdr_dog.*?title='([^']+)'", re.S)
_GRID_MARKER = "mdr_dog"
# WordPress page-numbers pager: the "next" link carries the next ?sf_paged= URL.
_NEXT_TAG_RE = re.compile(
    r"<a[^>]*class=['\"][^'\"]*\bnext\b[^'\"]*page-numbers[^'\"]*['\"][^>]*>", re.I
)
_HREF_RE = re.compile(r"href=['\"]([^'\"]+)['\"]")


def parse_list(html_text: str) -> list[Listing]:
    """Parse the individual-dogs page into card-level listings.

    Args:
        html_text: Raw HTML of the individual-dogs listing page.

    Returns:
        One dog Listing per grid post, with url, name, and species set. An empty
        list means no dogs were rendered (caller treats it as EMPTY_OK).

    Raises:
        ParseError: If the dog grid is present but no posts parse (markup drift).
    """
    listings: list[Listing] = []
    for post_id, name in _CARD_RE.findall(html_text):
        listings.append(
            Listing(
                url=DOG_URL.format(id=post_id),
                name=clean(name),
                species="dog",
            )
        )
    if not listings and _GRID_MARKER in html_text:
        raise ParseError("Doggie Rescue dog grid present but no posts parsed (drift)")
    return listings


def next_page_url(html_text: str, current_url: str) -> str | None:
    """Return the next ``?sf_paged=`` page URL, or None on the last page.

    Args:
        html_text: Raw HTML of the current individual-dogs page.
        current_url: The URL the current page was fetched from (unused; the next
            link is absolute and self-contained).

    Returns:
        The next page's absolute URL, or None when the pager has no next link.
    """
    tag = _NEXT_TAG_RE.search(html_text)
    if tag is None:
        return None
    href = _HREF_RE.search(tag.group(0))
    return html.unescape(href.group(1)) if href else None


def _value_after(label: str, html_text: str) -> str | None:
    """Return the rich-text value following an ``<h5>`` field label, or None."""
    label_match = re.search(re.escape(label) + r"</span>\s*</h5>", html_text)
    if label_match is None:
        label_match = re.search(re.escape(label) + r"</h5>", html_text)
    if label_match is None:
        return None
    window = html_text[label_match.end():label_match.end() + 1200]
    value_match = re.search(r'fl-rich-text">\s*(.*?)</div>', window, re.S)
    if value_match is None:
        return None
    return clean(re.sub(r"<[^>]+>", " ", value_match.group(1)))


def parse_detail(html_text: str, listing: Listing) -> Listing:
    """Enrich a Listing with breed/sex/age/size/fee from its detail page.

    Args:
        html_text: Raw HTML of a ``/dogs/<id>/`` detail page.
        listing: The card-level Listing to enrich (mutated in place and returned).

    Returns:
        The same Listing with fields filled where found.

    Raises:
        ParseError: If none of the expected labelled fields are present (drift).
    """
    breed = _value_after("Breed", html_text)
    sex = _value_after("Sex", html_text)
    age = _value_after("Age", html_text)
    size = _value_after("Size", html_text)
    fee = _value_after("Adoption Fee", html_text)

    if breed is None and sex is None and age is None and size is None:
        raise ParseError(f"no labelled fields on {listing.url} (markup drift)")

    listing.breed = breed
    listing.sex = sex
    listing.age = age
    listing.size = size.lower() if size else None
    listing.fee = _format_fee(fee)
    listing.status = "available"
    return listing


def _format_fee(fee: str | None) -> str | None:
    """Prefix a bare numeric fee with '$'; pass other values through."""
    if not fee:
        return None
    return f"${fee}" if re.fullmatch(r"[\d,.]+", fee) else fee
