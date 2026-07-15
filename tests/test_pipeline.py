"""Tests for the pipeline's multi-page collection loop."""
from __future__ import annotations

import json
import os
import tempfile
import types
import unittest
from unittest import mock

from src import pipeline, store
from src.fetch import FetchError, FetchResult
from src.parsers.base import Listing, ParseError


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

    def test_detail_error_recorded_but_status_ok(self):
        """A failing detail fetch is noted in error, status stays OK, card still upserted."""
        def bad_detail(body, listing):
            raise ParseError("bad detail")
        mod = types.SimpleNamespace(
            SOURCE_KIND="fake",
            parse_list=lambda body: [Listing(url="https://x/1")] if body == "p1" else [],
            next_page_url=lambda body, current: None,
            parse_detail=bad_detail,
        )
        state = store.empty_state()
        with mock.patch.object(pipeline, "fetch", side_effect=lambda u, **k: _fr(u)):
            res = pipeline._collect_source({"name": "F", "listing_url": "p1"}, mod, "p1", state, set(), "TS")
        self.assertEqual(res.status, "OK")
        self.assertIn("detail fetch/parse failure", res.error or "")
        self.assertIn("https://x/1", state["listings"])

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


class RecheckQualifiedDetailsTest(unittest.TestCase):
    def setUp(self):
        """Silence the inter-fetch sleep so tests run fast."""
        patcher = mock.patch("time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _qualified_entry(self, url: str, **overrides) -> dict:
        """A minimal qualified, non-removed state entry."""
        entry = {
            "url": url, "verdict": store.QUALIFIED, "removed": False,
            "source_kind": "fake", "recheck": None, "status": "available",
            "last_seen": "20260101-000000",
        }
        entry.update(overrides)
        return entry

    def test_status_refreshed_and_confirmed(self):
        """A qualified dog's detail page is re-fetched, status updated, and its
        URL reported back as confirmed still live."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry("https://x/1")

        def parse_detail(body, listing):
            listing.status = "on-hold"
            return listing

        mod = types.SimpleNamespace(parse_detail=parse_detail)
        with mock.patch.object(pipeline, "fetch", side_effect=lambda u, **k: _fr(u)), \
             mock.patch.object(pipeline.registry, "by_source_kind", return_value=mod):
            confirmed, flagged = pipeline._recheck_qualified_details(state, "TS")
        self.assertEqual(flagged, [])
        self.assertEqual(confirmed, {"https://x/1"})
        self.assertEqual(state["listings"]["https://x/1"]["status"], "on-hold")
        # A confirmed detail recheck counts as a sighting, so last_seen advances.
        self.assertEqual(state["listings"]["https://x/1"]["last_seen"], "TS")

    def test_confirming_fine_clears_a_stale_recheck_flag(self):
        """A dog flagged maybe_adopted (e.g. its card dropped from a list
        render) whose own detail page still resolves as not-adopted has its
        flag cleared and is reported confirmed, not left flagged."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry(
            "https://x/1", recheck="maybe_adopted")

        def parse_detail(body, listing):
            listing.status = "on-hold"
            return listing

        mod = types.SimpleNamespace(parse_detail=parse_detail)
        with mock.patch.object(pipeline, "fetch", side_effect=lambda u, **k: _fr(u)), \
             mock.patch.object(pipeline.registry, "by_source_kind", return_value=mod):
            confirmed, flagged = pipeline._recheck_qualified_details(state, "TS")
        self.assertEqual(flagged, [])
        self.assertEqual(confirmed, {"https://x/1"})
        self.assertIsNone(state["listings"]["https://x/1"]["recheck"])
        self.assertEqual(state["listings"]["https://x/1"]["status"], "on-hold")

    def test_adopted_detail_page_flags_maybe_adopted(self):
        """A detail page now marked adopted is flagged, not left displayed as-is."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry("https://x/1")

        def parse_detail(body, listing):
            listing.status = "adopted"
            return listing

        mod = types.SimpleNamespace(parse_detail=parse_detail)
        with mock.patch.object(pipeline, "fetch", side_effect=lambda u, **k: _fr(u)), \
             mock.patch.object(pipeline.registry, "by_source_kind", return_value=mod):
            confirmed, flagged = pipeline._recheck_qualified_details(state, "TS")
        self.assertEqual(len(flagged), 1)
        self.assertEqual(confirmed, set())
        self.assertEqual(state["listings"]["https://x/1"]["recheck"], "maybe_adopted")
        self.assertEqual(state["listings"]["https://x/1"]["status"], "adopted")
        # A flagged (adopted) dog is not a sighting; last_seen is left untouched.
        self.assertEqual(state["listings"]["https://x/1"]["last_seen"], "20260101-000000")

    def test_dead_detail_url_flags_maybe_adopted(self):
        """A detail page that now 404s is flagged for the LLM to confirm."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry("https://x/1")

        def boom(url, **kwargs):
            raise FetchError("404")

        mod = types.SimpleNamespace(parse_detail=lambda body, listing: listing)
        with mock.patch.object(pipeline, "fetch", side_effect=boom), \
             mock.patch.object(pipeline.registry, "by_source_kind", return_value=mod):
            confirmed, flagged = pipeline._recheck_qualified_details(state, "TS")
        self.assertEqual(len(flagged), 1)
        self.assertEqual(confirmed, set())
        self.assertEqual(state["listings"]["https://x/1"]["recheck"], "maybe_adopted")
        # Status is left untouched since no fresh detail was parsed.
        self.assertEqual(state["listings"]["https://x/1"]["status"], "available")
        # A flagged (dead-URL) dog is not a sighting; last_seen is left untouched.
        self.assertEqual(state["listings"]["https://x/1"]["last_seen"], "20260101-000000")

    def test_skips_non_qualified_and_removed(self):
        """Rejected and removed entries are never re-fetched."""
        state = store.empty_state()
        state["listings"]["https://x/rejected"] = self._qualified_entry(
            "https://x/rejected", verdict=store.REJECTED)
        state["listings"]["https://x/removed"] = self._qualified_entry(
            "https://x/removed", removed=True)
        with mock.patch.object(pipeline, "fetch") as fetch_mock:
            confirmed, flagged = pipeline._recheck_qualified_details(state, "TS")
        fetch_mock.assert_not_called()
        self.assertEqual(confirmed, set())
        self.assertEqual(flagged, [])

    def test_skips_source_with_no_registered_parser(self):
        """A browser-discovered listing has no static parser and is skipped."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry(
            "https://x/1", source_kind="browser")
        with mock.patch.object(pipeline, "fetch") as fetch_mock, \
             mock.patch.object(pipeline.registry, "by_source_kind", return_value=None):
            confirmed, flagged = pipeline._recheck_qualified_details(state, "TS")
        fetch_mock.assert_not_called()
        self.assertEqual(confirmed, set())
        self.assertEqual(flagged, [])


class CollectRecheckIntegrationTest(unittest.TestCase):
    """Regression coverage for the bug where a dog's card dropping out of its
    shelter's list render (e.g. PetRescue excludes on-hold dogs from search
    results) got it flagged maybe_adopted by flag_disappeared before the
    detail-page recheck ever ran, leaving a stale status behind."""

    def setUp(self):
        """Silence the inter-fetch sleep so tests run fast."""
        patcher = mock.patch("time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_card_missing_from_list_but_detail_confirms_not_flagged(self):
        """A qualified dog absent from its shelter's list this run, but whose
        own detail page still resolves as on-hold (not adopted), is NOT
        flagged maybe_adopted and gets its status refreshed."""
        with tempfile.TemporaryDirectory() as tmp:
            shelters_path = os.path.join(tmp, "shelters.json")
            state_path = os.path.join(tmp, "state.json")
            out_dir = os.path.join(tmp, "out")
            with open(shelters_path, "w", encoding="utf-8") as f:
                json.dump([{"name": "Fake Shelter", "listing_url": "https://fake/list"}], f)

            state = store.empty_state()
            state["listings"]["https://fake/dog/1"] = {
                "url": "https://fake/dog/1", "verdict": store.QUALIFIED, "removed": False,
                "source_kind": "fake", "recheck": None, "status": "available",
                "shelter": "Fake Shelter", "first_seen": "20260101-000000",
            }
            store.save_state(state_path, state)

            list_module = types.SimpleNamespace(
                SOURCE_KIND="fake", parse_list=lambda body: [])  # the card is gone
            detail_module = types.SimpleNamespace(
                parse_detail=lambda body, listing: (setattr(listing, "status", "on-hold"), listing)[1])

            with mock.patch.object(pipeline, "fetch", side_effect=lambda u, **k: _fr(u)), \
                 mock.patch.object(pipeline.registry, "resolve",
                                    return_value=(list_module, "https://fake/list")), \
                 mock.patch.object(pipeline.registry, "by_source_kind", return_value=detail_module):
                pipeline.collect(shelters_path, state_path, out_dir)

            final = store.load_state(state_path)["listings"]["https://fake/dog/1"]
        self.assertIsNone(final["recheck"])
        self.assertEqual(final["status"], "on-hold")


if __name__ == "__main__":
    unittest.main()
