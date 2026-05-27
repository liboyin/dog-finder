"""Tests for the state store: upsert, dedup, disappearance flagging, verdicts, seed."""
from __future__ import annotations

import os
import tempfile
import unittest

from src import store
from src.parsers.petrescue import Listing

TS1 = "20260525-100000"
TS2 = "20260526-100000"


def _listing(url: str, **kwargs) -> Listing:
    """Build a Listing for tests."""
    return Listing(url=url, **kwargs)


class UpsertTest(unittest.TestCase):
    def test_new_then_existing(self):
        """First upsert is new (pending); a second updates last_seen and is not new."""
        state = store.empty_state()
        self.assertTrue(store.upsert_listing(state, _listing("https://x/listings/1", name="A"), TS1))
        self.assertFalse(store.upsert_listing(state, _listing("https://x/listings/1", name="A", status="on-hold"), TS2))
        entry = state["listings"]["https://x/listings/1"]
        self.assertEqual(entry["verdict"], store.PENDING)
        self.assertEqual(entry["first_seen"], TS1)
        self.assertEqual(entry["last_seen"], TS2)
        self.assertEqual(entry["status"], "on-hold")


class SaveStateTest(unittest.TestCase):
    def test_save_then_load_round_trips(self):
        """save_state writes a file that load_state reads back identically."""
        state = store.empty_state()
        store.upsert_listing(state, _listing("https://x/listings/1", name="A"), TS1)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            store.save_state(path, state)
            self.assertEqual(store.load_state(path), state)
            self.assertEqual([f for f in os.listdir(tmp) if f != "state.json"], [])


class PendingAndDisappearTest(unittest.TestCase):
    def test_pending_includes_pending_and_rechecks(self):
        """pending_listings returns pending verdicts and re-check-flagged entries."""
        state = store.empty_state()
        store.upsert_listing(state, _listing("https://x/listings/1"), TS1)
        state["listings"]["https://x/listings/2"] = {
            "url": "https://x/listings/2", "verdict": store.QUALIFIED, "removed": False,
            "source_kind": "petrescue", "recheck": "maybe_adopted",
        }
        urls = {e["url"] for e in store.pending_listings(state)}
        self.assertEqual(urls, {"https://x/listings/1", "https://x/listings/2"})

    def test_flag_disappeared(self):
        """A qualified dog absent from its successfully-fetched shelter is flagged."""
        state = store.empty_state()
        state["listings"]["https://x/listings/9"] = {
            "url": "https://x/listings/9", "verdict": store.QUALIFIED, "removed": False,
            "source_kind": "petrescue", "recheck": None, "shelter": "Shelter A",
        }
        flagged = store.flag_disappeared(state, present=set(), ts=TS2, fetched_shelters={"Shelter A"})
        self.assertEqual(len(flagged), 1)
        self.assertEqual(state["listings"]["https://x/listings/9"]["recheck"], "maybe_adopted")

    def test_disappeared_not_flagged_when_shelter_unfetched(self):
        """A dog whose shelter failed/wasn't scanned this run is not flagged."""
        state = store.empty_state()
        state["listings"]["https://x/listings/9"] = {
            "url": "https://x/listings/9", "verdict": store.QUALIFIED, "removed": False,
            "source_kind": "petrescue", "recheck": None, "shelter": "Shelter A",
        }
        flagged = store.flag_disappeared(state, present=set(), ts=TS2, fetched_shelters={"Shelter B"})
        self.assertEqual(flagged, [])
        self.assertIsNone(state["listings"]["https://x/listings/9"]["recheck"])


class PruneStaleTest(unittest.TestCase):
    def test_prunes_only_entries_unseen_before_cutoff(self):
        """Entries last seen before the cutoff are removed; newer ones are kept."""
        state = store.empty_state()
        state["listings"]["https://x/old"] = {"url": "https://x/old", "last_seen": "20260101-000000"}
        state["listings"]["https://x/new"] = {"url": "https://x/new", "last_seen": "20260401-000000"}
        removed = store.prune_stale(state, cutoff="20260301-000000")
        self.assertEqual([e["url"] for e in removed], ["https://x/old"])
        self.assertIn("https://x/new", state["listings"])
        self.assertNotIn("https://x/old", state["listings"])

    def test_keeps_entries_without_last_seen(self):
        """An entry missing last_seen is never pruned (treated as unknown, kept)."""
        state = store.empty_state()
        state["listings"]["https://x/y"] = {"url": "https://x/y"}
        self.assertEqual(store.prune_stale(state, cutoff="20990101-000000"), [])
        self.assertIn("https://x/y", state["listings"])


class ApplyVerdictsTest(unittest.TestCase):
    def test_sets_verdict_and_creates_browser_entry(self):
        """Verdicts update existing entries and create browser-found ones."""
        state = store.empty_state()
        store.upsert_listing(state, _listing("https://x/listings/1"), TS1)
        store.apply_verdicts(state, [
            {"url": "https://x/listings/1", "verdict": "qualified", "summary": "Good dog.", "tags": ["t"]},
            {"url": "https://site/fido", "verdict": "qualified", "name": "Fido", "breed": "Maltese", "source_kind": "browser"},
        ], TS2)
        first = state["listings"]["https://x/listings/1"]
        self.assertEqual(first["verdict"], store.QUALIFIED)
        self.assertEqual(first["summary"], "Good dog.")
        self.assertIsNone(first["recheck"])
        self.assertIn("https://site/fido", state["listings"])
        self.assertEqual(state["listings"]["https://site/fido"]["name"], "Fido")

    def test_removed_flag(self):
        """A verdict with removed=True hides the listing from render."""
        state = store.empty_state()
        store.upsert_listing(state, _listing("https://x/listings/1"), TS1)
        store.apply_verdicts(state, [{"url": "https://x/listings/1", "verdict": "qualified", "removed": True}], TS2)
        self.assertEqual(store.qualified_for_render(state), [])


if __name__ == "__main__":
    unittest.main()
