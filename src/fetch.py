"""HTTP fetching for the dog-finder pipeline.

Static shelter pages are retrieved with a browser-like User-Agent and a single
retry. JS-rendered shelters are NOT fetched here — the pipeline routes those to
the LLM/browser-MCP path instead.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) dog-finder/1.0"
)
DEFAULT_TIMEOUT = 25
RETRY_BACKOFF_S = 1.5


class FetchError(Exception):
    """Raised when a URL cannot be retrieved (network error or non-2xx status)."""


@dataclass
class FetchResult:
    """Outcome of a successful HTTP GET."""

    url: str
    status: int
    body: str
    bytes: int


def fetch(url: str, *, timeout: int = DEFAULT_TIMEOUT, retries: int = 1) -> FetchResult:
    """Fetch a URL via HTTP GET with a browser-like UA and one retry.

    Args:
        url: Absolute URL to GET.
        timeout: Per-attempt timeout in seconds.
        retries: Number of additional attempts after the first on failure.

    Returns:
        A FetchResult with the decoded body, byte count, and HTTP status.

    Raises:
        FetchError: If every attempt fails or a non-2xx status is returned.
    """
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return FetchResult(
                    url=url,
                    status=response.status,
                    body=raw.decode("utf-8", errors="replace"),
                    bytes=len(raw),
                )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(RETRY_BACKOFF_S)
    raise FetchError(f"GET {url} failed after {retries + 1} attempt(s): {last_error}")
