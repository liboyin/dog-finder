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

    def test_shelter_falls_back_to_source_then_unknown(self):
        """The Shelter line shows the real shelter, else the finding source, else 'unknown'."""
        self.assertIn("Real Shelter (", render.render_block(
            dict(ENTRY, shelter="Real Shelter", source="agg search")))
        self.assertIn("agg search (", render.render_block(
            dict(ENTRY, shelter=None, source="agg search")))
        self.assertIn("unknown (", render.render_block(
            dict(ENTRY, shelter=None, source=None)))


class SanitizeTest(unittest.TestCase):
    def test_hostile_field_renders_inert(self):
        """A markdown-link/HTML injection in a field is neutralized, not rendered live."""
        block = render.render_block(dict(ENTRY, name="](http://evil) <script>x</script>"))
        self.assertNotIn("<script>", block)
        self.assertIn(r"\]", block)  # link bracket escaped so it can't form a link

    def test_legitimate_punctuation_preserved(self):
        """Parentheses in locations and $ in fees render unchanged."""
        block = render.render_block(dict(ENTRY, location="Sydney (Inner West), NSW", fee="$300"))
        self.assertIn("Sydney (Inner West), NSW", block)
        self.assertIn("$300", block)

    def test_tags_are_sanitized(self):
        """Tag text is stripped of HTML like any other interpolated field."""
        block = render.render_block(dict(ENTRY, tags=["<b>verify</b> drive time"]))
        self.assertNotIn("<b>", block)
        self.assertIn("verify", block)

    def test_sanitize_escapes_backslash_before_brackets(self):
        """A leading backslash is doubled so it can't neutralize the bracket escape."""
        # r"\[" (backslash + bracket) must become r"\\\[" (escaped backslash + escaped bracket).
        self.assertEqual(render._sanitize("\\["), "\\\\\\[")

    def test_non_string_field_does_not_crash(self):
        """A numeric field (e.g. an LLM-emitted fee) is coerced, not crashed on."""
        block = render.render_block(dict(ENTRY, fee=300))
        self.assertIn("300", block)


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


def _index_with(*urls: str) -> str:
    """Build an index whose managed region lists the given dog URLs."""
    entries = [dict(ENTRY, url=u, name=f"Dog{i}") for i, u in enumerate(urls)]
    return render.render_index(INDEX, entries, "2026-05-25")


class IndexDogUrlsTest(unittest.TestCase):
    def test_extracts_only_region_urls(self):
        """index_dog_urls returns the dog URLs from the managed region."""
        md = _index_with("https://x/1", "https://x/2")
        self.assertEqual(render.index_dog_urls(md), {"https://x/1", "https://x/2"})

    def test_empty_region(self):
        """An index with no dogs yields an empty set."""
        self.assertEqual(render.index_dog_urls(render.render_index(INDEX, [], "2026-05-25")), set())


class DroppedDogUrlsTest(unittest.TestCase):
    def test_detects_only_drops(self):
        """dropped_dog_urls reports removed dogs and ignores additions."""
        old = _index_with("https://x/1", "https://x/2")
        new = _index_with("https://x/2", "https://x/3")  # 1 dropped, 3 added
        self.assertEqual(render.dropped_dog_urls(old, new), {"https://x/1"})

    def test_pure_additions_drop_nothing(self):
        """Adding dogs without removing any yields no dropped URLs."""
        old = _index_with("https://x/1")
        new = _index_with("https://x/1", "https://x/2")
        self.assertEqual(render.dropped_dog_urls(old, new), set())


class AddedDogUrlsTest(unittest.TestCase):
    def test_detects_only_additions(self):
        """added_dog_urls reports new dogs and ignores drops."""
        old = _index_with("https://x/1", "https://x/2")
        new = _index_with("https://x/2", "https://x/3")  # 3 added, 1 dropped
        self.assertEqual(render.added_dog_urls(old, new), {"https://x/3"})

    def test_unchanged_set_adds_nothing(self):
        """The same set of dogs (in any order) yields no additions."""
        old = _index_with("https://x/1", "https://x/2")
        new = _index_with("https://x/2", "https://x/1")
        self.assertEqual(render.added_dog_urls(old, new), set())


if __name__ == "__main__":
    unittest.main()
