#!/usr/bin/env python3
"""Write a Codex judge report from a schema-validated verdict response.

Args: <verdicts_file> <report_file> <pending_file>
"""
from __future__ import annotations

import json
import sys
from collections import Counter

try:
    from src import dedup
except ModuleNotFoundError:
    import dedup


def validate_coverage(response: object, pending: object) -> str | None:
    """Return an error when a response omits or duplicates pending verdicts.

    Every candidate emitted by collection must receive exactly one verdict before
    the launcher mutates state. Browser discoveries may add response URLs that
    were not in the pending input.
    """
    if not isinstance(response, dict) or not isinstance(response.get("verdicts"), list):
        return "missing verdicts array"
    if not isinstance(pending, dict) or not isinstance(pending.get("pending"), list):
        return "missing pending array"

    pending_urls = [
        dog.get("url")
        for dog in pending["pending"]
        if isinstance(dog, dict) and isinstance(dog.get("url"), str) and dog["url"]
    ]
    if len(pending_urls) != len(pending["pending"]):
        return "pending input contains an invalid URL"
    pending_keys = [dedup.canonical(url) for url in pending_urls]
    if len(set(pending_keys)) != len(pending_keys):
        return "pending input contains duplicate URLs"

    verdict_urls = [
        verdict.get("url")
        for verdict in response["verdicts"]
        if isinstance(verdict, dict) and isinstance(verdict.get("url"), str) and verdict["url"]
    ]
    if len(verdict_urls) != len(response["verdicts"]):
        return "verdict response contains an invalid URL"
    verdict_keys = [dedup.canonical(url) for url in verdict_urls]
    duplicates = sorted(url for url, count in Counter(verdict_keys).items() if count > 1)
    if duplicates:
        return f"verdict response duplicates {len(duplicates)} URL(s)"

    missing = set(pending_keys) - set(verdict_keys)
    if missing:
        return f"verdict response omits {len(missing)} pending URL(s)"
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
