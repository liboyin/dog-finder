"""Tests for extracting the human report from a Codex verdict response."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.write_report as testee


class VerdictSchemaTest(unittest.TestCase):
    """Keep the structured-output schema aligned with the verdict contract."""

    def test_deferred_and_non_nullable_source_kind_are_declared(self) -> None:
        """The schema permits deferral but requires lifecycle metadata for every verdict."""
        schema_path = Path(__file__).parents[1] / "config" / "verdicts.schema.json"
        with schema_path.open(encoding="utf-8") as source:
            schema = json.load(source)

        properties = schema["properties"]["verdicts"]["items"]["properties"]
        self.assertIn("deferred", properties["verdict"]["enum"])
        self.assertEqual(properties["source_kind"]["type"], "string")
        self.assertEqual(properties["source_kind"]["minLength"], 1)


class ValidateCoverageTest(unittest.TestCase):
    """Cover the deterministic verdict and browser-lifecycle contract."""

    REPORT = {"report": "Refresh complete."}

    def test_complete_qualified_and_rejected_coverage_succeeds(self) -> None:
        """Every pending dog needs an object even when its judgment is rejection."""
        response = self.REPORT | {
            "verdicts": [
                {"url": "https://example.test/qualified", "verdict": "qualified"},
                {"url": "https://example.test/rejected", "verdict": "rejected"},
            ]
        }
        pending = {
            "pending": [
                {"url": "https://example.test/qualified"},
                {"url": "https://example.test/rejected"},
            ]
        }

        self.assertIsNone(testee.validate_coverage(response, pending))

    def test_deferred_pending_recheck_succeeds(self) -> None:
        """An inconclusive re-check is covered while its state entry remains for retry."""
        response = self.REPORT | {
            "verdicts": [{"url": "https://example.test/recheck", "verdict": "deferred"}]
        }
        pending = {"pending": [{"url": "https://example.test/recheck", "recheck": "maybe_adopted"}]}

        self.assertIsNone(testee.validate_coverage(response, pending))

    def test_deferred_regular_pending_candidate_fails(self) -> None:
        """New candidates cannot evade a qualification decision by being deferred."""
        response = self.REPORT | {
            "verdicts": [{"url": "https://example.test/new", "verdict": "deferred"}]
        }
        pending = {"pending": [{"url": "https://example.test/new"}]}

        self.assertIn("not pending re-checks", testee.validate_coverage(response, pending) or "")

    def test_deferred_browser_discovery_fails(self) -> None:
        """Only existing pending re-checks, never discoveries, may defer judgment."""
        response = self.REPORT | {
            "verdicts": [
                {"url": "https://example.test/pending", "verdict": "qualified"},
                {
                    "url": "https://example.test/discovery",
                    "verdict": "deferred",
                    "source_kind": "browser",
                },
            ]
        }
        pending = {"pending": [{"url": "https://example.test/pending"}]}

        self.assertIn("discoveries defer", testee.validate_coverage(response, pending) or "")

    def test_missing_pending_verdict_fails(self) -> None:
        """A partial judge response cannot silently leave a pending dog unresolved."""
        response = self.REPORT | {
            "verdicts": [{"url": "https://example.test/first", "verdict": "qualified"}]
        }
        pending = {
            "pending": [
                {"url": "https://example.test/first"},
                {"url": "https://example.test/second"},
            ]
        }

        self.assertIn("omits 1 pending", testee.validate_coverage(response, pending) or "")

    def test_duplicate_canonical_verdict_urls_fail(self) -> None:
        """Equivalent URLs must not merge two judgments into one state entry."""
        response = self.REPORT | {
            "verdicts": [
                {"url": "https://EXAMPLE.test/dog/", "verdict": "qualified"},
                {"url": "https://example.test/dog", "verdict": "rejected"},
            ]
        }
        pending = {"pending": [{"url": "https://example.test/dog"}]}

        self.assertIn("duplicates 1", testee.validate_coverage(response, pending) or "")

    def test_raw_url_variants_fail_before_canonical_coverage(self) -> None:
        """Whitespace and scheme case cannot bypass merge's raw-URL safety rule."""
        pending = {"pending": [{"url": "https://example.test/dog"}]}
        for url in (" https://example.test/dog", "https://example.test/dog ", "HTTPS://example.test/dog"):
            with self.subTest(url=url):
                response = self.REPORT | {"verdicts": [{"url": url, "verdict": "qualified"}]}
                self.assertIn("unsafe URL", testee.validate_coverage(response, pending) or "")

    def test_extra_urls_require_browser_source_kind(self) -> None:
        """Discovery URLs need browser provenance so their lifecycle can be tracked."""
        pending = {"pending": [{"url": "https://example.test/pending"}]}
        for source_kind in (None, "", "petrescue"):
            with self.subTest(source_kind=source_kind):
                response = self.REPORT | {
                    "verdicts": [
                        {"url": "https://example.test/pending", "verdict": "qualified"},
                        {
                            "url": "https://example.test/discovery",
                            "verdict": "qualified",
                            "source_kind": source_kind,
                        },
                    ]
                }
                self.assertIn("invalid source_kind", testee.validate_coverage(response, pending) or "")

    def test_extra_browser_discovery_succeeds(self) -> None:
        """A browser-only shelter may add a lifecycle-tracked listing beyond pending work."""
        response = self.REPORT | {
            "verdicts": [
                {"url": "https://example.test/pending", "verdict": "qualified"},
                {
                    "url": "https://example.test/discovery",
                    "verdict": "qualified",
                    "source_kind": "browser",
                },
            ]
        }
        pending = {"pending": [{"url": "https://example.test/pending"}]}

        self.assertIsNone(testee.validate_coverage(response, pending))


class WriteReportTest(unittest.TestCase):
    """Cover the launcher-facing report-writing behavior after contract validation."""

    def test_main_writes_required_report(self) -> None:
        """A valid response preserves the report that operators need in the run log."""
        with tempfile.TemporaryDirectory() as directory:
            verdicts = Path(directory) / "verdicts.json"
            report = Path(directory) / "report.txt"
            pending = Path(directory) / "pending.json"
            verdicts.write_text(
                json.dumps(
                    {
                        "verdicts": [{"url": "https://example.test/dog", "verdict": "qualified"}],
                        "report": "Refresh complete: no changes.",
                    }
                ),
                encoding="utf-8",
            )
            pending.write_text(json.dumps({"pending": [{"url": "https://example.test/dog"}]}), encoding="utf-8")

            with patch.object(sys, "argv", ["write_report.py", str(verdicts), str(report), str(pending)]):
                result = testee.main()

            self.assertEqual(0, result)
            self.assertEqual("Refresh complete: no changes.\n", report.read_text(encoding="utf-8"))

    def test_main_rejects_missing_report(self) -> None:
        """A response without an operator report fails so a broken judge cannot look healthy."""
        with tempfile.TemporaryDirectory() as directory:
            verdicts = Path(directory) / "verdicts.json"
            report = Path(directory) / "report.txt"
            pending = Path(directory) / "pending.json"
            verdicts.write_text(json.dumps({"verdicts": []}), encoding="utf-8")
            pending.write_text(json.dumps({"pending": []}), encoding="utf-8")

            with patch.object(sys, "argv", ["write_report.py", str(verdicts), str(report), str(pending)]):
                result = testee.main()

            self.assertEqual(1, result)
            self.assertFalse(report.exists())
