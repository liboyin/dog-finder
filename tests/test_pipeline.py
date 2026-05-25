"""Tests for the pipeline's multi-page collection loop."""
from __future__ import annotations

import types
import unittest
from unittest import mock

from src import pipeline, store
from src.fetch import FetchError, FetchResult
from src.parsers.base import Listing


def _fr(url: str) -> FetchResult:
    """A FetchResult whose body is the URL, so a fake parser can branch on it."""
    return FetchResult(url=url, status=200, body=url, bytes=len(url))


def _module(pages: dict) -> types.SimpleNamespace:
    """Build a fake parser module from a {body: (listings, next_url)} map."""
    return types.SimpleNamespace(
        SOURCE_KIND="fake",
        parse_list=lambda body: list(pages[body][0]),
        next_page_url=lambda body, current: pages[body][1],
    )


class PaginationLoopTest(unittest.TestCase):
    def setUp(self):
        """Silence the inter-page sleep so tests run fast."""
        patcher = mock.patch("time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_follows_pages_and_dedups(self):
        """The loop follows next_page_url, merges pages, and dedups by URL."""
        a, b, c = Listing(url="https://x/1"), Listing(url="https://x/2"), Listing(url="https://x/3")
        mod = _module({"p1": ([a, b], "p2"), "p2": ([b, c], None)})
        state = store.empty_state()
        with mock.patch.object(pipeline, "fetch", side_effect=lambda u, **k: _fr(u)):
            res = pipeline._collect_source({"name": "Fake", "listing_url": "p1"}, mod, "p1", state, set(), "TS")
        self.assertEqual(res.status, "OK")
        self.assertEqual(res.n_pages, 2)
        self.assertEqual(res.n_cards, 3)  # b deduped across pages
        self.assertEqual(res.n_new, 3)
        self.assertEqual(len(state["listings"]), 3)

    def test_stops_on_empty_page(self):
        """A first page with zero cards ends as EMPTY_OK without paging further."""
        mod = _module({"p1": ([], "p2"), "p2": ([Listing(url="https://x/9")], None)})
        with mock.patch.object(pipeline, "fetch", side_effect=lambda u, **k: _fr(u)):
            res = pipeline._collect_source({"name": "F", "listing_url": "p1"}, mod, "p1", store.empty_state(), set(), "TS")
        self.assertEqual(res.status, "EMPTY_OK")
        self.assertEqual(res.n_pages, 1)

    def test_first_page_fetch_error(self):
        """A first-page fetch error yields FETCH_ERROR and no paging."""
        def boom(url, **kwargs):
            raise FetchError("nope")
        with mock.patch.object(pipeline, "fetch", side_effect=boom):
            res = pipeline._collect_source({"name": "F", "listing_url": "p1"}, _module({}), "p1", store.empty_state(), set(), "TS")
        self.assertEqual(res.status, "FETCH_ERROR")

    def test_max_pages_cap(self):
        """An endless pager stops at MAX_PAGES and notes the cap."""
        mod = types.SimpleNamespace(
            SOURCE_KIND="fake",
            parse_list=lambda body: [Listing(url="https://x/" + str(len(body)))],
            next_page_url=lambda body, current: body + "x",
        )
        with mock.patch.object(pipeline, "MAX_PAGES", 3), \
             mock.patch.object(pipeline, "fetch", side_effect=lambda u, **k: _fr(u)):
            res = pipeline._collect_source({"name": "F", "listing_url": "p"}, mod, "p", store.empty_state(), set(), "TS")
        self.assertEqual(res.n_pages, 3)
        self.assertIn("MAX_PAGES", res.error or "")


if __name__ == "__main__":
    unittest.main()
