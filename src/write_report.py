#!/usr/bin/env python3
"""Write a Codex judge report from a schema-validated verdict response.

Args: <verdicts_file> <report_file> <pending_file>
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from src import dedup, store


def _sample_urls(urls: list[str]) -> str:
    """Return a deterministic, bounded sample for a validation error.

    Args:
        urls: Canonical or raw URLs that caused the same validation failure.

    Returns:
        Up to three sorted URLs joined for a concise error message.
    """
    return ", ".join(sorted(urls)[:3])


def validate_coverage(response: object, pending: object) -> str | None:
    """Return an error when response verdicts violate the pending-work contract.

    Every candidate emitted by collection must receive exactly one verdict before
    the launcher mutates state. Browser discoveries may add response URLs only
    when they carry browser lifecycle metadata. Deferred outcomes cover only an
    existing pending re-check and intentionally leave that state entry untouched.

    Args:
        response: The decoded schema-validated Codex response.
        pending: The decoded collection artifact for the same run.

    Returns:
        A concise validation error, or None when the response is safe to apply.
    """
    if not isinstance(response, dict) or not isinstance(response.get("verdicts"), list):
        return "missing verdicts array"
    if not isinstance(pending, dict) or not isinstance(pending.get("pending"), list):
        return "missing pending array"

    pending_entries = pending["pending"]
    pending_urls = [
        dog.get("url")
        for dog in pending_entries
        if isinstance(dog, dict) and isinstance(dog.get("url"), str) and dog["url"]
    ]
    if len(pending_urls) != len(pending_entries):
        return "pending input contains an invalid URL"
    pending_keys = [dedup.canonical(url) for url in pending_urls]
    pending_duplicates = sorted(
        key for key, count in Counter(pending_keys).items() if count > 1
    )
    if pending_duplicates:
        return (
            f"pending input contains {len(pending_duplicates)} duplicate URL(s): "
            f"{_sample_urls(pending_duplicates)}"
        )
    pending_by_key = dict(zip(pending_keys, pending_entries, strict=True))

    verdict_entries = response["verdicts"]
    verdict_urls = [
        verdict.get("url")
        for verdict in verdict_entries
        if isinstance(verdict, dict) and isinstance(verdict.get("url"), str) and verdict["url"]
    ]
    if len(verdict_urls) != len(verdict_entries):
        return "verdict response contains an invalid URL"
    unsafe_urls = [url for url in verdict_urls if not store.valid_verdict_url(url)]
    if unsafe_urls:
        return (
            f"verdict response contains {len(unsafe_urls)} unsafe URL(s): "
            f"{_sample_urls(unsafe_urls)}"
        )
    verdict_keys = [dedup.canonical(url) for url in verdict_urls]
    duplicates = sorted(url for url, count in Counter(verdict_keys).items() if count > 1)
    if duplicates:
        return f"verdict response duplicates {len(duplicates)} URL(s): {_sample_urls(duplicates)}"

    pending_key_set = set(pending_keys)
    missing = pending_key_set - set(verdict_keys)
    if missing:
        return f"verdict response omits {len(missing)} pending URL(s): {_sample_urls(list(missing))}"

    discoveries = [
        (verdict, key) for verdict, key in zip(verdict_entries, verdict_keys, strict=True)
        if key not in pending_key_set
    ]
    invalid_source_urls = [
        verdict["url"] for verdict, _ in discoveries
        if verdict.get("source_kind") != "browser"
    ]
    if invalid_source_urls:
        return (
            f"browser discoveries have invalid source_kind for {len(invalid_source_urls)} URL(s): "
            f"{_sample_urls(invalid_source_urls)}"
        )
    deferred_discovery_urls = [
        verdict["url"] for verdict, _ in discoveries
        if verdict.get("verdict") == store.DEFERRED
    ]
    if deferred_discovery_urls:
        return (
            f"browser discoveries defer {len(deferred_discovery_urls)} URL(s): "
            f"{_sample_urls(deferred_discovery_urls)}"
        )
    invalid_deferred_urls = [
        verdict["url"] for verdict, key in zip(verdict_entries, verdict_keys, strict=True)
        if key in pending_key_set
        and verdict.get("verdict") == store.DEFERRED
        and not pending_by_key[key].get("recheck")
    ]
    if invalid_deferred_urls:
        return (
            f"deferred verdicts are not pending re-checks for {len(invalid_deferred_urls)} URL(s): "
            f"{_sample_urls(invalid_deferred_urls)}"
        )
    return None


def main() -> int:
    """Validate a complete response and write its report to the requested file.

    Returns:
        Zero after a complete response writes a non-empty string report; one if
        either input cannot be decoded or the response is incomplete.
    """
    verdicts_file, report_file, pending_file = sys.argv[1:4]
    try:
        with open(verdicts_file, encoding="utf-8") as source:
            response = json.load(source)
        with open(pending_file, encoding="utf-8") as source:
            pending = json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        print(f"invalid Codex response input: {error}", file=sys.stderr)
        return 1

    report = response.get("report") if isinstance(response, dict) else None
    if not isinstance(report, str) or not report.strip():
        print("invalid Codex verdict response: missing non-empty report", file=sys.stderr)
        return 1
    coverage_error = validate_coverage(response, pending)
    if coverage_error:
        print(f"invalid Codex verdict response: {coverage_error}", file=sys.stderr)
        return 1

    with open(report_file, "w", encoding="utf-8") as destination:
        destination.write(report)
        destination.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
