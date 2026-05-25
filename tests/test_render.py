"""Tests for rendering the dog list into the marked region of the index."""
from __future__ import annotations

import unittest

from src import render

INDEX = f"""# Title

- **Last refreshed:** 2026-01-01

## Current candidates

{render.BEGIN_MARKER}

_old content_

{render.END_MARKER}

## Monitored shelters
"""

ENTRY = {
    "url": "https://x/listings/1", "name": "Bella", "breed": "Maltese",
    "age": None, "sex": "Female", "size": "small", "location": "Sydney, NSW",
    "shelter": "Test Shelter", "fee": "$300", "status": "available",
    "summary": "A lovely maltese.", "tags": ["verify drive time"],
    "first_seen": "20260520-120000",
}


class RenderBlockTest(unittest.TestCase):
    def test_block_fields_and_tag(self):
        """A block renders fields, formats the date, and appends tags."""
        block = render.render_block(ENTRY)
        self.assertIn("### [NEW 2026-05-20] Bella — Maltese, not stated, Female", block)
        self.assertIn("**URL:** https://x/listings/1", block)
        self.assertIn("Test Shelter (Sydney, NSW)", block)
        self.assertIn("_(verify drive time)_", block)


class RenderIndexTest(unittest.TestCase):
    def test_region_replaced_and_date_updated(self):
        """The managed region is replaced and Last refreshed is updated."""
        out = render.render_index(INDEX, [ENTRY], "2026-05-25")
        self.assertNotIn("_old content_", out)
        self.assertIn("Bella", out)
        self.assertIn("- **Last refreshed:** 2026-05-25", out)
        self.assertIn("## Monitored shelters", out)

    def test_empty_entries_placeholder(self):
        """With no entries the region shows a placeholder, not stale content."""
        out = render.render_index(INDEX, [], "2026-05-25")
        self.assertIn("_No current candidates._", out)

    def test_missing_markers_raises(self):
        """Rendering an index without the markers is an error."""
        with self.assertRaises(ValueError):
            render.render_index("# no markers here", [ENTRY], "2026-05-25")


if __name__ == "__main__":
    unittest.main()
