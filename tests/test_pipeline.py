"""Tests for the pipeline's multi-page collection loop."""
from __future__ import annotations

from copy import deepcopy
import json
import os
import stat
import tempfile
import types
import unittest
from datetime import datetime
from unittest import mock

from src import manifest, render, store
import src.pipeline as testee
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
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)):
            res = testee._collect_source({"name": "Fake", "listing_url": "p1"}, mod, "p1", state, "TS")
        self.assertEqual(res.status, "OK")
        self.assertEqual(res.n_pages, 2)
        self.assertEqual(res.n_cards, 3)  # b deduped across pages
        self.assertEqual(res.n_new, 3)
        self.assertEqual(len(state["listings"]), 3)

    def test_stops_on_empty_page(self):
        """A first page with zero cards ends as EMPTY_OK without paging further."""
        mod = _module({"p1": ([], "p2"), "p2": ([Listing(url="https://x/9")], None)})
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)):
            res = testee._collect_source({"name": "F", "listing_url": "p1"}, mod, "p1", store.empty_state(), "TS")
        self.assertEqual(res.status, "EMPTY_OK")
        self.assertEqual(res.n_pages, 1)

    def test_first_page_fetch_error(self):
        """A first-page fetch error yields FETCH_ERROR and no paging."""
        def boom(url, **kwargs):
            raise FetchError("nope")
        with mock.patch.object(testee, "fetch", side_effect=boom):
            res = testee._collect_source({"name": "F", "listing_url": "p1"}, _module({}), "p1", store.empty_state(), "TS")
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
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)):
            res = testee._collect_source({"name": "F", "listing_url": "p1"}, mod, "p1", state, "TS")
        self.assertEqual(res.status, "OK")
        self.assertIn("detail fetch/parse failure", res.error or "")
        self.assertIn("https://x/1", state["listings"])

    def test_new_card_records_source_and_parsed_shelter(self):
        """A new card keeps its config source separate from its parsed shelter."""
        mod = types.SimpleNamespace(
            SOURCE_KIND="fake",
            parse_list=lambda body: [Listing(url="https://x/1")] if body == "p1" else [],
            next_page_url=lambda body, current: None,
            parse_detail=lambda body, listing: setattr(listing, "shelter", "Real Shelter Inc") or listing,
        )
        state = store.empty_state()
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)):
            testee._collect_source(
                {"name": "Some Aggregator Search", "listing_url": "p1"}, mod, "p1", state, "TS")
        entry = state["listings"]["https://x/1"]
        self.assertEqual(entry["source"], "Some Aggregator Search")
        self.assertEqual(entry["shelter"], "Real Shelter Inc")

    def test_max_pages_cap(self):
        """An endless pager stops at MAX_PAGES and notes the cap."""
        mod = types.SimpleNamespace(
            SOURCE_KIND="fake",
            parse_list=lambda body: [Listing(url="https://x/" + str(len(body)))],
            next_page_url=lambda body, current: body + "x",
        )
        with mock.patch.object(testee, "MAX_PAGES", 3), \
             mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)):
            res = testee._collect_source({"name": "F", "listing_url": "p"}, mod, "p", store.empty_state(), "TS")
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
        """A successful detail recheck refreshes status and confirms the dog is live."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry("https://x/1")

        def parse_detail(body, listing):
            listing.status = "on-hold"
            return listing

        mod = types.SimpleNamespace(parse_detail=parse_detail)
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)), \
             mock.patch.object(testee.registry, "by_source_kind", return_value=mod):
            flagged = testee._recheck_qualified_details(state, "TS")
        self.assertEqual(flagged, [])
        self.assertEqual(state["listings"]["https://x/1"]["status"], "on-hold")
        # A confirmed detail recheck counts as a sighting, so last_seen advances.
        self.assertEqual(state["listings"]["https://x/1"]["last_seen"], "TS")

    def test_recheck_backfills_parsed_shelter(self):
        """A successful recheck copies the parser's real shelter onto the entry."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry("https://x/1", shelter=None)

        def parse_detail(body, listing):
            listing.shelter = "RSPCA Illawarra Shelter"
            return listing

        mod = types.SimpleNamespace(parse_detail=parse_detail)
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)), \
             mock.patch.object(testee.registry, "by_source_kind", return_value=mod):
            testee._recheck_qualified_details(state, "TS")
        self.assertEqual(state["listings"]["https://x/1"]["shelter"], "RSPCA Illawarra Shelter")

    def test_confirming_fine_clears_a_stale_recheck_flag(self):
        """A live recheck clears a stale maybe-adopted flag and its reason."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry(
            "https://x/1", recheck="maybe_adopted", recheck_reason="http_gone")

        def parse_detail(body, listing):
            listing.status = "on-hold"
            return listing

        mod = types.SimpleNamespace(parse_detail=parse_detail)
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)), \
             mock.patch.object(testee.registry, "by_source_kind", return_value=mod):
            flagged = testee._recheck_qualified_details(state, "TS")
        self.assertEqual(flagged, [])
        self.assertIsNone(state["listings"]["https://x/1"]["recheck"])
        self.assertIsNone(state["listings"]["https://x/1"]["recheck_reason"])
        self.assertEqual(state["listings"]["https://x/1"]["status"], "on-hold")

    def test_adopted_detail_page_flags_maybe_adopted(self):
        """A detail page now marked adopted is flagged, not left displayed as-is."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry("https://x/1")

        def parse_detail(body, listing):
            listing.status = "adopted"
            return listing

        mod = types.SimpleNamespace(parse_detail=parse_detail)
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)), \
             mock.patch.object(testee.registry, "by_source_kind", return_value=mod):
            flagged = testee._recheck_qualified_details(state, "TS")
        self.assertEqual(len(flagged), 1)
        self.assertEqual(state["listings"]["https://x/1"]["recheck"], "maybe_adopted")
        self.assertEqual(state["listings"]["https://x/1"]["recheck_reason"], "status_adopted")
        self.assertEqual(state["listings"]["https://x/1"]["status"], "adopted")
        # A flagged (adopted) dog is not a sighting; last_seen is left untouched.
        self.assertEqual(state["listings"]["https://x/1"]["last_seen"], "20260101-000000")

    def test_dead_detail_url_flags_http_gone(self):
        """A detail page that now 404s is flagged http_gone for the LLM to confirm."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry("https://x/1")

        def boom(url, **kwargs):
            raise FetchError("404", status=404)

        mod = types.SimpleNamespace(parse_detail=lambda body, listing: listing)
        with mock.patch.object(testee, "fetch", side_effect=boom), \
             mock.patch.object(testee.registry, "by_source_kind", return_value=mod):
            flagged = testee._recheck_qualified_details(state, "TS")
        self.assertEqual(len(flagged), 1)
        self.assertEqual(state["listings"]["https://x/1"]["recheck"], "maybe_adopted")
        self.assertEqual(state["listings"]["https://x/1"]["recheck_reason"], "http_gone")
        # Status is left untouched since no fresh detail was parsed.
        self.assertEqual(state["listings"]["https://x/1"]["status"], "available")
        # A flagged (dead-URL) dog is not a sighting; last_seen is left untouched.
        self.assertEqual(state["listings"]["https://x/1"]["last_seen"], "20260101-000000")

    def test_unparseable_detail_flags_detail_unparseable(self):
        """A detail page that no longer parses is flagged detail_unparseable."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry("https://x/1")

        def bad_detail(body, listing):
            raise ParseError("drift")

        mod = types.SimpleNamespace(parse_detail=bad_detail)
        with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)), \
             mock.patch.object(testee.registry, "by_source_kind", return_value=mod):
            flagged = testee._recheck_qualified_details(state, "TS")
        self.assertEqual(len(flagged), 1)
        self.assertEqual(state["listings"]["https://x/1"]["recheck_reason"], "detail_unparseable")

    def test_transient_fetch_error_does_not_flag_or_clear(self):
        """A transient 403/timeout neither flags a dog nor clears its existing flag."""
        state = store.empty_state()
        clean = self._qualified_entry("https://x/clean")
        already = self._qualified_entry(
            "https://x/flagged", recheck="maybe_adopted", recheck_reason="http_gone")
        state["listings"]["https://x/clean"] = clean
        state["listings"]["https://x/flagged"] = already

        def boom(url, **kwargs):
            raise FetchError("403 forbidden", status=403)

        mod = types.SimpleNamespace(parse_detail=lambda body, listing: listing)
        with mock.patch.object(testee, "fetch", side_effect=boom), \
             mock.patch.object(testee.registry, "by_source_kind", return_value=mod):
            flagged = testee._recheck_qualified_details(state, "TS")
        self.assertEqual(flagged, [])
        self.assertIsNone(clean["recheck"])  # clean dog not newly flagged
        self.assertEqual(already["recheck"], "maybe_adopted")  # existing flag kept
        self.assertEqual(already["recheck_reason"], "http_gone")

    def test_skips_non_qualified_and_removed(self):
        """Rejected and removed entries are never re-fetched."""
        state = store.empty_state()
        state["listings"]["https://x/rejected"] = self._qualified_entry(
            "https://x/rejected", verdict=store.REJECTED)
        state["listings"]["https://x/removed"] = self._qualified_entry(
            "https://x/removed", removed=True)
        with mock.patch.object(testee, "fetch") as fetch_mock:
            flagged = testee._recheck_qualified_details(state, "TS")
        fetch_mock.assert_not_called()
        self.assertEqual(flagged, [])

    def test_skips_source_with_no_registered_parser(self):
        """A browser-discovered listing has no static parser and is skipped."""
        state = store.empty_state()
        state["listings"]["https://x/1"] = self._qualified_entry(
            "https://x/1", source_kind="browser")
        with mock.patch.object(testee, "fetch") as fetch_mock, \
             mock.patch.object(testee.registry, "by_source_kind", return_value=None):
            flagged = testee._recheck_qualified_details(state, "TS")
        fetch_mock.assert_not_called()
        self.assertEqual(flagged, [])


class CollectRecheckIntegrationTest(unittest.TestCase):
    """Regression coverage for the detail-recheck vanish-detection path (which
    replaced flag_disappeared): a dog's card dropping out of its shelter's list
    render (e.g. PetRescue excludes on-hold dogs from search results) must be
    resolved by re-reading the dog's own detail page, not by the coarse "absent
    from the list this run" signal — confirming it if the page still resolves,
    flagging it only if that page is actually gone or adopted."""

    def setUp(self):
        """Silence the inter-fetch sleep so tests run fast."""
        patcher = mock.patch("time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run_collect(self, tmp, list_module, detail_module):
        """Run collect over one fake shelter with the given list/detail modules."""
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
            "last_seen": "20260101-000000",
        }
        store.save_state(state_path, state)
        with mock.patch.object(testee.registry, "resolve",
                               return_value=(list_module, "https://fake/list")), \
             mock.patch.object(testee.registry, "by_source_kind", return_value=detail_module):
            testee.collect(shelters_path, state_path, out_dir)
        return store.load_state(state_path)["listings"]["https://fake/dog/1"]

    def test_card_missing_from_list_but_detail_confirms_not_flagged(self):
        """A live on-hold detail page overrides a missing list card without flagging adoption."""
        list_module = types.SimpleNamespace(
            SOURCE_KIND="fake", parse_list=lambda body: [])  # the card is gone
        detail_module = types.SimpleNamespace(
            parse_detail=lambda body, listing: (setattr(listing, "status", "on-hold"), listing)[1])
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(testee, "fetch", side_effect=lambda u, **k: _fr(u)):
                final = self._run_collect(tmp, list_module, detail_module)
        self.assertIsNone(final["recheck"])
        self.assertEqual(final["status"], "on-hold")

    def test_card_missing_from_list_and_detail_dead_is_flagged(self):
        """A missing list card plus a 404 detail page is flagged as http_gone."""
        list_module = types.SimpleNamespace(
            SOURCE_KIND="fake", parse_list=lambda body: [])  # the card is gone

        def fetch_side_effect(url, **kwargs):
            if url == "https://fake/dog/1":
                raise FetchError("404", status=404)  # detail URL is dead
            return _fr(url)

        detail_module = types.SimpleNamespace(parse_detail=lambda body, listing: listing)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(testee, "fetch", side_effect=fetch_side_effect):
                final = self._run_collect(tmp, list_module, detail_module)
        self.assertEqual(final["recheck"], "maybe_adopted")
        self.assertEqual(final["recheck_reason"], "http_gone")


class BrowserStaleCollectTest(unittest.TestCase):
    """collect must wire flag_stale_browser with a now-minus-BROWSER_STALE_DAYS
    cutoff so a long-unseen qualified browser dog gets re-verified rather than
    silently aging out at the 90-day prune."""

    def setUp(self):
        """Silence the inter-fetch sleep so tests run fast."""
        patcher = mock.patch("time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_stale_browser_flagged_fresh_left_alone(self):
        """A years-old browser dog is flagged stale_browser; one seen today isn't."""
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        with tempfile.TemporaryDirectory() as tmp:
            shelters_path = os.path.join(tmp, "shelters.json")
            state_path = os.path.join(tmp, "state.json")
            out_dir = os.path.join(tmp, "out")
            with open(shelters_path, "w", encoding="utf-8") as f:
                json.dump([], f)  # no static sources; exercise only the flagging tail

            state = store.empty_state()
            for key, last_seen in (("stale", "20250101-000000"), ("fresh", now)):
                state["listings"][key] = {
                    "url": key, "verdict": store.QUALIFIED, "removed": False,
                    "source_kind": "browser", "recheck": None, "last_seen": last_seen,
                }
            store.save_state(state_path, state)

            testee.collect(shelters_path, state_path, out_dir)
            final = store.load_state(state_path)["listings"]
        self.assertEqual(final["stale"]["recheck_reason"], "stale_browser")
        self.assertIsNone(final["fresh"]["recheck"])


class CollectStatsTest(unittest.TestCase):
    def _source(self, status: str, n_new: int = 0) -> manifest.SourceResult:
        """A SourceResult with the given status (and optional new-dog count)."""
        return manifest.SourceResult(
            shelter="S", listing_url="u", status=status, n_new=n_new)

    def test_empty_counted_apart_from_errors(self):
        """EMPTY_OK feeds n_empty, not n_errors — only PARSE/FETCH errors are errors."""
        sources = [
            self._source(manifest.STATUS_OK, n_new=2),
            self._source(manifest.STATUS_EMPTY_OK),
            self._source(manifest.STATUS_EMPTY_OK),
            self._source(manifest.STATUS_PARSE_ERROR),
            self._source(manifest.STATUS_FETCH_ERROR),
            self._source(manifest.STATUS_NEEDS_BROWSER),
        ]
        stats = testee._collect_stats(sources, n_maybe_adopted=1, n_pending=3)
        self.assertEqual(stats["n_new"], 2)
        self.assertEqual(stats["n_empty"], 2)
        self.assertEqual(stats["n_errors"], 2)  # PARSE + FETCH only, not the 2 empties
        self.assertEqual(stats["n_needs_browser"], 1)
        self.assertEqual(stats["n_maybe_adopted"], 1)
        self.assertEqual(stats["n_pending"], 3)


class AtomicIndexPersistenceTest(unittest.TestCase):
    def test_write_failure_keeps_existing_index_and_removes_temp_file(self):
        """A temporary write error leaves the prior index intact for recovery."""
        with tempfile.TemporaryDirectory() as tmp:
            index_path = os.path.join(tmp, "dog-index.md")
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("previous index\n")
            real_fdopen = os.fdopen

            class FailingWriter:
                def __init__(self, fd: int):
                    self._handle = real_fdopen(fd, "w", encoding="utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *unused):
                    self._handle.close()

                def write(self, markdown: str) -> None:
                    raise OSError("write failed")

                def flush(self) -> None:
                    raise AssertionError("write failure must skip flush")

            with mock.patch.object(testee.os, "fdopen", side_effect=lambda fd, *args, **kwargs: FailingWriter(fd)):
                with self.assertRaisesRegex(OSError, "write failed"):
                    testee._save_index(index_path, "new index\n")

            with open(index_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "previous index\n")
            self.assertEqual(os.listdir(tmp), ["dog-index.md"])

    def test_replace_failure_keeps_existing_index_and_removes_temp_file(self):
        """A failed atomic replacement preserves the readable prior index for recovery."""
        with tempfile.TemporaryDirectory() as tmp:
            index_path = os.path.join(tmp, "dog-index.md")
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("previous index\n")

            with mock.patch.object(testee.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    testee._save_index(index_path, "new index\n")

            with open(index_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "previous index\n")
            self.assertEqual(os.listdir(tmp), ["dog-index.md"])

    def test_replacement_preserves_existing_index_mode(self):
        """Atomic replacement retains the deployment's existing index permissions."""
        with tempfile.TemporaryDirectory() as tmp:
            index_path = os.path.join(tmp, "dog-index.md")
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("previous index\n")
            os.chmod(index_path, 0o664)

            testee._save_index(index_path, "new index\n")

            self.assertEqual(stat.S_IMODE(os.stat(index_path).st_mode), 0o664)


class ApplyTest(unittest.TestCase):
    def _write_index(self, path: str) -> str:
        """Create a minimal machine-managed index and return its original bytes."""
        markdown = (
            "# Dogs\n\n"
            "- **Last refreshed:** 2026-01-01\n\n"
            f"{render.BEGIN_MARKER}\n\n_No current candidates._\n\n{render.END_MARKER}\n"
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(markdown)
        return markdown

    def test_render_failure_leaves_state_and_index_unchanged(self):
        """Rendering must succeed before either authoritative output is persisted."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            verdicts_path = os.path.join(tmp, "verdicts.json")
            index_path = os.path.join(tmp, "dog-index.md")
            state = store.empty_state()
            store.upsert_listing(state, Listing(url="https://example.test/dog"), "20260101-000000")
            store.save_state(state_path, state)
            with open(verdicts_path, "w", encoding="utf-8") as handle:
                json.dump([{"url": "https://example.test/dog", "verdict": "qualified"}], handle)
            with open(state_path, "rb") as handle:
                original_state = handle.read()
            original_index = self._write_index(index_path).encode()

            with mock.patch.object(testee.render, "render_index", side_effect=ValueError("bad index")):
                with self.assertRaisesRegex(ValueError, "bad index"):
                    testee.apply(state_path, verdicts_path, index_path)

            with open(state_path, "rb") as handle:
                self.assertEqual(handle.read(), original_state)
            with open(index_path, "rb") as handle:
                self.assertEqual(handle.read(), original_index)

    def test_successful_apply_updates_state_and_index(self):
        """A complete in-memory render commits both independently atomic outputs."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            verdicts_path = os.path.join(tmp, "verdicts.json")
            index_path = os.path.join(tmp, "dog-index.md")
            store.save_state(state_path, store.empty_state())
            with open(verdicts_path, "w", encoding="utf-8") as handle:
                json.dump([{"url": "https://example.test/dog", "verdict": "qualified"}], handle)
            self._write_index(index_path)

            self.assertEqual(testee.apply(state_path, verdicts_path, index_path), 1)

            entry = store.load_state(state_path)["listings"]["https://example.test/dog"]
            self.assertEqual(entry["verdict"], store.QUALIFIED)
            with open(index_path, encoding="utf-8") as handle:
                self.assertIn("https://example.test/dog", handle.read())

    def test_deferred_verdict_leaves_persisted_recheck_unchanged(self):
        """The full apply path retains an inconclusive recheck exactly for retry."""
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            verdicts_path = os.path.join(tmp, "verdicts.json")
            index_path = os.path.join(tmp, "dog-index.md")
            state = store.empty_state()
            store.upsert_listing(state, Listing(url="https://example.test/recheck", name="Fido"), "20260101-000000")
            entry = state["listings"]["https://example.test/recheck"]
            entry.update({
                "verdict": store.QUALIFIED,
                "summary": "Keep this summary.",
                "tags": ["verify coat/breed"],
                "recheck": "maybe_adopted",
                "recheck_reason": "stale_browser",
            })
            expected_entry = deepcopy(entry)
            store.save_state(state_path, state)
            with open(verdicts_path, "w", encoding="utf-8") as handle:
                json.dump([{"url": entry["url"], "verdict": store.DEFERRED}], handle)
            self._write_index(index_path)

            testee.apply(state_path, verdicts_path, index_path)

            self.assertEqual(
                store.load_state(state_path)["listings"]["https://example.test/recheck"],
                expected_entry,
            )


if __name__ == "__main__":
    unittest.main()
