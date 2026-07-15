"""dog-finder pipeline: deterministic fetch/parse/dedup around an LLM judge.

Two subcommands frame one nightly run:

* ``collect`` — fetch and parse the server-rendered PetRescue shelters, dedup
  against ``state.json``, detail-fetch genuinely new dogs, re-fetch the detail
  page of already-qualified dogs to refresh status and catch a now-dead detail
  URL, flag qualified dogs that vanished (from their list page or detail page)
  as ``maybe_adopted``, and write ``pending.json`` (dogs needing a verdict)
  plus ``fetch_manifest.json`` (per-source outcomes, incl. the
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
import subprocess
import time
from datetime import datetime, timedelta

from src import manifest, render, store
from src.dedup import canonical
from src.fetch import FetchError, fetch
from src.parsers import registry
from src.parsers.base import Listing, ParseError, is_dog

DETAIL_FETCH_DELAY_S = 0.5
PAGE_DELAY_S = 0.5
MAX_PAGES = 30  # safety cap on pages followed per source

logger = logging.getLogger("dog_finder.pipeline")


def _result_detail(result: manifest.SourceResult) -> str:
    """Build the human-readable tail for a per-shelter log line."""
    if result.status in (manifest.STATUS_OK, manifest.STATUS_EMPTY_OK):
        pages = f", {result.n_pages}p" if (result.n_pages or 0) > 1 else ""
        suffix = f"; {result.error}" if result.error else ""
        return f" — {result.n_cards or 0} cards, {result.n_new or 0} new{pages}{suffix}"
    if result.error:
        return f" — {result.error}"
    return ""


def _fetch_all_pages(module, start_url: str, base: manifest.SourceResult) -> list:
    """Fetch and parse every page of a source, following next_page_url.

    Pages are followed until the parser reports no next page, a page yields no
    cards, or MAX_PAGES is reached. A first-page fetch/parse failure sets
    ``base.status`` to FETCH_ERROR/PARSE_ERROR and returns []; a later-page
    failure is noted in ``base.error`` and stops paging with the pages so far.

    Args:
        module: The parser module (may expose prepare_url / next_page_url).
        start_url: The source's starting URL.
        base: The SourceResult to annotate (n_pages, http_status, bytes, error).

    Returns:
        The cards across all fetched pages, de-duplicated by canonical URL.
    """
    page_url = module.prepare_url(start_url) if hasattr(module, "prepare_url") else start_url
    all_cards: list = []
    seen: set[str] = set()
    pages = 0
    while page_url and pages < MAX_PAGES:
        try:
            result = fetch(page_url)
        except FetchError as error:
            if pages == 0:
                base.status = manifest.STATUS_FETCH_ERROR
                base.error = str(error)
                return []
            base.error = f"page {pages + 1} fetch failed: {error}"
            break
        if pages == 0:
            base.http_status = result.status
            base.bytes = result.bytes
        try:
            cards = module.parse_list(result.body)
        except ParseError as error:
            if pages == 0:
                base.status = manifest.STATUS_PARSE_ERROR
                base.error = str(error)
                return []
            base.error = f"page {pages + 1} parse failed: {error}"
            break
        pages += 1
        for card in cards:
            key = canonical(card.url)
            if key not in seen:
                seen.add(key)
                all_cards.append(card)
        if not cards:
            break
        page_url = module.next_page_url(result.body, page_url) if hasattr(module, "next_page_url") else None
        if page_url:
            time.sleep(PAGE_DELAY_S)
    base.n_pages = pages
    if page_url and pages >= MAX_PAGES:
        logger.warning("%s: hit MAX_PAGES=%d cap; later pages skipped", base.shelter, MAX_PAGES)
        base.error = f"hit MAX_PAGES={MAX_PAGES} cap"
    return all_cards


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

    cards = _fetch_all_pages(module, url, base)
    if base.status in (manifest.STATUS_FETCH_ERROR, manifest.STATUS_PARSE_ERROR):
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
    detail_errors: list[str] = []
    for card in new_cards:
        card.shelter = card.shelter or name
        if has_detail:
            try:
                detail = fetch(card.url)
                module.parse_detail(detail.body, card)
            except (FetchError, ParseError) as error:
                detail_errors.append(str(error))
            time.sleep(DETAIL_FETCH_DELAY_S)
        store.upsert_listing(state, card, ts, source_kind)
        logger.debug("      + %s — %s", card.name, card.breed)

    if detail_errors:
        note = f"{len(detail_errors)} detail fetch/parse failure(s); first: {detail_errors[0]}"
        base.error = f"{base.error}; {note}" if base.error else note
    base.n_new = len(new_cards)
    return base


def _recheck_qualified_details(state: dict, ts: str) -> tuple[set[str], list[dict]]:
    """Re-fetch each qualified listing's own detail page to catch drift its
    shelter's list page won't show: a status change (e.g. available -> on-hold),
    an explicit "adopted" status while the card lingers on the shelter's list,
    or a detail URL that now 404s outright.

    Scoped to qualified, non-removed listings (the handful actually shown in
    the index) with a registered detail parser; browser-discovered listings
    have no static parser to re-fetch with and are skipped, matching
    ``flag_disappeared``'s existing browser exclusion. Unlike that function,
    every qualifying entry is re-fetched regardless of any recheck flag already
    on it (from a prior day, or a card the shelter's own list page dropped this
    run e.g. an on-hold dog) — a direct read of the dog's own page is strictly
    more authoritative than its absence from a list render, so it can resolve a
    stale flag on its own rather than waiting on the LLM.

    A detail page that 404/410s ("http_gone"), one that no longer parses
    ("detail_unparseable"), or one now marked "adopted" ("status_adopted") is
    flagged ``maybe_adopted`` for the LLM to confirm and prune, with the reason
    recorded in ``recheck_reason`` — code detects the anomaly, the LLM confirms
    removal, matching how ``flag_disappeared`` already handles a vanished
    listing. A transient fetch failure (403/5xx/timeout/DNS) is NOT evidence the
    dog is gone, so the entry is left untouched and retried next run. Anything
    else confirms the dog is still up: its status is refreshed, its ``last_seen``
    is bumped to this run (a direct detail-page confirmation is a sighting, so a
    long-on-hold dog dropped from its list render isn't pruned despite being
    confirmed live daily), any recheck flag/reason is cleared, and its URL is
    reported back so the caller can count it as present before running
    ``flag_disappeared`` (whose coarser "missing from the list page" signal would
    otherwise re-flag it).

    Args:
        state: The state document (mutated in place).
        ts: This run's timestamp, recorded as ``last_seen`` on confirmed dogs.

    Returns:
        A (confirmed_urls, flagged) tuple: canonical URLs confirmed still live
        and not adopted, and the entries newly flagged maybe_adopted because
        their detail page is now unreachable or reports "adopted".
    """
    confirmed: set[str] = set()
    flagged: list[dict] = []
    for entry in state["listings"].values():
        if entry.get("verdict") != store.QUALIFIED or entry.get("removed"):
            continue
        module = registry.by_source_kind(entry.get("source_kind"))
        if module is None or not hasattr(module, "parse_detail"):
            continue
        listing = Listing(url=entry["url"])
        try:
            detail = fetch(entry["url"])
            module.parse_detail(detail.body, listing)
        except FetchError as error:
            if error.status in (404, 410):
                _flag(entry, "http_gone", flagged)
            else:
                # 403/5xx/timeout/DNS: a transient fetch gap, not evidence the
                # dog is gone. Leave the entry untouched (an existing flag too)
                # and retry next run — the per-dog analogue of the shelter-outage
                # scoping in flag_disappeared.
                logger.info("recheck: transient fetch failure for %s (%s); not flagging",
                            entry["url"], error)
            continue
        except ParseError:
            # The detail page no longer matches the listing template — often what
            # an adopted-page rewrite looks like.
            _flag(entry, "detail_unparseable", flagged)
            continue
        finally:
            time.sleep(DETAIL_FETCH_DELAY_S)
        if listing.status:
            entry["status"] = listing.status
        if listing.status == "adopted":
            _flag(entry, "status_adopted", flagged)
        else:
            entry["recheck"] = None
            entry["recheck_reason"] = None
            entry["last_seen"] = ts
            confirmed.add(canonical(entry["url"]))
    return confirmed, flagged


def _flag(entry: dict, reason: str, flagged: list[dict]) -> None:
    """Flag an entry maybe_adopted with a reason and record it in ``flagged``.

    Args:
        entry: The state entry to flag (mutated in place).
        reason: The ``recheck_reason`` label explaining why (e.g. "http_gone").
        flagged: The running list of flagged entries this collects into.
    """
    entry["recheck"] = "maybe_adopted"
    entry["recheck_reason"] = reason
    flagged.append(entry)


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

    fetched_shelters = {
        source.shelter for source in run_manifest.sources
        if source.status in (manifest.STATUS_OK, manifest.STATUS_EMPTY_OK)
    }
    detail_confirmed, detail_flagged = _recheck_qualified_details(state, ts)
    if detail_flagged:
        logger.info("flagged %d qualified dog(s) as maybe_adopted (detail page unreachable or adopted)",
                    len(detail_flagged))

    flagged = store.flag_disappeared(state, present | detail_confirmed, ts, fetched_shelters)
    if flagged:
        logger.info("flagged %d qualified dog(s) as maybe_adopted (vanished this run)", len(flagged))
    flagged = flagged + detail_flagged
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


def prune(state_path: str, days: int) -> int:
    """Drop state entries last seen more than ``days`` ago.

    Args:
        state_path: Path to data/state.json.
        days: Retention window in days; entries older than this are removed.

    Returns:
        The number of entries pruned.
    """
    state = store.load_state(state_path)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d-%H%M%S")
    removed = store.prune_stale(state, cutoff)
    if removed:
        store.save_state(state_path, state)
    logger.info("prune: removed %d stale entry(ies) last seen before %s (%d-day retention)",
                len(removed), cutoff, days)
    return len(removed)


def _git_head_version(path: str) -> str | None:
    """Return the HEAD-committed contents of a tracked file, or None if absent.

    Args:
        path: Path to a file inside the git repo.

    Returns:
        The file's contents at HEAD, or None if git is unavailable or the file
        is not tracked at HEAD.
    """
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        rel = os.path.relpath(os.path.abspath(path), root)
        result = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=root, capture_output=True, text=True,
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def index_requires_commit(index_path: str) -> bool:
    """Decide whether the index changes warrant a commit.

    A commit is warranted when the list's membership changed since the last
    commit — a dog was added or dropped. In-place field edits that keep the same
    set of dog URLs are left uncommitted in the working tree. If the HEAD version
    cannot be read, err on the side of committing.

    Args:
        index_path: Path to data/dog-index.md (the freshly-rendered version).

    Returns:
        True if a dog was added or dropped (or the prior version is unavailable).
    """
    with open(index_path, encoding="utf-8") as handle:
        new_md = handle.read()
    old_md = _git_head_version(index_path)
    if old_md is None:
        logger.info("index-check: no committed index to compare against; committing")
        return True
    dropped = render.dropped_dog_urls(old_md, new_md)
    added = render.added_dog_urls(old_md, new_md)
    logger.info("index-check vs HEAD: %d added, %d dropped", len(added), len(dropped))
    return bool(added or dropped)


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

    prune_parser = sub.add_parser("prune", help="drop state entries unseen beyond the retention window")
    prune_parser.add_argument("--state", required=True)
    prune_parser.add_argument("--days", type=int, default=90, help="retention window in days (default 90)")

    collect_parser = sub.add_parser("collect", help="fetch/parse/dedup into state + pending.json")
    collect_parser.add_argument("--shelters", required=True)
    collect_parser.add_argument("--state", required=True)
    collect_parser.add_argument("--out", required=True)

    apply_parser = sub.add_parser("apply", help="merge verdicts.json and re-render the index")
    apply_parser.add_argument("--state", required=True)
    apply_parser.add_argument("--verdicts", required=True)
    apply_parser.add_argument("--index", required=True)

    check_parser = sub.add_parser("index-check", help="print 'commit' if a dog was dropped since HEAD, else 'keep'")
    check_parser.add_argument("--index", required=True)

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.command == "prune":
        n_pruned = prune(args.state, args.days)
        print(f"prune complete: removed {n_pruned} stale entry(ies)")
    elif args.command == "index-check":
        print("commit" if index_requires_commit(args.index) else "keep")
    elif args.command == "collect":
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
