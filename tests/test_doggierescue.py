"""Tests for the Doggie Rescue parser against captured HTML fixtures."""
from __future__ import annotations

import pathlib
import unittest

from src.parsers import doggierescue
from src.parsers.base import Listing

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    """Read a fixture HTML file by name."""
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseListTest(unittest.TestCase):
    def test_list_yields_dogs_with_urls_and_names(self):
        """The list fixture parses into dog listings with /dogs/<id>/ URLs and names."""
        listings = doggierescue.parse_list(_load("doggierescue_list.html"))
        self.assertGreater(len(listings), 1)
        names = {l.name for l in listings}
        self.assertIn("BonBon", names)
        for listing in listings:
            self.assertRegex(listing.url, r"^https://www\.doggierescue\.com/dogs/\d+/$")
            self.assertEqual(listing.species, "dog")

    def test_empty_page_returns_empty_list(self):
        """A page with no grid returns [] rather than raising."""
        self.assertEqual(doggierescue.parse_list("<html>nothing</html>"), [])

    def test_grid_without_posts_raises(self):
        """A dog grid marker with no parseable posts signals markup drift."""
        with self.assertRaises(doggierescue.ParseError):
            doggierescue.parse_list("<div class='mdr_dog'></div>")


class PaginationTest(unittest.TestCase):
    def test_next_page_from_list_fixture(self):
        """The list fixture's pager yields the next ?sf_paged= page URL."""
        nxt = doggierescue.next_page_url(_load("doggierescue_list.html"), "https://www.doggierescue.com/search-pets/individual-dogs/")
        self.assertIsNotNone(nxt)
        self.assertIn("sf_paged=2", nxt)

    def test_no_next_link_returns_none(self):
        """A page without a next page-numbers link is the last page."""
        self.assertIsNone(doggierescue.next_page_url("<ul class='pagination'></ul>", "https://www.doggierescue.com/x"))


class ParseDetailTest(unittest.TestCase):
    def test_detail_fills_breed_sex_age_size_fee(self):
        """The detail fixture enriches a listing with its labelled fields."""
        listing = Listing(url="https://www.doggierescue.com/dogs/52337/", name="BonBon")
        doggierescue.parse_detail(_load("doggierescue_detail.html"), listing)
        self.assertEqual(listing.breed, "French Bulldog X")
        self.assertEqual(listing.sex, "female")
        self.assertEqual(listing.size, "small")
        self.assertIn("3 years", listing.age)
        self.assertEqual(listing.fee, "$800")
        self.assertEqual(listing.status, "available")

    def test_missing_fields_raises(self):
        """A detail page with none of the labelled fields signals markup drift."""
        listing = Listing(url="https://www.doggierescue.com/dogs/1/")
        with self.assertRaises(doggierescue.ParseError):
            doggierescue.parse_detail("<html><body>no fields</body></html>", listing)


if __name__ == "__main__":
    unittest.main()
