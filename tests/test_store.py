"""Tests for the state store: upsert, dedup, disappearance flagging, verdicts, seed."""
from __future__ import annotations

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
        self.assertTrue(store.upsert_petrescue(state, _listing("https://x/listings/1", name="A"), TS1))
        self.assertFalse(store.upsert_petrescue(state, _listing("https://x/listings/1", name="A", status="on-hold"), TS2))
        entry = state["listings"]["https://x/listings/1"]
        self.assertEqual(entry["verdict"], store.PENDING)
        self.assertEqual(entry["first_seen"], TS1)
        self.assertEqual(entry["last_seen"], TS2)
        self.assertEqual(entry["status"], "on-hold")


class PendingAndDisappearTest(unittest.TestCase):
    def test_pending_includes_pending_and_rechecks(self):
        """pending_listings returns pending verdicts and re-check-flagged entries."""
        state = store.empty_state()
        store.upsert_petrescue(state, _listing("https://x/listings/1"), TS1)
        state["listings"]["https://x/listings/2"] = {
            "url": "https://x/listings/2", "verdict": store.QUALIFIED, "removed": False,
            "source_kind": "petrescue", "recheck": "maybe_adopted",
        }
        urls = {e["url"] for e in store.pending_listings(state)}
        self.assertEqual(urls, {"https://x/listings/1", "https://x/listings/2"})

    def test_flag_disappeared(self):
        """A qualified PetRescue dog absent from this run is flagged maybe_adopted."""
        state = store.empty_state()
        state["listings"]["https://x/listings/9"] = {
            "url": "https://x/listings/9", "verdict": store.QUALIFIED, "removed": False,
            "source_kind": "petrescue", "recheck": None,
        }
        flagged = store.flag_disappeared(state, present=set(), ts=TS2)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(state["listings"]["https://x/listings/9"]["recheck"], "maybe_adopted")


class ApplyVerdictsTest(unittest.TestCase):
    def test_sets_verdict_and_creates_browser_entry(self):
        """Verdicts update existing entries and create browser-found ones."""
        state = store.empty_state()
        store.upsert_petrescue(state, _listing("https://x/listings/1"), TS1)
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
        store.upsert_petrescue(state, _listing("https://x/listings/1"), TS1)
        store.apply_verdicts(state, [{"url": "https://x/listings/1", "verdict": "qualified", "removed": True}], TS2)
        self.assertEqual(store.qualified_for_render(state), [])


class SeedTest(unittest.TestCase):
    INDEX = """- **Last refreshed:** 2026-05-24

## Current candidates

### [NEW 2026-05-24] Kev — Poodle (Toy) x Pug, 10 months, male
- **URL:** https://www.petrescue.com.au/listings/111
- **Shelter:** Wollongong Shelter (Wollongong, NSW)
- **Status:** available · **Fee:** not stated · **Size:** toy
- **date_indexed:** 2026-05-24
- A young toy poodle cross.

## Recently adopted

- https://www.petrescue.com.au/listings/222 — Miso (Mini Poodle, Ramsgate)

## Monitored shelters
"""

    def test_seed_parses_current_and_adopted(self):
        """Seeding captures current candidates faithfully and adopted URLs as removed."""
        state = store.seed_from_index(self.INDEX, TS1)
        kev = state["listings"]["https://www.petrescue.com.au/listings/111"]
        self.assertEqual(kev["breed"], "Poodle (Toy) x Pug")
        self.assertEqual(kev["age"], "10 months")
        self.assertEqual(kev["sex"], "male")
        self.assertEqual(kev["size"], "toy")
        self.assertEqual(kev["shelter"], "Wollongong Shelter")
        self.assertEqual(kev["location"], "Wollongong, NSW")
        self.assertEqual(kev["verdict"], store.QUALIFIED)
        miso = state["listings"]["https://www.petrescue.com.au/listings/222"]
        self.assertTrue(miso["removed"])


if __name__ == "__main__":
    unittest.main()
