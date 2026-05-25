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
import logging
import os
import time
from datetime import datetime

from src import manifest, render, store
from src.dedup import canonical
from src.fetch import FetchError, fetch
from src.parsers import registry
from src.parsers.base import ParseError, is_dog

DETAIL_FETCH_DELAY_S = 0.5

logger = logging.getLogger("dog_finder.pipeline")


def _result_detail(result: manifest.SourceResult) -> str:
    """Build the human-readable tail for a per-shelter log line."""
    if result.status in (manifest.STATUS_OK, manifest.STATUS_EMPTY_OK):
        return f" — {result.n_cards or 0} cards, {result.n_new or 0} new"
    if result.error:
        return f" — {result.error}"
    return ""


def _collect_source(
    shelter: dict, module, url: str, state: dict, present: set[str], ts: str
) -> manifest.SourceResult:
    """Fetch and parse one shelter page with its parser, upserting dogs to state.

    Args:
        shelter: The shelter config entry.
        module: The parser module resolved for this shelter.
        url: The page URL to fetch.
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
    has_detail = hasattr(module, "parse_detail")

    try:
        result = fetch(url)
    except FetchError as error:
        base.status = manifest.STATUS_FETCH_ERROR
        base.error = str(error)
        return base

    base.http_status = result.status
    base.bytes = result.bytes
    try:
        cards = module.parse_list(result.body)
    except ParseError as error:
        base.status = manifest.STATUS_PARSE_ERROR
        base.error = str(error)
        return base

    base.n_cards = len(cards)
    if not cards:
        base.status = manifest.STATUS_EMPTY_OK
        base.n_new = 0
        return base

    new_cards = []
    for card in (c for c in cards if is_dog(c)):
        key = canonical(card.url)
        present.add(key)
        if key in state["listings"]:
            store.touch(state, card.url, ts)
        else:
            new_cards.append(card)

    if new_cards and has_detail:
        logger.info("    %s: fetching %d new detail page(s)", name, len(new_cards))
    source_kind = getattr(module, "SOURCE_KIND", "petrescue")
    for card in new_cards:
        card.shelter = card.shelter or name
        if has_detail:
            try:
                detail = fetch(card.url)
                module.parse_detail(detail.body, card)
            except (FetchError, ParseError) as error:
                base.error = f"detail fetch/parse issue: {error}"
            time.sleep(DETAIL_FETCH_DELAY_S)
        store.upsert_listing(state, card, ts, source_kind)
        logger.debug("      + %s — %s", card.name, card.breed)

    base.n_new = len(new_cards)
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

    total = len(shelters)
    logger.info("collect: %d shelters; state has %d known listing(s)", total, len(state["listings"]))
    for index, shelter in enumerate(shelters, start=1):
        render_kind = shelter.get("render", "static")
        if render_kind == "dead":
            result = manifest.SourceResult(
                shelter=shelter["name"], listing_url=shelter["listing_url"],
                render=render_kind, status=manifest.STATUS_SKIPPED_DEAD)
        else:
            resolved = registry.resolve(shelter)
            if resolved is None:
                reason = ("JS-rendered, no code parser" if render_kind == "js"
                          else "no code parser for this site")
                result = manifest.SourceResult(
                    shelter=shelter["name"], listing_url=shelter["listing_url"],
                    render=render_kind, status=manifest.STATUS_NEEDS_BROWSER, error=reason)
            else:
                module, url = resolved
                result = _collect_source(shelter, module, url, state, present, ts)
        run_manifest.add(result)
        logger.info("[%2d/%d] %-13s %s%s", index, total, result.status,
                    shelter["name"], _result_detail(result))

    flagged = store.flag_disappeared(state, present, ts)
    if flagged:
        logger.info("flagged %d qualified dog(s) as maybe_adopted (vanished this run)", len(flagged))
    store.save_state(state_path, state)

    pending = store.pending_listings(state)
    logger.info("collect done: %d pending dog(s) need a verdict", len(pending))
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
    if not verdicts:
        logger.warning("apply: no verdicts found at %s; re-rendering from existing state", verdicts_path)
    else:
        logger.info("apply: merging %d verdict(s) into state", len(verdicts))
    store.apply_verdicts(state, verdicts, ts)
    store.save_state(state_path, state)

    qualified = store.qualified_for_render(state)
    logger.info("apply: index now lists %d qualified dog(s)", len(qualified))
    with open(index_path, encoding="utf-8") as handle:
        current_md = handle.read()
    updated = render.render_index(current_md, qualified, datetime.now().strftime("%Y-%m-%d"))
    with open(index_path, "w", encoding="utf-8") as out:
        out.write(updated)
    return len(qualified)


def main() -> int:
    """Parse CLI args, dispatch to collect/apply, and print a one-line summary."""
    parser = argparse.ArgumentParser(description="dog-finder pipeline")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="log each new dog as its detail page is fetched")
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
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
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
