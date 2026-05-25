"""Tests for parser registry host resolution."""
from __future__ import annotations

import unittest

from src.parsers import doggierescue, petrescue, registry, wollongong


class ResolveTest(unittest.TestCase):
    def test_petrescue_group_and_subdomain(self):
        """A petrescue.com.au URL resolves to the PetRescue parser."""
        module, url = registry.resolve({"listing_url": "https://www.petrescue.com.au/groups/1/X"})
        self.assertIs(module, petrescue)

    def test_lookalike_domain_does_not_match_petrescue(self):
        """sydneypetrescue.com.au must NOT resolve to the PetRescue parser."""
        self.assertIsNone(registry.resolve({"listing_url": "https://www.sydneypetrescue.com.au/"}))

    def test_js_shelter_resolved_via_petrescue_crosspost(self):
        """A JS shelter with a PetRescue cross-post resolves via that cross-post."""
        module, url = registry.resolve({
            "listing_url": "https://www.rspcansw.org.au/adopt-foster/",
            "petrescue_url": "https://www.petrescue.com.au/groups/10520/X",
            "render": "js",
        })
        self.assertIs(module, petrescue)
        self.assertIn("petrescue.com.au", url)

    def test_other_registered_sites(self):
        """Doggie Rescue and Wollongong resolve to their own parsers."""
        self.assertIs(registry.resolve({"listing_url": "https://www.doggierescue.com/search-pets/individual-dogs/"})[0], doggierescue)
        self.assertIs(registry.resolve({"listing_url": "https://www.wollongong.nsw.gov.au/residents/pets/find-a-pet/find-a-dog"})[0], wollongong)

    def test_unsupported_site_returns_none(self):
        """A site with no registered parser resolves to None (NEEDS_BROWSER)."""
        self.assertIsNone(registry.resolve({"listing_url": "https://sydneydogsandcatshome.org/adopt/"}))


if __name__ == "__main__":
    unittest.main()
