"""Tests for the state store: upsert, dedup, disappearance flagging, verdicts, seed."""
from __future__ import annotations

from copy import deepcopy
import os
import tempfile
import unittest

import src.store as testee
from src.parsers.petrescue import Listing

TS1 = "20260525-100000"
TS2 = "20260526-100000"


def _listing(url: str, **kwargs) -> Listing:
    """Build a Listing for tests."""
    return Listing(url=url, **kwargs)


class UpsertTest(unittest.TestCase):
    def test_new_then_existing(self):
        """First upsert is new (pending); a second updates last_seen and is not new."""
        state = testee.empty_state()
        self.assertTrue(testee.upsert_listing(state, _listing("https://x/listings/1", name="A"), TS1))
        self.assertFalse(testee.upsert_listing(state, _listing("https://x/listings/1", name="A", status="on-hold"), TS2))
        entry = state["listings"]["https://x/listings/1"]
        self.assertEqual(entry["verdict"], testee.PENDING)
        self.assertEqual(entry["first_seen"], TS1)
        self.assertEqual(entry["last_seen"], TS2)
        self.assertEqual(entry["status"], "on-hold")

    def test_records_source_apart_from_shelter(self):
        """A new entry keeps the finding source separate from the real shelter."""
        state = testee.empty_state()
        testee.upsert_listing(
            state, _listing("https://x/listings/1", shelter="RSPCA Illawarra Shelter"),
            TS1, "petrescue", "PetRescue NSW poodle search (aggregator)")
        entry = state["listings"]["https://x/listings/1"]
        self.assertEqual(entry["shelter"], "RSPCA Illawarra Shelter")
        self.assertEqual(entry["source"], "PetRescue NSW poodle search (aggregator)")


class SaveStateTest(unittest.TestCase):
    def test_save_then_load_round_trips(self):
        """save_state writes a file that load_state reads back identically."""
        state = testee.empty_state()
        testee.upsert_listing(state, _listing("https://x/listings/1", name="A"), TS1)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            testee.save_state(path, state)
            self.assertEqual(testee.load_state(path), state)
            self.assertEqual([f for f in os.listdir(tmp) if f != "state.json"], [])


class FlagStaleBrowserTest(unittest.TestCase):
    CUTOFF = "20260301-000000"

    def _browser_entry(self, url: str, **overrides) -> dict:
        """A qualified browser-sourced entry, stale (last_seen before cutoff) by default."""
        entry = {
            "url": url, "verdict": testee.QUALIFIED, "removed": False,
            "source_kind": "browser", "recheck": None, "last_seen": "20260101-000000",
        }
        entry.update(overrides)
        return entry

    def test_flags_stale_qualified_browser_dog(self):
        """A qualified browser dog unseen since the cutoff is flagged stale_browser."""
        state = testee.empty_state()
        state["listings"]["u"] = self._browser_entry("u")
        flagged = testee.flag_stale_browser(state, self.CUTOFF)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(state["listings"]["u"]["recheck"], "maybe_adopted")
        self.assertEqual(state["listings"]["u"]["recheck_reason"], "stale_browser")

    def test_fresh_browser_dog_not_flagged(self):
        """A browser dog seen after the cutoff is left alone — no false flag."""
        state = testee.empty_state()
        state["listings"]["u"] = self._browser_entry("u", last_seen="20260401-000000")
        self.assertEqual(testee.flag_stale_browser(state, self.CUTOFF), [])
        self.assertIsNone(state["listings"]["u"]["recheck"])

    def test_cutoff_boundary_is_exclusive(self):
        """A dog last seen exactly at the cutoff is not yet stale (strict <)."""
        state = testee.empty_state()
        state["listings"]["u"] = self._browser_entry("u", last_seen=self.CUTOFF)
        self.assertEqual(testee.flag_stale_browser(state, self.CUTOFF), [])

    def test_non_browser_source_not_flagged(self):
        """A stale static-source dog is the detail recheck's job, not this one's."""
        state = testee.empty_state()
        state["listings"]["u"] = self._browser_entry("u", source_kind="petrescue")
        self.assertEqual(testee.flag_stale_browser(state, self.CUTOFF), [])

    def test_non_qualified_or_removed_not_flagged(self):
        """Only qualified, non-removed dogs are shown in the index and worth re-checking."""
        state = testee.empty_state()
        state["listings"]["rej"] = self._browser_entry("rej", verdict=testee.REJECTED)
        state["listings"]["rm"] = self._browser_entry("rm", removed=True)
        self.assertEqual(testee.flag_stale_browser(state, self.CUTOFF), [])

    def test_already_flagged_not_reflagged(self):
        """An existing recheck flag is preserved rather than overwritten stale_browser."""
        state = testee.empty_state()
        state["listings"]["u"] = self._browser_entry(
            "u", recheck="maybe_adopted", recheck_reason="http_gone")
        self.assertEqual(testee.flag_stale_browser(state, self.CUTOFF), [])
        self.assertEqual(state["listings"]["u"]["recheck_reason"], "http_gone")


class PruneStaleTest(unittest.TestCase):
    def test_prunes_only_entries_unseen_before_cutoff(self):
        """Entries last seen before the cutoff are removed; newer ones are kept."""
        state = testee.empty_state()
        state["listings"]["https://x/old"] = {"url": "https://x/old", "last_seen": "20260101-000000"}
        state["listings"]["https://x/new"] = {"url": "https://x/new", "last_seen": "20260401-000000"}
        removed = testee.prune_stale(state, cutoff="20260301-000000")
        self.assertEqual([e["url"] for e in removed], ["https://x/old"])
        self.assertIn("https://x/new", state["listings"])
        self.assertNotIn("https://x/old", state["listings"])

    def test_keeps_entries_without_last_seen(self):
        """An entry missing last_seen is never pruned (treated as unknown, kept)."""
        state = testee.empty_state()
        state["listings"]["https://x/y"] = {"url": "https://x/y"}
        self.assertEqual(testee.prune_stale(state, cutoff="20990101-000000"), [])
        self.assertIn("https://x/y", state["listings"])


class MigrateSourceFieldTest(unittest.TestCase):
    AGGREGATORS = {"PetRescue NSW poodle search (aggregator)"}

    def _state(self):
        """State with one aggregator-found and one real-shelter entry, pre-split."""
        state = testee.empty_state()
        state["listings"]["agg"] = {
            "url": "agg", "shelter": "PetRescue NSW poodle search (aggregator)"}
        state["listings"]["real"] = {"url": "real", "shelter": "RSPCA Illawarra Shelter"}
        return state

    def test_aggregator_shelter_moved_to_source_and_nulled(self):
        """An aggregator name moves to source and is cleared from shelter."""
        state = self._state()
        testee.migrate_source_field(state, self.AGGREGATORS)
        agg = state["listings"]["agg"]
        self.assertEqual(agg["source"], "PetRescue NSW poodle search (aggregator)")
        self.assertIsNone(agg["shelter"])

    def test_real_shelter_kept_in_both_fields(self):
        """A real shelter name stays in shelter and is copied to source."""
        state = self._state()
        testee.migrate_source_field(state, self.AGGREGATORS)
        real = state["listings"]["real"]
        self.assertEqual(real["shelter"], "RSPCA Illawarra Shelter")
        self.assertEqual(real["source"], "RSPCA Illawarra Shelter")

    def test_idempotent(self):
        """Running the migration twice yields the same state as running it once."""
        once = self._state()
        testee.migrate_source_field(once, self.AGGREGATORS)
        twice = self._state()
        testee.migrate_source_field(twice, self.AGGREGATORS)
        testee.migrate_source_field(twice, self.AGGREGATORS)
        self.assertEqual(once, twice)


class PendingTest(unittest.TestCase):
    def test_pending_includes_pending_and_rechecks(self):
        """pending_listings returns pending verdicts and re-check-flagged entries."""
        state = testee.empty_state()
        testee.upsert_listing(state, _listing("https://x/listings/1"), TS1)
        state["listings"]["https://x/listings/2"] = {
            "url": "https://x/listings/2", "verdict": testee.QUALIFIED, "removed": False,
            "source_kind": "petrescue", "recheck": "maybe_adopted",
        }
        urls = {e["url"] for e in testee.pending_listings(state)}
        self.assertEqual(urls, {"https://x/listings/1", "https://x/listings/2"})


class ValidVerdictUrlTest(unittest.TestCase):
    def test_rejects_raw_url_variants_forbidden_at_response_validation(self):
        """The shared validator keeps unsafe response URLs out of state and the index."""
        for url in (
            " https://example.test/dog",
            "https://example.test/dog ",
            "HTTPS://example.test/dog",
            "javascript:alert(1)",
            "https://example.test/[click](https://evil.test)",
        ):
            with self.subTest(url=url):
                self.assertFalse(testee.valid_verdict_url(url))


class ApplyVerdictsTest(unittest.TestCase):
    def test_sets_verdict_and_creates_browser_entry(self):
        """Verdicts update existing entries and create browser-found ones."""
        state = testee.empty_state()
        testee.upsert_listing(state, _listing("https://x/listings/1"), TS1)
        # A prior recheck flag+reason must be cleared once the LLM judges it.
        state["listings"]["https://x/listings/1"]["recheck"] = "maybe_adopted"
        state["listings"]["https://x/listings/1"]["recheck_reason"] = "http_gone"
        testee.apply_verdicts(state, [
            {"url": "https://x/listings/1", "verdict": "qualified", "summary": "Good dog.", "tags": ["t"]},
            {"url": "https://site/fido", "verdict": "qualified", "name": "Fido", "breed": "Maltese",
             "shelter": "Fido Rescue Inc", "source_kind": "browser", "source": "DoodleAid"},
        ], TS2)
        first = state["listings"]["https://x/listings/1"]
        self.assertEqual(first["verdict"], testee.QUALIFIED)
        self.assertEqual(first["summary"], "Good dog.")
        self.assertIsNone(first["recheck"])
        self.assertIsNone(first["recheck_reason"])
        fido = state["listings"]["https://site/fido"]
        self.assertEqual(fido["name"], "Fido")
        self.assertEqual(fido["shelter"], "Fido Rescue Inc")
        self.assertEqual(fido["source"], "DoodleAid")

    def test_deferred_recheck_leaves_existing_entry_unchanged(self):
        """An inconclusive browser recheck must preserve every field for the next retry."""
        state = testee.empty_state()
        testee.upsert_listing(state, _listing("https://x/listings/1", name="Fido"), TS1)
        entry = state["listings"]["https://x/listings/1"]
        entry.update({
            "verdict": testee.QUALIFIED,
            "last_seen": TS1,
            "summary": "Keep this summary.",
            "tags": ["verify coat/breed"],
            "removed": False,
            "recheck": "maybe_adopted",
            "recheck_reason": "stale_browser",
        })
        before = deepcopy(entry)

        testee.apply_verdicts(state, [
            {
                "url": "https://x/listings/1",
                "verdict": testee.DEFERRED,
                "removed": False,
                "summary": None,
                "tags": [],
            }
        ], TS2)

        self.assertEqual(state["listings"]["https://x/listings/1"], before)

    def test_new_entries_always_store_browser_source_kind(self):
        """Defense-in-depth merge tracking does not trust absent or null discovery provenance."""
        for verdict in (
            {"url": "https://site/missing", "verdict": "qualified"},
            {"url": "https://site/null", "verdict": "qualified", "source_kind": None},
        ):
            with self.subTest(verdict=verdict):
                state = testee.empty_state()
                testee.apply_verdicts(state, [verdict], TS2)
                self.assertEqual(state["listings"][verdict["url"]]["source_kind"], "browser")

    def test_removed_flag(self):
        """A verdict with removed=True hides the listing from render."""
        state = testee.empty_state()
        testee.upsert_listing(state, _listing("https://x/listings/1"), TS1)
        testee.apply_verdicts(state, [{"url": "https://x/listings/1", "verdict": "qualified", "removed": True}], TS2)
        self.assertEqual(testee.qualified_for_render(state), [])

    def test_ignores_verdict_with_unsafe_url(self):
        """A verdict whose url isn't a clean http(s) URL never creates an entry."""
        state = testee.empty_state()
        testee.apply_verdicts(state, [
            {"url": "javascript:alert(1)", "verdict": "qualified", "name": "X"},
            {"url": "https://ok/1 <script>", "verdict": "qualified"},
        ], TS2)
        self.assertEqual(state["listings"], {})

    def test_rejects_verdict_url_with_link_brackets(self):
        """A bracketed Markdown-link verdict URL is rejected before index rendering."""
        state = testee.empty_state()
        testee.apply_verdicts(state, [
            {"url": "https://x/[click](http://evil)", "verdict": "qualified"},
        ], TS2)
        self.assertEqual(state["listings"], {})

    def test_caps_overlong_string_fields(self):
        """A stored string field longer than the cap is truncated (bounds state size)."""
        state = testee.empty_state()
        testee.apply_verdicts(state, [
            {"url": "https://x/1", "verdict": "qualified", "summary": "z" * 500},
        ], TS2)
        self.assertEqual(len(state["listings"]["https://x/1"]["summary"]), testee.MAX_FIELD_LEN)

    def test_new_entry_missing_verdict_defaults_pending(self):
        """A new URL with no verdict becomes pending (visible next run), not an orphan."""
        state = testee.empty_state()
        testee.apply_verdicts(state, [{"url": "https://x/1", "name": "Newbie"}], TS2)
        self.assertEqual(state["listings"]["https://x/1"]["verdict"], testee.PENDING)

    def test_two_fragment_dogs_on_one_page_coexist(self):
        """Two dogs sharing a page URL but distinct #slug fragments both persist, neither overwriting the other."""
        state = testee.empty_state()
        page = "https://www.paws.com.au/FosterCare/FosterCareDogs.html"
        testee.apply_verdicts(state, [
            {"url": page + "#bindi", "verdict": "qualified", "name": "Bindi", "source_kind": "browser"},
            {"url": page + "#rex", "verdict": "qualified", "name": "Rex", "source_kind": "browser"},
        ], TS2)
        self.assertEqual(state["listings"][page + "#bindi"]["name"], "Bindi")
        self.assertEqual(state["listings"][page + "#rex"]["name"], "Rex")
        self.assertEqual(len(testee.qualified_for_render(state)), 2)


if __name__ == "__main__":
    unittest.main()
