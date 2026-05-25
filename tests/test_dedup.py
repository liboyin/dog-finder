"""Tests for URL canonicalization."""
from __future__ import annotations

import unittest

from src import dedup


class CanonicalTest(unittest.TestCase):
    def test_trailing_slash_and_fragment_removed(self):
        """Trailing slash and fragment are normalized away."""
        self.assertEqual(
            dedup.canonical("https://Example.com/Path/#frag"),
            "https://example.com/Path",
        )


if __name__ == "__main__":
    unittest.main()
