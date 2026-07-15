"""Tests for URL canonicalization."""
from __future__ import annotations

import unittest

from src import dedup


class CanonicalTest(unittest.TestCase):
    def test_trailing_slash_removed_host_lowercased_fragment_kept(self):
        """Trailing slash and host case normalize away, but the per-dog fragment stays."""
        self.assertEqual(
            dedup.canonical("https://Example.com/Path/#bindi"),
            "https://example.com/Path#bindi",
        )

    def test_two_fragments_on_one_page_stay_distinct(self):
        """Two dogs on the same page keep separate keys via their fragments."""
        base = "https://www.paws.com.au/FosterCare/FosterCareDogs.html"
        self.assertNotEqual(
            dedup.canonical(base + "#bindi"),
            dedup.canonical(base + "#rex"),
        )


if __name__ == "__main__":
    unittest.main()
