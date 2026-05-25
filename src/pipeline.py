"""dog-finder pipeline: deterministic fetch/parse/dedup around an LLM judge.

Two subcommands frame one nightly run:

* ``collect`` — fetch and parse the server-rendered PetRescue shelters, dedup
  against ``state.json``, detail-fetch genuinely new dogs, flag qualified dogs
  that vanished as ``maybe_adopted``, and write ``pending.json`` (dogs needing a
  verdict) plus ``fetch_manifest.json`` (per-source outcomes, incl. the
  ``NEEDS_BROWSER`` shelters the LLM must handle via the browser MCP).
* ``apply`` — merge the LLM's ``verdicts.json`` into ``state.json`` and
  re-render the human-facing ``dog-index.md`` from state.

Run from the repo root::

    python3 -m src.pipeline collect --shelters config/shelters.json \\
        --state data/state.json --out runs/<ts>/
    python3 -m src.pipeline apply --state data/state.json \\
        --verdicts runs/<ts>/verdicts.json --index data/dog-index.md
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime

from src import manifest, render, store
from src.dedup import canonical
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


def _collect_petrescue(
    shelter: dict, url: str, state: dict, present: set[str], ts: str
) -> manifest.SourceResult:
    """Fetch a PetRescue page, upserting its dogs into state.

    Args:
        shelter: The shelter config entry.
        url: PetRescue page URL to fetch.
        state: The state document (mutated in place).
        present: Set of canonical URLs seen on OK pages this run (mutated).
        ts: This run's timestamp.

    Returns:
        The SourceResult describing this source's outcome.
    """
    name = shelter["name"]
    base = manifest.SourceResult(
        shelter=name, listing_url=shelter["listing_url"],
        render=shelter.get("render", "static"), status=manifest.STATUS_OK,
        fetched_url=url,
    )

    try:
        result = fetch(url)
    except FetchError as error:
        base.status = manifest.STATUS_FETCH_ERROR
        base.error = str(error)
        return base

    base.http_status = result.status
    base.bytes = result.bytes
    try:
        cards = petrescue.parse_list(result.body)
    except ParseError as error:
        base.status = manifest.STATUS_PARSE_ERROR
        base.error = str(error)
        return base

    base.n_cards = len(cards)
    if not cards:
        base.status = manifest.STATUS_EMPTY_OK
        base.n_new = 0
        return base

    n_new = 0
    for card in (c for c in cards if petrescue.is_dog(c)):
        key = canonical(card.url)
        present.add(key)
        if key in state["listings"]:
            store.touch(state, card.url, ts)
            continue
        card.shelter = name
        try:
            detail = fetch(card.url)
            petrescue.parse_detail(detail.body, card)
        except (FetchError, ParseError) as error:
            base.error = f"detail fetch/parse issue: {error}"
        store.upsert_petrescue(state, card, ts)
        n_new += 1
        time.sleep(DETAIL_FETCH_DELAY_S)

    base.n_new = n_new
    return base


def collect(shelters_path: str, state_path: str, out_dir: str) -> dict:
    """Run the collect phase: update state and write pending.json + manifest.

    Args:
        shelters_path: Path to config/shelters.json.
        state_path: Path to data/state.json (created if absent).
        out_dir: Directory for this run's artifacts (created if absent).

    Returns:
        A stats dict: n_new, n_needs_browser, n_errors, n_maybe_adopted.
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(out_dir, exist_ok=True)

    with open(shelters_path, encoding="utf-8") as handle:
        shelters = json.load(handle)
    state = store.load_state(state_path)

    run_manifest = manifest.Manifest(run_ts=ts)
    present: set[str] = set()

    for shelter in shelters:
        render_kind = shelter.get("render", "static")
        if render_kind == "dead":
            run_manifest.add(manifest.SourceResult(
                shelter=shelter["name"], listing_url=shelter["listing_url"],
                render=render_kind, status=manifest.STATUS_SKIPPED_DEAD))
            continue
        url = _petrescue_url(shelter)
        if url is None:
            reason = ("JS-rendered, no PetRescue cross-post" if render_kind == "js"
                      else "no code parser for this site")
            run_manifest.add(manifest.SourceResult(
                shelter=shelter["name"], listing_url=shelter["listing_url"],
                render=render_kind, status=manifest.STATUS_NEEDS_BROWSER, error=reason))
            continue
        run_manifest.add(_collect_petrescue(shelter, url, state, present, ts))

    flagged = store.flag_disappeared(state, present, ts)
    store.save_state(state_path, state)

    pending = store.pending_listings(state)
    with open(os.path.join(out_dir, "pending.json"), "w", encoding="utf-8") as out:
        json.dump({"run_ts": ts, "pending": pending}, out, indent=2, ensure_ascii=False)
    run_manifest.write(os.path.join(out_dir, "fetch_manifest.json"))

    return {
        "n_new": sum((s.n_new or 0) for s in run_manifest.sources),
        "n_needs_browser": sum(s.status == manifest.STATUS_NEEDS_BROWSER for s in run_manifest.sources),
        "n_errors": sum(s.status in (manifest.STATUS_PARSE_ERROR, manifest.STATUS_FETCH_ERROR, manifest.STATUS_EMPTY_OK) for s in run_manifest.sources),
        "n_maybe_adopted": len(flagged),
        "n_pending": len(pending),
    }


def _load_verdicts(path: str) -> list[dict]:
    """Load verdicts.json, accepting either a bare list or a {"verdicts": [...]} dict."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return data.get("verdicts", [])
    return data


def apply(state_path: str, verdicts_path: str, index_path: str) -> int:
    """Run the apply phase: merge verdicts and re-render the index.

    Args:
        state_path: Path to data/state.json.
        verdicts_path: Path to the LLM-produced verdicts.json.
        index_path: Path to data/dog-index.md (re-rendered in place).

    Returns:
        The number of qualified, non-removed listings now in the index.
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    state = store.load_state(state_path)
    verdicts = _load_verdicts(verdicts_path) if os.path.exists(verdicts_path) else []
    store.apply_verdicts(state, verdicts, ts)
    store.save_state(state_path, state)

    qualified = store.qualified_for_render(state)
    with open(index_path, encoding="utf-8") as handle:
        current_md = handle.read()
    updated = render.render_index(current_md, qualified, datetime.now().strftime("%Y-%m-%d"))
    with open(index_path, "w", encoding="utf-8") as out:
        out.write(updated)
    return len(qualified)


def main() -> int:
    """Parse CLI args, dispatch to collect/apply, and print a one-line summary."""
    parser = argparse.ArgumentParser(description="dog-finder pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    collect_parser = sub.add_parser("collect", help="fetch/parse/dedup into state + pending.json")
    collect_parser.add_argument("--shelters", required=True)
    collect_parser.add_argument("--state", required=True)
    collect_parser.add_argument("--out", required=True)

    apply_parser = sub.add_parser("apply", help="merge verdicts.json and re-render the index")
    apply_parser.add_argument("--state", required=True)
    apply_parser.add_argument("--verdicts", required=True)
    apply_parser.add_argument("--index", required=True)

    args = parser.parse_args()
    if args.command == "collect":
        stats = collect(args.shelters, args.state, args.out)
        print(
            f"collect complete: {stats['n_new']} new, {stats['n_pending']} pending, "
            f"{stats['n_maybe_adopted']} maybe-adopted, {stats['n_needs_browser']} need browser, "
            f"{stats['n_errors']} source error(s)"
        )
    else:
        n_qualified = apply(args.state, args.verdicts, args.index)
        print(f"apply complete: index now lists {n_qualified} qualified dog(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
