"""Tests for the Wollongong Pet Connection parser against captured HTML fixtures."""
from __future__ import annotations

import pathlib
import unittest

from src.parsers import wollongong
from src.parsers.base import Listing

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    """Read a fixture HTML file by name."""
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseListTest(unittest.TestCase):
    def test_list_yields_dogs_with_urls_and_names(self):
        """The list fixture parses into dog listings with detail URLs and names."""
        listings = wollongong.parse_list(_load("wollongong_list.html"))
        self.assertGreater(len(listings), 1)
        names = {l.name for l in listings}
        self.assertIn("Kev", names)
        for listing in listings:
            self.assertIn("/animal-adoptions/dogs/", listing.url)
            self.assertEqual(listing.species, "dog")

    def test_empty_page_returns_empty_list(self):
        """A page with no card list returns [] rather than raising."""
        self.assertEqual(wollongong.parse_list("<html>nothing</html>"), [])

    def test_list_marker_without_cards_raises(self):
        """The list marker with no parseable cards signals markup drift."""
        with self.assertRaises(wollongong.ParseError):
            wollongong.parse_list('<div class="news-list__item-heading"></div>')


class ParseDetailTest(unittest.TestCase):
    def test_detail_fills_breed_sex_age(self):
        """The detail fixture enriches a listing from its table rows."""
        listing = Listing(url="https://www.wollongong.nsw.gov.au/animal-adoptions/dogs/kev", name="Kev")
        wollongong.parse_detail(_load("wollongong_detail.html"), listing)
        self.assertEqual(listing.breed, "Poodle (Toy) x Pug cross")
        self.assertEqual(listing.sex, "male")
        self.assertIn("10 months", listing.age)
        self.assertNotIn("Please note", listing.age)
        self.assertEqual(listing.status, "available")
        self.assertEqual(listing.shelter, "Wollongong Pet Connection")

    def test_missing_rows_raises(self):
        """A detail page with none of the expected rows signals markup drift."""
        listing = Listing(url="https://www.wollongong.nsw.gov.au/animal-adoptions/dogs/x")
        with self.assertRaises(wollongong.ParseError):
            wollongong.parse_detail("<html><body>no table</body></html>", listing)


if __name__ == "__main__":
    unittest.main()
