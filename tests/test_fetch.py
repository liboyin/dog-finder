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
        error = urllib.error.HTTPError("http://x", code, "err", {}, None)
        error.close = mock.Mock(wraps=error.close)
        return error

    def test_permanent_4xx_not_retried(self):
        """A 404 stops after one attempt and closes its response immediately."""
        error = self._http_error(404)
        urlopen = mock.Mock(side_effect=error)
        with mock.patch.object(testee.urllib.request, "urlopen", urlopen):
            with self.assertRaises(testee.FetchError) as ctx:
                testee.fetch("http://x")
        self.assertEqual(urlopen.call_count, 1)  # no pointless retry on a 4xx
        self.assertEqual(ctx.exception.status, 404)
        error.close.assert_called_once_with()

    def test_5xx_is_retried_and_records_status(self):
        """Each retried 500 response closes before the next network attempt."""
        errors = [self._http_error(500), self._http_error(500)]
        urlopen = mock.Mock(side_effect=errors)
        testee.time.sleep.side_effect = lambda _seconds: self.assertTrue(errors[0].close.called)
        with mock.patch.object(testee.urllib.request, "urlopen", urlopen):
            with self.assertRaises(testee.FetchError) as ctx:
                testee.fetch("http://x")
        self.assertEqual(urlopen.call_count, 2)  # initial + one retry
        self.assertEqual(ctx.exception.status, 500)
        for error in errors:
            error.close.assert_called_once_with()

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
