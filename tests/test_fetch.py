"""Tests for HTTP fetching: status carrying and the 4xx-vs-transient retry policy."""
from __future__ import annotations

import unittest
import urllib.error
from unittest import mock

import src.fetch as testee


class FetchErrorStatusTest(unittest.TestCase):
    def test_carries_supplied_status(self):
        """FetchError exposes the HTTP status when one is supplied."""
        self.assertEqual(testee.FetchError("boom", status=404).status, 404)

    def test_status_defaults_none(self):
        """A transport-level FetchError carries no status."""
        self.assertIsNone(testee.FetchError("boom").status)


class FetchRetryTest(unittest.TestCase):
    def setUp(self):
        """Silence the retry backoff sleep so tests run fast."""
        patcher = mock.patch.object(testee.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _http_error(self, code: int) -> urllib.error.HTTPError:
        """Build an HTTPError with the given status code."""
        return urllib.error.HTTPError("http://x", code, "err", {}, None)

    def test_permanent_4xx_not_retried(self):
        """A 404 is permanent: it stops after one attempt and carries its status."""
        urlopen = mock.Mock(side_effect=self._http_error(404))
        with mock.patch.object(testee.urllib.request, "urlopen", urlopen):
            with self.assertRaises(testee.FetchError) as ctx:
                testee.fetch("http://x")
        self.assertEqual(urlopen.call_count, 1)  # no pointless retry on a 4xx
        self.assertEqual(ctx.exception.status, 404)

    def test_5xx_is_retried_and_records_status(self):
        """A 500 is transient, so it is retried; its status is still recorded."""
        urlopen = mock.Mock(side_effect=self._http_error(500))
        with mock.patch.object(testee.urllib.request, "urlopen", urlopen):
            with self.assertRaises(testee.FetchError) as ctx:
                testee.fetch("http://x")
        self.assertEqual(urlopen.call_count, 2)  # initial + one retry
        self.assertEqual(ctx.exception.status, 500)

    def test_urlerror_retried_without_status(self):
        """A transport URLError is retried and carries no HTTP status."""
        urlopen = mock.Mock(side_effect=urllib.error.URLError("dns"))
        with mock.patch.object(testee.urllib.request, "urlopen", urlopen):
            with self.assertRaises(testee.FetchError) as ctx:
                testee.fetch("http://x")
        self.assertEqual(urlopen.call_count, 2)  # initial + one retry
        self.assertIsNone(ctx.exception.status)


if __name__ == "__main__":
    unittest.main()
