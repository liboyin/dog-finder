"""Tests for extracting the human report from a Codex verdict response."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.write_report as testee


class WriteReportTest(unittest.TestCase):
    """Cover the launcher-facing structured response contract."""

    def test_main_writes_required_report(self) -> None:
        """A valid response preserves the report that operators need in the run log."""
        with tempfile.TemporaryDirectory() as directory:
            verdicts = Path(directory) / "verdicts.json"
            report = Path(directory) / "report.txt"
            verdicts.write_text(
                json.dumps(
                    {
                        "verdicts": [{"url": "https://example.test/dog"}],
                        "report": "Refresh complete: no changes.",
                    }
                ),
                encoding="utf-8",
            )
            pending = Path(directory) / "pending.json"
            pending.write_text(
                json.dumps({"pending": [{"url": "https://example.test/dog"}]}),
                encoding="utf-8",
            )

            with patch.object(sys, "argv", ["write_report.py", str(verdicts), str(report), str(pending)]):
                result = testee.main()

            self.assertEqual(0, result)
            self.assertEqual("Refresh complete: no changes.\n", report.read_text(encoding="utf-8"))

    def test_main_rejects_missing_report(self) -> None:
        """A response without an operator report fails so a broken judge cannot look healthy."""
        with tempfile.TemporaryDirectory() as directory:
            verdicts = Path(directory) / "verdicts.json"
            report = Path(directory) / "report.txt"
            verdicts.write_text(json.dumps({"verdicts": []}), encoding="utf-8")
            pending = Path(directory) / "pending.json"
            pending.write_text(json.dumps({"pending": []}), encoding="utf-8")

            with patch.object(sys, "argv", ["write_report.py", str(verdicts), str(report), str(pending)]):
                result = testee.main()

            self.assertEqual(1, result)
            self.assertFalse(report.exists())

    def test_main_rejects_partial_verdict_coverage(self) -> None:
        """A partial judge response must not silently leave a pending dog unresolved."""
        with tempfile.TemporaryDirectory() as directory:
            verdicts = Path(directory) / "verdicts.json"
            report = Path(directory) / "report.txt"
            pending = Path(directory) / "pending.json"
            verdicts.write_text(
                json.dumps(
                    {
                        "verdicts": [{"url": "https://example.test/first"}],
                        "report": "Refresh complete.",
                    }
                ),
                encoding="utf-8",
            )
            pending.write_text(
                json.dumps(
                    {
                        "pending": [
                            {"url": "https://example.test/first"},
                            {"url": "https://example.test/second"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(sys, "argv", ["write_report.py", str(verdicts), str(report), str(pending)]):
                result = testee.main()

            self.assertEqual(1, result)
            self.assertFalse(report.exists())

    def test_main_rejects_duplicate_canonical_verdict_urls(self) -> None:
        """Equivalent verdict URLs must not merge two decisions into one state entry."""
        with tempfile.TemporaryDirectory() as directory:
            verdicts = Path(directory) / "verdicts.json"
            report = Path(directory) / "report.txt"
            pending = Path(directory) / "pending.json"
            verdicts.write_text(
                json.dumps(
                    {
                        "verdicts": [
                            {"url": "https://EXAMPLE.test/dog/"},
                            {"url": "https://example.test/dog"},
                        ],
                        "report": "Refresh complete.",
                    }
                ),
                encoding="utf-8",
            )
            pending.write_text(
                json.dumps({"pending": [{"url": "https://example.test/dog"}]}),
                encoding="utf-8",
            )

            with patch.object(sys, "argv", ["write_report.py", str(verdicts), str(report), str(pending)]):
                result = testee.main()

            self.assertEqual(1, result)
            self.assertFalse(report.exists())

    def test_main_allows_extra_browser_discovery(self) -> None:
        """A browser-only shelter may add a new listing beyond the pending static candidates."""
        with tempfile.TemporaryDirectory() as directory:
            verdicts = Path(directory) / "verdicts.json"
            report = Path(directory) / "report.txt"
            pending = Path(directory) / "pending.json"
            verdicts.write_text(
                json.dumps(
                    {
                        "verdicts": [
                            {"url": "https://example.test/pending"},
                            {"url": "https://example.test/browser-discovery"},
                        ],
                        "report": "Refresh complete.",
                    }
                ),
                encoding="utf-8",
            )
            pending.write_text(
                json.dumps({"pending": [{"url": "https://example.test/pending"}]}),
                encoding="utf-8",
            )

            with patch.object(sys, "argv", ["write_report.py", str(verdicts), str(report), str(pending)]):
                result = testee.main()

            self.assertEqual(0, result)
            self.assertEqual("Refresh complete.\n", report.read_text(encoding="utf-8"))

    def test_script_invocation_writes_report(self) -> None:
        """The Bash launcher can invoke the script directly outside the src package context."""
        with tempfile.TemporaryDirectory() as directory:
            verdicts = Path(directory) / "verdicts.json"
            report = Path(directory) / "report.txt"
            pending = Path(directory) / "pending.json"
            verdicts.write_text(
                json.dumps(
                    {
                        "verdicts": [{"url": "https://example.test/dog"}],
                        "report": "Refresh complete.",
                    }
                ),
                encoding="utf-8",
            )
            pending.write_text(
                json.dumps({"pending": [{"url": "https://example.test/dog"}]}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(Path(testee.__file__)), str(verdicts), str(report), str(pending)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("Refresh complete.\n", report.read_text(encoding="utf-8"))
