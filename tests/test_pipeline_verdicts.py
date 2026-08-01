"""Tests for the pipeline's Codex verdict response input contract."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import src.pipeline as testee


class LoadVerdictsTest(unittest.TestCase):
    """Cover the launcher-produced structured response wrapper."""

    def test_load_verdicts_accepts_codex_response_object(self) -> None:
        """The pipeline must merge verdicts from Codex's response object, not discard them as metadata."""
        expected = [{"url": "https://example.test/dog", "verdict": "qualified"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "verdicts.json"
            path.write_text(
                json.dumps({"verdicts": expected, "report": "Refresh complete."}),
                encoding="utf-8",
            )

            actual = testee._load_verdicts(str(path))

        self.assertEqual(expected, actual)
