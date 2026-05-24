"""dog-finder pipeline: fetch + parse + dedup PetRescue shelters into candidates.

Run as a module from the repo root::

    python3 -m src.pipeline --shelters config/shelters.json \\
        --index data/dog-index.md --out runs/<ts>/

It writes two files into ``--out``:

* ``candidates.json`` — new listings (not already in the index) with breed/fee
  filled from each listing's detail page, for the LLM to judge.
* ``fetch_manifest.json`` — per-source outcomes (OK / EMPTY_OK / PARSE_ERROR /
  FETCH_ERROR / NEEDS_BROWSER / SKIPPED_DEAD) for shelter-level observability.

Static PetRescue pages are parsed in code. A ``render:js`` shelter is still
handled in code when it has a PetRescue cross-post (its static listing). Other
``render:js`` shelters and non-PetRescue own-sites are flagged ``NEEDS_BROWSER``
so the LLM drives them via Playwright/Chrome MCP.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime

from src import dedup, manifest
from src.fetch import FetchError, fetch
from src.parsers import petrescue
from src.parsers.petrescue import ParseError

PETRESCUE_HOST = "petrescue.com.au"
DETAIL_FETCH_DELAY_S = 0.5


def _petrescue_url(shelter: dict) -> str | None:
    """Return the shelter's PetRescue URL (listing or cross-post), or None."""
    listing_url = shelter.get("listing_url", "")
    if PETRESCUE_HOST in listing_url:
        return listing_url
    cross_post = shelter.get("petrescue_url", "")
    if PETRESCUE_HOST in cross_post:
        return cross_post
    return None


def _process_petrescue(
    shelter: dict, url: str, known: set[str], seen: set[str]
) -> tuple[manifest.SourceResult, list[petrescue.Listing]]:
    """Fetch and parse one PetRescue page into new candidate listings.

    Args:
        shelter: The shelter config entry.
        url: The PetRescue page URL to fetch.
        known: Canonical URLs already in the index (skip these).
        seen: Canonical URLs already emitted this run (mutated to dedup across
            sources).

    Returns:
        A (SourceResult, listings) tuple. ``listings`` holds the new, enriched
        candidates from this source (possibly empty).
    """
    name = shelter["name"]
    base = manifest.SourceResult(
        shelter=name, listing_url=shelter["listing_url"], render=shelter.get("render", "static"),
        status=manifest.STATUS_OK, fetched_url=url,
    )

    try:
        result = fetch(url)
    except FetchError as error:
        base.status = manifest.STATUS_FETCH_ERROR
        base.error = str(error)
        return base, []

    base.http_status = result.status
    base.bytes = result.bytes

    try:
        cards = petrescue.parse_list(result.body)
    except ParseError as error:
        base.status = manifest.STATUS_PARSE_ERROR
        base.error = str(error)
        return base, []

    base.n_cards = len(cards)
    if not cards:
        base.status = manifest.STATUS_EMPTY_OK
        base.n_new = 0
        return base, []

    dog_cards = [card for card in cards if petrescue.is_dog(card)]
    new_listings: list[petrescue.Listing] = []
    detail_errors = 0
    for card in dog_cards:
        canonical_url = dedup.canonical(card.url)
        if canonical_url in known or canonical_url in seen:
            continue
        seen.add(canonical_url)
        card.shelter = name
        try:
            detail = fetch(card.url)
            petrescue.parse_detail(detail.body, card)
        except (FetchError, ParseError) as error:
            detail_errors += 1
            base.error = f"{detail_errors} detail fetch/parse error(s); last: {error}"
        new_listings.append(card)
        time.sleep(DETAIL_FETCH_DELAY_S)

    base.n_new = len(new_listings)
    return base, new_listings


def run(shelters_path: str, index_path: str, out_dir: str) -> manifest.Manifest:
    """Execute the pipeline and write candidates.json + fetch_manifest.json.

    Args:
        shelters_path: Path to config/shelters.json.
        index_path: Path to data/dog-index.md.
        out_dir: Directory to write run artifacts into (created if absent).

    Returns:
        The populated Manifest (also written to disk).
    """
    run_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(out_dir, exist_ok=True)

    with open(shelters_path, encoding="utf-8") as handle:
        shelters = json.load(handle)
    with open(index_path, encoding="utf-8") as handle:
        known = dedup.known_urls(handle.read())

    run_manifest = manifest.Manifest(run_ts=run_ts)
    candidates: list[petrescue.Listing] = []
    seen: set[str] = set()

    for shelter in shelters:
        render = shelter.get("render", "static")
        if render == "dead":
            run_manifest.add(
                manifest.SourceResult(
                    shelter=shelter["name"], listing_url=shelter["listing_url"],
                    render=render, status=manifest.STATUS_SKIPPED_DEAD,
                )
            )
            continue

        url = _petrescue_url(shelter)
        if url is None:
            reason = "JS-rendered, no PetRescue cross-post" if render == "js" else "no code parser for this site"
            run_manifest.add(
                manifest.SourceResult(
                    shelter=shelter["name"], listing_url=shelter["listing_url"],
                    render=render, status=manifest.STATUS_NEEDS_BROWSER, error=reason,
                )
            )
            continue

        source_result, new_listings = _process_petrescue(shelter, url, known, seen)
        run_manifest.add(source_result)
        candidates.extend(new_listings)

    _write_candidates(os.path.join(out_dir, "candidates.json"), run_ts, candidates)
    run_manifest.write(os.path.join(out_dir, "fetch_manifest.json"))
    return run_manifest


def _write_candidates(path: str, run_ts: str, candidates: list[petrescue.Listing]) -> None:
    """Write the candidate listings to a compact JSON file."""
    payload = {
        "run_ts": run_ts,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidates": [listing.to_dict() for listing in candidates],
    }
    with open(path, "w", encoding="utf-8") as out:
        json.dump(payload, out, indent=2, ensure_ascii=False)


def main() -> int:
    """Parse CLI arguments, run the pipeline, and print a one-line summary."""
    parser = argparse.ArgumentParser(description="dog-finder fetch/parse/dedup pipeline")
    parser.add_argument("--shelters", required=True, help="path to shelters.json")
    parser.add_argument("--index", required=True, help="path to dog-index.md")
    parser.add_argument("--out", required=True, help="output directory for run artifacts")
    args = parser.parse_args()

    result = run(args.shelters, args.index, args.out)
    n_candidates = sum((source.n_new or 0) for source in result.sources)
    n_needs_browser = sum(s.status == manifest.STATUS_NEEDS_BROWSER for s in result.sources)
    n_errors = sum(
        s.status in (manifest.STATUS_PARSE_ERROR, manifest.STATUS_FETCH_ERROR, manifest.STATUS_EMPTY_OK)
        for s in result.sources
    )
    print(
        f"pipeline complete: {n_candidates} new candidates, "
        f"{n_needs_browser} need browser, {n_errors} source error(s); out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
