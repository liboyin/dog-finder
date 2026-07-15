# PLAN.md — dog-finder improvement plan (execution hand-over)

- **Finalized:** 2026-07-10. Review evidence is from the 2026-07-05 snapshot (state, index, logs); the daily job has run since, so re-verify specifics like `last_seen` values before relying on them.
- **Authority:** every decision in §3 was confirmed by the owner. Do not re-open them. If you hit a genuine ambiguity that §3–§5 doesn't cover, **stop and ask the owner** (AGENTS.md meta guideline) — do not guess on contract-level questions.
- **Audience:** an agent executing one or more work packages (§4) with no other context. Read `AGENTS.md` and `README.md` first; this file assumes both.

## 0. Progress tracker

Flip a row to `DONE` **in the same commit** that completes the work package, and put `(WPn)` in the commit's one-line summary so history maps to this table.

| WP | Title | Status |
|----|-------|--------|
| WP1 | Confirmed rechecks bump `last_seen` | TODO |
| WP2 | `FetchError` status + `recheck_reason` | TODO |
| WP3 | Browser-dog staleness recheck | TODO |
| WP4 | `EMPTY_OK` out of `n_errors` | TODO |
| WP5 | Launcher hardening | TODO |
| WP6 | Drop Labradoodle Association source | TODO |
| WP12 | Remove `flag_disappeared` | TODO |
| WP7 | Per-dog identity on shared-URL pages | TODO |
| WP8 | Split `source` vs `shelter` | TODO |
| WP10 | Sanitize rendered content | TODO |
| WP11 | Run/log retention | TODO |
| WP9 | Judge permission allowlist | TODO |
| WP13 | Residual documentation fixes | TODO |

**Recommended order** (rows above are in it): WP1–WP6 in any order (independent) → WP12 (needs WP2+WP3; doing it before WP8 means WP8 never touches `flag_disappeared`) → WP7 → WP8 → WP10 → WP11 → WP9 (its paid verification run needs scheduling care) → WP13 last.

---

## 1. System facts an executor must know

### 1.1 Repo map

| Path | Responsibility |
|---|---|
| `src/pipeline.py` | CLI + orchestration: `prune` / `collect` / `apply` / `index-check` subcommands; pagination loop; qualified-detail recheck; git-diff commit gate |
| `src/store.py` | State document: load/save (atomic), upsert/touch, disappearance flagging, prune, pending selection, verdict merge |
| `src/fetch.py` | HTTP GET with UA, timeout, one retry; `FetchError` |
| `src/dedup.py` | `canonical(url)` — the state key function |
| `src/render.py` | Renders qualified entries into the marked region of `data/dog-index.md`; index-membership diff helpers |
| `src/manifest.py` | Per-source run outcomes (`SourceResult`, status constants) |
| `src/parsers/` | `base.py` (Listing, ParseError, text helpers), `petrescue.py`, `wollongong.py`, `registry.py` (host→parser; `SOURCE_KIND`→parser) |
| `src/parse_usage.py` | Parses the judge's stream-json for `logs/usage.log` (Claude-Code-specific; standalone script) |
| `scripts/daily-refresh.sh` | zsh launcher run by launchd: prune → collect → `claude -p` judge (watchdog, budget) → apply → conditional commit/push → usage parse |
| `prompts/daily-refresh.md` | Judge instructions; the launcher extracts everything after the first `---` line |
| `config/shelters.json` | Source list (name, region, listing_url, optional petrescue_url, optional `render: js\|dead`) |
| `data/state.json` | Authoritative record, keyed by `canonical(url)` (~2,240 entries, tracked in git) |
| `data/dog-index.md` | Human artifact; only the `<!-- DOGS:BEGIN/END -->` region is machine-managed |
| `deploy/*.plist` | launchd agent definition (13:00 daily) |
| `runs/<ts>/`, `logs/` | Per-run artifacts and logs — **gitignored**, never stage them |
| `tests/` | `unittest` suite + HTML fixtures in `tests/fixtures/` |

### 1.2 Environment & conventions

- **Runtime:** stock macOS Python (`/usr/bin/python3`, **3.9.6**), stdlib only — no new dependencies, no ≥3.10 runtime syntax. Modern type annotations are fine only because every module has `from __future__ import annotations`; keep that pattern in new files.
- **Tests:** `/usr/bin/python3 -m unittest discover -s tests` — 59 pass at hand-over, runs in <1 s, no network. This is the gate for every commit. The suite is plain `unittest` (pytest is *not* installed for the system interpreter — don't write pytest-isms).
- **Docstrings (AGENTS.md):** Google style for new/changed non-test functions; one-line docstrings for test methods.
- **Test idioms to reuse** (see `tests/test_pipeline.py`): patch `time.sleep` in `setUp` via `mock.patch`; fake fetches with `mock.patch.object(pipeline, "fetch", side_effect=...)` returning `FetchResult(url=u, status=200, body=u, bytes=len(u))`; fake parser modules with `types.SimpleNamespace(parse_list=..., parse_detail=..., SOURCE_KIND=...)`.
- **State entry shape** (see `store._entry_from_listing`): `url, name, breed, age, sex, size, species, location, shelter, fee, status, source_kind, first_seen, last_seen, verdict(pending|qualified|rejected), summary, tags, removed, recheck`. Timestamps are `YYYYMMDD-HHMMSS` strings compared lexically.
- **Key invariant:** code owns `state.json` and the rendered index region; the LLM's only write is `verdicts.json`. Preserve this in every change.

### 1.3 The live schedule

A launchd job (`com.dog-finder.daily-refresh`) runs `scripts/daily-refresh.sh` at **13:00 local (Australia/Sydney)** daily. It mutates `data/*`, and commits **and pushes** `main` when index membership changed. A run takes roughly 5–15 minutes.

## 2. Ground rules for executors

Important note: This plan may be executed on a computer that does not host the daily job. Never set up the job unless explicitly asked to.

1. **Sequence with the live job; don't pause it.** No `launchctl` changes. Don't leave the repo broken or half-migrated across 13:00 — finish and commit a work package, or don't start it. `data/state.json` and `data/dog-index.md` are routinely dirty from "keep-local" daily runs; that is normal — **never stage or revert them**.
2. **Commit straight to `main`**, one WP per commit, AGENTS.md format — `Claude: <one-line summary> (WPn)` plus one explanatory paragraph, **no** Co-Authored-By. The daily job may auto-push your commits; accepted. Do not push manually unless a WP says so.
3. **Sandbox procedure** for exercising the pipeline by hand: copy state first —
   `SCRATCH=$(mktemp -d); cp data/state.json "$SCRATCH/"; /usr/bin/python3 -m src.pipeline collect --shelters config/shelters.json --state "$SCRATCH/state.json" --out "$SCRATCH/out"`.
   Note a real `collect` fetches ~40 live shelter pages over several minutes — prefer unit tests; use live collect only when a WP explicitly calls for it, and never point ad-hoc runs at `data/state.json`.
4. **Paid runs:** only WP9 requires an end-to-end judge run. Protocol in §6; cost ≤ $2.50 per attempt (the built-in cap — do not change it). Everything else is verifiable by unit tests plus, where noted, observing the next scheduled run's output in `logs/daily-refresh.log` and `runs/<ts>/`.
5. **Docs travel with code** (AGENTS.md): each WP lists the README/prompt sections it makes stale; update them in the same commit. WP13 covers only *pre-existing* drift.
6. §7 lists things deliberately **out of scope** — do not fix or improve them in passing, even where the code invites it.

---

## 3. Owner decisions (final — treat as constraints)

1. **Labradoodle sources:** labradoodles are categorically excluded (typically >10 kg; also fail the coat rule). Drop the *Australian Labradoodle Association rehoming* source; **keep DoodleAid** (it also carries qualifying small oodles).
2. **Multi-dog URLs:** a URL is *not* a reliable per-dog identifier. When one page hosts several dogs (e.g. PAWS `FosterCareDogs.html`), **all** must be representable — extend the state key (WP7).
3. **Cross-listing duplicates accepted:** the same dog listed under two sources (own-site + PetRescue) may appear twice in the index. No dedup logic anywhere. Document it.
4. **No "code-delegation refactor":** not planned; remove the stale README reference. The judge re-judging browser-shelter dogs every run is an accepted cost. Budget cap stays at $2.50/run, verification runs included.
5. **Browser-dog rechecks** go through the **browser-MCP subagent path**, not WebFetch (browser shelters are exactly the WebFetch-blocked ones — the 2026-07-05 log shows 8 of them returning 403/JS-blocked). **Removal requires positive evidence** (dead per-dog URL, or explicit adopted/rehomed content, or confirmed absence from the shelter's rendered list); unreachability alone means leave it and retry next run.
6. **Source vs shelter split approved** (WP8): the index must show the real shelter, not "PetRescue NSW poodle search (aggregator)".
7. **Prompt intent on state.json:** the judge must never *edit* `state.json`/`dog-index.md` itself; *invoking the deterministic pipeline* (which owns those files) is allowed. Reword the prompt accordingly (WP13).
8. **Judge permissions:** replace `--dangerously-skip-permissions` with an explicit allowlist (WP9).
9. **Coordination:** sequence between daily runs; commit to main.
10. **CI is dropped** (no GitHub Actions). **`flag_disappeared` removal is in scope** (WP12).

Accepted defaults — encode as-is, see also §5: staleness threshold N = 3 days; 404/410 flag vs 403/5xx/timeout transient; lock contention skips the run; 30-day run-artifact retention; index displays real shelter with source kept in state.

---

## 4. Work packages

### WP1 — Confirmed rechecks must count as "seen"
- **Problem:** `_recheck_qualified_details` ([pipeline.py:182-240](src/pipeline.py)) confirms a dog live daily but never bumps `last_seen`; only list cards do, via `store.touch`. A long-on-hold dog delisted from list renders (PetRescue hides on-hold dogs from search results) is pruned at 90 days *despite daily confirmations* and silently vanishes from the index.
- **Change:** add a `ts: str` parameter to `_recheck_qualified_details`; on the confirmed path (detail parsed, status != adopted) set `entry["last_seen"] = ts`. Update the call site in `collect` (it has `ts` in scope) and the existing tests in `tests/test_pipeline.py` (`RecheckQualifiedDetailsTest` and `CollectRecheckIntegrationTest` call the old signature).
- **Tests:** confirmed entry's `last_seen` == run ts; flagged (404/adopted) entries' `last_seen` unchanged.
- **Commit summary:** `Claude: count a confirmed detail recheck as a sighting (WP1)`

### WP2 — `FetchError` carries HTTP status; rechecks record a reason
- **Problem:** [fetch.py](src/fetch.py) collapses 404 / 403 / timeout into one string. Permanent 4xx get a pointless retry; `_recheck_qualified_details` flags `maybe_adopted` on *any* failure (mass false flags on an outage day); the judge is told nothing about *why* a dog was flagged and re-investigates from scratch.
- **Change, fetch side:** give `FetchError` an optional `status: int | None` attribute (custom `__init__(message, status=None)`). In `fetch()`, catch `urllib.error.HTTPError` **before** `URLError` (it's a subclass — catch order matters), record `error.code`, and skip the retry loop when `400 <= code < 500`. Keep the existing exception tuple for the transport cases.
- **Change, pipeline side:** in `_recheck_qualified_details`, branch on the caught error:
  - `FetchError` with status 404/410 → flag, `entry["recheck_reason"] = "http_gone"`.
  - `ParseError` (detail page no longer matches the template — often what an adopted-page rewrite looks like) → flag, reason `"detail_unparseable"` (preserves current behavior, now labeled).
  - `FetchError` with any other/no status (403, 5xx, timeout, DNS) → **do not flag**; log at INFO and leave the entry untouched (per-dog analogue of the shelter-outage rule).
  - Parsed page with `status == "adopted"` → flag, reason `"status_adopted"`.
  - `flag_disappeared` sets reason `"vanished_from_list"` (dies with WP12 — fine either way).
  - `apply_verdicts` clears `recheck_reason` wherever it clears `recheck`. The reason reaches `pending.json` automatically (entries serialize whole). New-entry template in `_entry_from_listing` gains `"recheck_reason": None`.
- **Prompt:** step 4 of `prompts/daily-refresh.md`: the judge may treat `recheck_reason: "http_gone"` as strong evidence — one confirming fetch, not a full investigation.
- **Tests:** no-retry on 404 (assert single attempt via a counting side_effect); retry preserved on URLError; each reason recorded; 403/timeout does not flag and does not clear an existing flag.
- **Commit summary:** `Claude: carry HTTP status on FetchError and record recheck reasons (WP2)`

### WP3 — Staleness detection for browser-sourced dogs *(after WP2)*
- **Problem:** `flag_disappeared` excludes `source_kind == "browser"` ([store.py:150](src/store.py)) and the detail recheck skips them (no registered parser) — nothing ever questions a browser-found qualified dog. Evidence (2026-07-05): two of eight index entries were 23 and 35 days stale, both shown "available". Their only exit was the 90-day prune — a silent, unconfirmed drop.
- **Change:** new function in `store.py` (keep it separate from `flag_disappeared` so WP12's removal is clean):
  `flag_stale_browser(state, cutoff) -> list[dict]` — flags qualified, non-removed, `source_kind == "browser"` entries with no current `recheck` whose `last_seen < cutoff`, setting `recheck = "maybe_adopted"`, `recheck_reason = "stale_browser"`. In `collect`, compute the cutoff exactly as `prune` does (`datetime.now() - timedelta(days=3)`, same string format) and call it alongside the other flagging; include the count in the log line and `n_maybe_adopted`.
- **Prompt:** step 4: entries with `recheck_reason: "stale_browser"` belong to JS/blocked sites — verify via the **browser-MCP subagent path**, not WebFetch (a WebFetch failure is NOT evidence). Emit `removed: true` only on positive evidence (§3.5). Otherwise re-emit the dog as qualified — that bumps `last_seen` through `apply_verdicts` and unflags it. Inconclusive → leave it; it retries next run.
- **Why N=3 is safe:** present browser dogs get `last_seen` bumped every run the browser pass re-emits them (accepted behavior, §3.4), so 3 days tolerates a couple of failed browser passes without false flags, while capping staleness at days instead of months.
- **Tests:** flagging predicate over age/source_kind/verdict/removed/existing-flag combinations; cutoff arithmetic.
- **Commit summary:** `Claude: flag stale browser-sourced dogs for recheck (WP3)`

### WP4 — Stop counting `EMPTY_OK` as an error
- **Problem:** `collect`'s `n_errors` includes `EMPTY_OK` ([pipeline.py:311](src/pipeline.py)); ~6 legitimately-empty shelters read as "6 source error(s)" every day, training humans to ignore the one signal that matters.
- **Change:** `n_errors` = `PARSE_ERROR` + `FETCH_ERROR` only; add `n_empty`; extend `main()`'s collect summary line (`… X empty, Y source error(s)`).
- **Tests:** stats dict assertions over a mixed manifest.
- **Commit summary:** `Claude: report empty sources separately from source errors (WP4)`

### WP5 — Launcher hardening (`scripts/daily-refresh.sh` + one help string)
- **Changes (one commit):**
  - **Overlap lock:** `mkdir "$DIR/.run.lock"` (atomic; zsh-safe) at the top; on failure, if the lock dir's mtime is older than 4 hours (`stat -f %m`, macOS syntax) treat it as stale from a crash — remove and retake; otherwise log `"another run holds the lock; skipping"` and exit 0. Release with `trap 'rmdir "$DIR/.run.lock" 2>/dev/null' EXIT`.
  - **Scoped commit:** `git commit -m "…" -- "$INDEX" "$STATE"` so files a human left staged are never swept into an automated commit.
  - Line 164: bare `python3` → `/usr/bin/python3` (only inconsistency in the file).
  - [pipeline.py:448](src/pipeline.py) `index-check` help: "…if a dog was **added or dropped** since HEAD…".
- **Verify:** run the script twice concurrently against the sandbox pattern is impractical (it invokes the judge) — instead test the lock logic by extracting it verbatim into a throwaway script, or start `daily-refresh.sh`, immediately invoke it again, confirm the second exits on the lock, then kill the first and confirm the trap released the lock. Suite green (help text).
- **Commit summary:** `Claude: add a run lock and scope the automated commit (WP5)`

### WP6 — Drop the Australian Labradoodle Association source
- **Change:** remove that entry from `config/shelters.json` (it's the `australianlabradoodleassoc.org.au` one). Keep DoodleAid. README *Assumptions* gains one line: breed-specific sources whose breed is categorically disqualified (labradoodle: >10 kg typical + shedding parent) are not monitored.
- **Check:** `python3 -c "import json; json.load(open('config/shelters.json'))"`; then confirm no qualified live state entry names it as shelter: none expected (it was browser-path; strays age out via prune, same as the documented doggierescue case).
- **Commit summary:** `Claude: drop the Labradoodle Association source (WP6)`

### WP12 — Remove `flag_disappeared` *(after WP2 + WP3; before WP8 recommended)*
- **Rationale (owner-approved):** since 137cc35, every qualified non-browser dog is detail-rechecked directly each run and both failure modes (gone, adopted) are caught there; WP3 covers browser dogs. `flag_disappeared`'s only residual value is parsers lacking `parse_detail` — none exist, and this WP makes that a requirement.
- **Change:**
  - Delete `store.flag_disappeared` and its tests; in `collect`, remove the call plus the now-unused bookkeeping: the `present` set threaded through `_collect_source`, the `fetched_shelters` computation, and the `detail_confirmed` half of the recheck return value (`_recheck_qualified_details` then only returns `flagged` — simplify its signature and docstring).
  - Add a registry test asserting **every module in `registry._REGISTRY` exposes `parse_detail`** — this is now a hard requirement for vanish detection; state it in [base.py](src/parsers/base.py)'s module docstring ("parsers MUST define parse_detail") and in README *Architecture*.
  - Keep/extend a regression test proving the recheck path flags a dog that vanished from its list **and** whose detail URL died (the exact case `flag_disappeared` existed for).
- **Commit summary:** `Claude: fold vanish detection into the detail recheck (WP12)`

### WP7 — Per-dog identity on shared-URL pages
- **Problem:** state is keyed by `canonical(url)` and [dedup.canonical()](src/dedup.py) strips fragments, so one URL = at most one dog. PAWS lists many dogs on one page; the current entry ("Bindi", key `https://www.paws.com.au/FosterCare/FosterCareDogs.html`) occupies the slot, and the next PAWS dog the judge emits would silently overwrite her via `apply_verdicts` — a lost dog, the failure this project exists to prevent.
- **Change:**
  - `canonical()` **preserves the fragment**: pass `parts.fragment` through `urlunsplit` instead of `""`. Backwards-compatible with all existing keys (none carries a fragment; PetRescue card hrefs are `/listings/\d+`). **The existing test asserts the old behavior — update `tests/test_dedup.py::test_trailing_slash_and_fragment_removed`** (rename it; fragment is now kept, docstring accordingly).
  - Prompt step 2 (browser instructions): when a shelter page lists multiple dogs under one URL, emit each dog's `url` as `<page-url>#<slug>` where slug = dog's name lowercased, non-alphanumeric runs collapsed to single hyphens (e.g. `#bindi`); the slug must be reproducible run-to-run so re-scrapes merge. Two identically-named dogs on one page is accepted as unresolvable.
  - Prompt step 4 note: a `#fragment` URL can't be fetched more precisely than its page — verifying such a dog means checking the page still shows that dog.
  - **Migration** (same commit, then delete the throwaway): rekey the PAWS entry —
    ```
    /usr/bin/python3 - <<'EOF'
    import json
    p = 'data/state.json'
    s = json.load(open(p))
    old = 'https://www.paws.com.au/FosterCare/FosterCareDogs.html'
    e = s['listings'].pop(old, None)
    if e:
        e['url'] = old + '#bindi'
        s['listings'][old + '#bindi'] = e
        json.dump(s, open(p, 'w'), indent=2, ensure_ascii=False, sort_keys=True)
        print('migrated')
    else:
        print('entry absent — verify state before proceeding')
    EOF
    ```
    Run it between daily runs; the changed URL will register as a drop+add at the next daily run and trigger one automated commit — expected and fine. (Committing the migrated `state.json` in this WP's commit is acceptable as the documented exception to ground rule 1 — say so in the commit paragraph.)
  - README *Assumptions*: rewrite "a listing URL is a stable, unique identity" — per-dog URLs where the site provides them; `url#name-slug` for shared pages; cross-source duplicates accepted (§3.3).
- **Tests:** `canonical` keeps fragments and still lowercases host / strips trailing slash; two fragment-distinct dogs on one page coexist through `apply_verdicts` (create both, assert two entries).
- **Commit summary:** `Claude: key shared-page dogs by URL fragment (WP7)`

### WP8 — Split `source` vs `shelter` *(after WP7; simpler after WP12)*
- **Problem:** `card.shelter = card.shelter or name` ([pipeline.py:164](src/pipeline.py)) stores the *config source name* as the dog's shelter — 4 of 8 index entries read "Shelter: PetRescue NSW poodle search (aggregator)", misleading in the one artifact a human trusts.
- **Change:**
  - **State:** new field `source` (the config source name — what *found* the dog); `shelter` becomes the actual organization or `None`. Thread it as a parameter: `upsert_listing(state, card, ts, source_kind, source)`; `_entry_from_listing` records both. Stop overwriting `card.shelter` with the source name in `_collect_source`; pass `name` as `source` instead. Browser dogs: subagents already return a real `shelter`; `apply_verdicts` stores `source_kind` today — have it also accept an optional `source` field from the verdict, defaulting to `None`.
  - **PetRescue parser:** `parse_detail` extracts the rescue group. The detail page links to `/groups/<id>/<Name-Slug>` (confirmed in `tests/fixtures/petrescue_detail.html`: `groups/10748/RSPCA-Illawarra-Shelter`). Prefer the anchor's inner text (`strip_tags`, `clean`); if empty, un-slug the URL tail (`-` → space). Absent group link → leave `listing.shelter` None; this is **not** a `ParseError`.
  - **Wollongong parser:** `parse_detail` sets `listing.shelter = "Wollongong Pet Connection"` (single-org site).
  - **Recheck refreshes shelter:** in `_recheck_qualified_details`, after a successful parse, copy `listing.shelter` into the entry when the parser supplied one — this is what backfills existing qualified dogs automatically on the next daily run.
  - **Render:** `render_block` shows `entry["shelter"] or entry["source"] or "unknown"`.
  - **Migration** (same commit; idempotent): for every entry, if `"source"` not present: `entry["source"] = entry.get("shelter")`; then set `entry["shelter"] = None` where its value is one of the aggregator source names (the eight `PetRescue NSW … search (aggregator)` names — read them from `config/shelters.json` rather than hard-coding). Non-aggregator names (real shelters/groups) stay in both fields — harmless and mostly correct.
  - **Docs:** README *Architecture* — one paragraph on the source/shelter distinction and the accepted consequence that cross-source duplicates are visible as two entries (§3.3).
- **Tests:** fixture test — group name extracted from `petrescue_detail.html`; render fallback chain; migration idempotence (run twice over a fixture state, same result); recheck copies a newly-parsed shelter into the entry.
- **Verify:** after the next scheduled run, aggregator-found qualified dogs in `data/dog-index.md` show a real shelter (the recheck backfill).
- **Commit summary:** `Claude: record discovering source separately from the shelter (WP8)`

### WP10 — Sanitize rendered content; validate verdict input
- **Problem:** `render_block` interpolates scraped/LLM text into Markdown verbatim (an HTML leak already shipped once — f723508); `apply_verdicts` accepts arbitrary fields for unknown URLs; the index auto-pushes to GitHub.
- **Change:**
  - [render.py](src/render.py): a `_sanitize(text)` applied to every interpolated field (fold into `_value`): strip HTML tags (reuse `base._TAG_RE`-style regex), escape `[` and `]` (`\[`, `\]`), collapse whitespace. URLs are handled by validation below, not escaping.
  - [store.py](src/store.py) `apply_verdicts`: ignore a verdict whose `url` doesn't start with `http://`/`https://` or contains whitespace/`<`/`>` (log a warning); cap every stored string field at **200 chars** (truncate; summaries are ≤25 words by contract anyway). Optionally default missing `verdict` to `"pending"` on newly-created entries so they can't become invisible orphans (see Appendix A).
- **Tests:** a name like `](http://evil) <script>x</script>` renders inert; over-long summary truncated; junk-URL verdict ignored; legitimate fields (locations with parentheses, fees with `$`) render unchanged.
- **Note:** re-rendering the existing index must produce no diffs beyond genuinely dirty data — eyeball `git diff data/dog-index.md` after a sandbox `apply` (§2.3 pattern, verdicts can be an empty `[]` file) before committing.
- **Commit summary:** `Claude: sanitize rendered fields and validate verdict input (WP10)`

### WP11 — Run/log retention
- **Change:** in the launcher, after the run completes:
  - `find "$RUNS" -maxdepth 1 -type d -name '[0-9]*-[0-9]*' -mtime +30 -exec rm -rf {} +` — guarded by `[ -d "$RUNS" ]`; the name pattern plus `-maxdepth 1` keeps it scoped even if `$RUNS` were empty/misset. Match the `YYYYMMDD-HHMMSS` shape.
  - Delete the legacy flat `runs/run-2026*` files once, by hand, in this commit's session (they predate the per-run directory layout).
  - Optional: skip log truncation — logs are 424 KB after six weeks; revisit only if they become a problem (don't gold-plate).
- **Docs:** README *Key design decisions*: one line stating both retention windows (90 d state, 30 d run artifacts).
- **Verify:** dry-run the `find` with `-print` instead of `-exec rm` first and eyeball the list; after the next scheduled run, confirm old dirs are gone and the newest survived.
- **Commit summary:** `Claude: prune run artifacts older than 30 days (WP11)`

### WP9 — Judge permission allowlist (replaces `--dangerously-skip-permissions`)
- **Problem:** the judge reads arbitrary scraped web content with unrestricted local authority — prompt injection has file, shell, and git reach. The design needs only a narrow tool set.
- **Known facts:** the main thread of run `20260705-130000` used exactly `Agent`, `Read`, `ToolSearch`, `WebFetch`, `Write` — **no Bash**. Subagent (Haiku) tool calls do **not** appear in the parent stream, so the browser-MCP tool names must be discovered iteratively: expect Playwright-MCP and/or Claude-in-Chrome tool patterns (`mcp__playwright__*` / `mcp__claude-in-chrome__*`), and refine from denials.
- **Change:** in `scripts/daily-refresh.sh`, drop `--dangerously-skip-permissions`; grant via `--allowedTools` (or a **tracked** `.claude/settings.json` — prefer the settings file for auditability; check `claude --help` of the installed version for exact syntax): `Read`, `WebFetch`, `Agent`/`Task`, `ToolSearch`, `Write` scoped to the runs directory (pattern-scoped permission, e.g. `Write(runs/**)`), and the browser-MCP tool patterns. **No Bash**: scheduled runs always have their artifacts (the launcher runs collect first); the prompt's "generate them yourself" escape hatch is interactive-only and runs under interactive permissions — add that qualifier to the prompt in this commit (coordinates with WP13's rewording; whichever lands second reconciles).
- **Verify (paid, §6):** one manual launcher run. Pass = non-empty `verdicts.json`; report present; **zero permission-denied events** in `run.stream.jsonl` (grep for `permission`/`denied`); at least one `NEEDS_BROWSER` shelter produced browser results. On failure: revert the script/settings commit immediately (single commit — clean revert), record the denied tool names in the revert commit's paragraph, and retry another day with the amended list. Budget each attempt ≤ $2.50; expect 1–3 attempts.
- **Docs:** README *Key design decisions* — replace the implicit skip-permissions posture with the allowlist and its rationale.
- **Commit summary:** `Claude: run the judge under a tool allowlist (WP9)`

### WP13 — Residual documentation fixes (one commit, last)
Pre-existing drift not owned by the WPs above — skip anything a prior WP already fixed:
- **README:** add a **Test** section (`/usr/bin/python3 -m unittest discover -s tests`; must pass on stock 3.9.6). Remove the "code-delegation refactor" clause from *Key design decisions* (§3.4). Add to *Assumptions*: cross-listing duplicates accepted; unknown species counts as a dog (`base.is_dog`); aggregator searches are NSW-only (`state_id=1`) so ACT coverage rests on the three ACT sources; a missing `state.json` silently rebuilds from empty; dropped sources should clean up their state entries (doggierescue precedent, 9faef8d).
- **`data/dog-index.md`** (human region, outside the markers — edit directly): the "Monitored shelters" link points at `shelters.json` (broken; resolves inside `data/`) — fix to `../config/shelters.json`; "cron job" → launchd agent.
- **`prompts/daily-refresh.md`:** reword the state constraint per §3.7 — e.g. "Never edit `data/state.json` or `data/dog-index.md` yourself; if this run's artifacts are missing (interactive use only), generate them by running the pipeline — the pipeline, not you, writes state."
- **`scripts/daily-refresh.sh`:** remove the undefined "Phase 2" numbering from comments.
- **`src/parse_usage.py`:** Google-style docstring for `main()`.
- **Commit summary:** `Claude: fix accumulated documentation drift (WP13)`

---

## 5. Parameters (single source of truth for the knobs above)

| Knob | Value |
|---|---|
| Browser-dog staleness threshold (WP3) | 3 days |
| Recheck HTTP mapping (WP2) | 404/410 → flag `http_gone`; adopted status → `status_adopted`; unparseable detail → `detail_unparseable`; 403/5xx/timeout/DNS → transient, no flag |
| `recheck_reason` values | `http_gone`, `status_adopted`, `detail_unparseable`, `vanished_from_list` (dies with WP12), `stale_browser` |
| Lock contention (WP5) | skip run, log line; stale lock auto-broken after 4 h |
| Run-artifact retention (WP11) | 30 days |
| State retention (existing) | 90 days — unchanged |
| Judge budget, incl. verification runs | $2.50 (`--max-budget-usd 2.5`) — unchanged |
| Field length cap (WP10) | 200 chars |
| Fragment slug rule (WP7) | dog name, lowercased, non-alphanumeric runs → single `-` |

## 6. Paid verification-run protocol (WP9 only)

1. Run well clear of the 13:00 window; confirm nothing is running (`pgrep -f daily-refresh.sh`; after WP5 the lock also enforces this).
2. Invoke `scripts/daily-refresh.sh` directly from the repo root. Cost is bounded by the built-in $2.50 cap.
3. Pass criteria: non-empty `runs/<ts>/verdicts.json`; `report.txt` present; no permission-denied / auth / watchdog lines in `run.stream.jsonl` or `logs/daily-refresh.log`; browser results for ≥1 `NEEDS_BROWSER` shelter; clean `apply`.
4. A verification run is a *real* run — it may legitimately commit and push an "Automated run" commit. Accepted.
5. On failure, revert your WP9 commit before the next 13:00 slot.

## 7. Out of scope — do not do

- Cross-listing dedup (owner accepted duplicates), including any fuzzy matching.
- Raising/lowering the $2.50 budget cap.
- The "code-delegation refactor" / feeding known URLs to browser subagents to cut re-judging cost.
- CI (explicitly dropped), lint configs, packaging (`pyproject.toml`), new dependencies, pytest.
- robots.txt handling; changing scrape cadence, delays, or page caps.
- Rewriting state to another format; changing the `runs/`+`logs/` gitignore policy.
- Any change letting the LLM write files other than `verdicts.json`.
- Decoupling the judge from Claude Code (engine adapters, etc.) — discussed with the owner and explicitly deferred.

---

## Appendix A — Known minor issues deliberately left (context, not tasks)

- `_detect_status` matches any `>Adopted<` / `>On hold<` text node anywhere on a detail page — false-positive risk on template drift; acceptable.
- `apply_verdicts` can create verdict-less orphan entries if the judge omits `verdict` on a new URL (entry is then neither pending nor rendered). WP10's optional defaulting addresses it; otherwise accepted.
- `canonical()` doesn't sort query params (two param orderings won't dedup) — unobserved in practice.
- Partial-pagination failure (page 3 of N dies) leaves `status=OK`; dogs on unfetched pages are protected from false flagging only by the detail recheck running first. If WP12 touches nearby code, a comment there is welcome; no behavior change wanted.
- 109 orphaned `source_kind: "doggierescue"` entries from the deliberate parser removal (9faef8d) age out via the 90-day prune; no action.
- Operational history that shaped the design (don't undo): 2026-06-14 hang → watchdog; 2026-06-22→07-04 silent auth outage → no-verdicts notification; 2026-07-04 budget abort at $2.51 → cap stays anyway (§3.4).

## Appendix B — Verified healthy; don't re-litigate

- Atomic state writes (`tempfile` + `os.replace`), sorted/indented JSON for stable diffs.
- Fail-loud parser philosophy: `ParseError` on drift, `EMPTY_OK` distinct from `OK`, per-source manifest; registry host-matching rejects lookalike domains (`sydneypetrescue.com.au` ≠ `petrescue.com.au`).
- Layered vanish detection with shelter-outage scoping and detail-page override (ff44827) — WP12 simplifies it because it became redundant, not because it was broken.
- Membership-gated auto-commit verified against git history; watchdog + notification address both observed failure modes.
- Tests: 59 green on the launcher's own interpreter; fixtures and regression coverage are good; docstring discipline holds (one gap → WP13).
- `CLAUDE.md → AGENTS.md` symlink keeps a single source of truth.
