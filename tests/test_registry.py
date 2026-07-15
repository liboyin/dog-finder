"""Tests for parser registry host resolution."""
from __future__ import annotations

import unittest

from src.parsers import petrescue, registry, wollongong


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
        """Wollongong resolves to its own parser."""
        self.assertIs(registry.resolve({"listing_url": "https://www.wollongong.nsw.gov.au/residents/pets/find-a-pet/find-a-dog"})[0], wollongong)

    def test_unsupported_site_returns_none(self):
        """A site with no registered parser resolves to None (NEEDS_BROWSER)."""
        self.assertIsNone(registry.resolve({"listing_url": "https://sydneydogsandcatshome.org/adopt/"}))


class RegistryContractTest(unittest.TestCase):
    def test_every_parser_defines_parse_detail(self):
        """Vanish detection re-fetches each qualified dog's detail page, so a
        registered parser without parse_detail would silently disable it."""
        for host, module in registry._REGISTRY:
            self.assertTrue(
                hasattr(module, "parse_detail"),
                f"parser for {host} must define parse_detail",
            )

    def test_every_parser_has_a_unique_source_kind(self):
        """by_source_kind maps a stored SOURCE_KIND back to its parser for the
        detail recheck, so each module needs a distinct, defined SOURCE_KIND."""
        kinds = [getattr(module, "SOURCE_KIND", None) for _, module in registry._REGISTRY]
        self.assertTrue(all(kinds), "every registered parser must define SOURCE_KIND")
        self.assertEqual(len(kinds), len(set(kinds)), "SOURCE_KIND values must be unique")


class BySourceKindTest(unittest.TestCase):
    def test_known_kinds_resolve_to_their_module(self):
        """"petrescue" and "wollongong" resolve to their respective modules."""
        self.assertIs(registry.by_source_kind("petrescue"), petrescue)
        self.assertIs(registry.by_source_kind("wollongong"), wollongong)

    def test_unknown_kind_returns_none(self):
        """An unregistered kind (e.g. "browser") returns None."""
        self.assertIsNone(registry.by_source_kind("browser"))
        self.assertIsNone(registry.by_source_kind(None))


if __name__ == "__main__":
    unittest.main()
