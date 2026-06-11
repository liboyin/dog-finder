"""Tests for the PetRescue parser against real captured HTML fixtures."""
from __future__ import annotations

import pathlib
import unittest

from src.parsers import petrescue

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    """Read a fixture HTML file by name."""
    return (FIXTURES / name).read_text(encoding="utf-8")


class SplitSpeciesTest(unittest.TestCase):
    def test_detail_description_yields_breed(self):
        """Detail description splits into size, sex, and breed (sans species noun)."""
        size, sex, breed = petrescue.split_species(
            "Medium Female American Staffordshire Terrier Mix Dog"
        )
        self.assertEqual(size, "Medium")
        self.assertEqual(sex, "Female")
        self.assertEqual(breed, "American Staffordshire Terrier Mix")

    def test_card_phrase_has_no_breed(self):
        """A card phrase with no breed yields size and sex but breed None."""
        size, sex, breed = petrescue.split_species("medium female Dog")
        self.assertEqual(size, "Medium")
        self.assertEqual(sex, "Female")
        self.assertIsNone(breed)

    def test_empty_phrase(self):
        """An empty phrase yields all-None."""
        self.assertEqual(petrescue.split_species(None), (None, None, None))


class ParseListTest(unittest.TestCase):
    def test_group_page_yields_named_cards(self):
        """The group fixture parses into listings with URLs, names, and locations."""
        listings = petrescue.parse_list(_load("petrescue_group.html"))
        self.assertGreater(len(listings), 0)
        for listing in listings:
            self.assertTrue(listing.url.startswith("https://www.petrescue.com.au/listings/"))
            self.assertIsNotNone(listing.name)

    def test_known_card_present(self):
        """Bella's card is parsed with expected size, sex, and location."""
        listings = petrescue.parse_list(_load("petrescue_group.html"))
        bella = next((l for l in listings if l.name == "Bella"), None)
        self.assertIsNotNone(bella)
        self.assertEqual(bella.size, "Medium")
        self.assertEqual(bella.sex, "Female")
        self.assertIn("NSW", bella.location)

    def test_species_detected_and_non_dogs_excludable(self):
        """Cards carry a species; the group fixture includes a non-dog the filter drops."""
        listings = petrescue.parse_list(_load("petrescue_group.html"))
        dogs = [l for l in listings if petrescue.is_dog(l)]
        non_dogs = [l for l in listings if not petrescue.is_dog(l)]
        self.assertTrue(any(l.species == "dog" for l in dogs))
        self.assertTrue(non_dogs, "fixture should contain at least one non-dog (rabbit)")
        self.assertNotIn("Tinkerbell", [l.name for l in dogs])

    def test_search_page_absolute_hrefs(self):
        """Search-aggregator cards use absolute hrefs and still parse to listing URLs."""
        listings = petrescue.parse_list(_load("petrescue_search.html"))
        self.assertGreater(len(listings), 0)
        for listing in listings:
            self.assertRegex(listing.url, r"^https://www\.petrescue\.com\.au/listings/\d+$")
            self.assertIsNotNone(listing.name)

    def test_search_card_fields_have_no_markup_leak(self):
        """Search cards yield clean location/size/sex despite malformed card markup."""
        listings = petrescue.parse_list(_load("petrescue_search.html"))
        for listing in listings:
            for value in (listing.location, listing.size, listing.sex):
                if value:
                    self.assertNotIn("<", value)
                    self.assertNotIn("Interstate", value)
        first = listings[0]
        self.assertEqual(first.location, "Sydney, NSW")
        self.assertEqual(first.size, "Medium")
        self.assertEqual(first.sex, "Male")
        self.assertTrue(petrescue.is_dog(first))

    def test_empty_page_returns_empty_list(self):
        """A page with no cards returns [] rather than raising."""
        self.assertEqual(petrescue.parse_list("<html><body>no cards</body></html>"), [])

    def test_card_without_name_raises(self):
        """A card matching the template but lacking a name signals markup drift."""
        broken = "<a class='cards-listings-preview__content' href='/listings/1'></a>"
        with self.assertRaises(petrescue.ParseError):
            petrescue.parse_list(broken)


class PaginationTest(unittest.TestCase):
    def test_prepare_url_enlarges_search_only(self):
        """prepare_url adds per_page to a search URL but leaves group URLs alone."""
        search = petrescue.prepare_url("https://www.petrescue.com.au/listings/search/dogs?q=poodle&state_id=1")
        self.assertIn("per_page=60", search)
        group = "https://www.petrescue.com.au/groups/10748/X"
        self.assertEqual(petrescue.prepare_url(group), group)

    def test_next_page_on_search_fixture(self):
        """A search page yields an absolute next-page URL carrying page and per_page."""
        nxt = petrescue.next_page_url(_load("petrescue_search.html"), "https://www.petrescue.com.au/listings/search/dogs?q=poodle&state_id=1")
        self.assertIsNotNone(nxt)
        self.assertTrue(nxt.startswith("https://www.petrescue.com.au/"))
        self.assertIn("page=2", nxt)
        self.assertIn("per_page=60", nxt)

    def test_no_next_on_group_fixture(self):
        """A group page has no next link, so it stays single-page."""
        self.assertIsNone(petrescue.next_page_url(_load("petrescue_group.html"), "https://www.petrescue.com.au/groups/1/X"))


class ParseDetailTest(unittest.TestCase):
    def test_detail_fixture_fills_breed_and_fee(self):
        """The detail fixture enriches a listing with breed and adoption fee."""
        listing = petrescue.Listing(url="https://www.petrescue.com.au/listings/1192935")
        petrescue.parse_detail(_load("petrescue_detail.html"), listing)
        self.assertEqual(listing.breed, "American Staffordshire Terrier Mix")
        self.assertEqual(listing.size, "Medium")
        self.assertEqual(listing.sex, "Female")
        self.assertEqual(listing.fee, "$500.00")
        self.assertEqual(listing.status, "available")

    def test_missing_ldjson_raises(self):
        """A detail page without the Thing ld+json signals markup drift."""
        listing = petrescue.Listing(url="https://www.petrescue.com.au/listings/1")
        with self.assertRaises(petrescue.ParseError):
            petrescue.parse_detail("<html><body>nothing</body></html>", listing)


if __name__ == "__main__":
    unittest.main()
