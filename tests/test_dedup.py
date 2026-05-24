"""Tests for known-URL extraction and canonicalization from the index."""
from __future__ import annotations

import unittest

from src import dedup

SAMPLE_INDEX = """
## Current candidates

### [NEW 2026-05-24] Kev — Poodle x Pug
- **URL:** https://www.petrescue.com.au/listings/1187908
- more text

## Recently adopted

- https://www.petrescue.com.au/listings/977903 — Miso (Mini Poodle).
- https://www.deniseatpaws.com.au/adopt-a-pet — Bindi

See [shelters.json](shelters.json) for targets.
"""


class KnownUrlsTest(unittest.TestCase):
    def test_collects_candidate_and_adopted_urls(self):
        """URLs from both candidates and adopted sections are treated as known."""
        urls = dedup.known_urls(SAMPLE_INDEX)
        self.assertIn("https://www.petrescue.com.au/listings/1187908", urls)
        self.assertIn("https://www.petrescue.com.au/listings/977903", urls)
        self.assertIn("https://www.deniseatpaws.com.au/adopt-a-pet", urls)

    def test_ignores_relative_links(self):
        """Relative markdown links (shelters.json) are not captured as URLs."""
        urls = dedup.known_urls(SAMPLE_INDEX)
        self.assertFalse(any("shelters.json" in u for u in urls))

    def test_trailing_punctuation_stripped(self):
        """A URL followed by a period is captured without the period."""
        urls = dedup.known_urls(SAMPLE_INDEX)
        self.assertNotIn("https://www.petrescue.com.au/listings/977903.", urls)


class CanonicalTest(unittest.TestCase):
    def test_trailing_slash_and_fragment_removed(self):
        """Trailing slash and fragment are normalized away."""
        self.assertEqual(
            dedup.canonical("https://Example.com/Path/#frag"),
            "https://example.com/Path",
        )


if __name__ == "__main__":
    unittest.main()
