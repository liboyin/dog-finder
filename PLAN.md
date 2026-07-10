# PLAN.md — dog-finder improvement plan (execution hand-over)

- **Finalized:** 2026-07-10. Review evidence is from the 2026-07-05 snapshot (state, index, logs); the daily job has run since, so re-verify specifics like `last_seen` values before relying on them.
- **Authority:** every decision in §3 was confirmed by the owner (2026-07-06/10). Do not re-open them. If you hit a genuine ambiguity §3–§5 doesn't cover, stop and ask the owner (per AGENTS.md).
- **Audience:** an agent executing one or more work packages (§4) with no other context. Read `AGENTS.md` and `README.md` first; this file assumes both.

---

## 1. System facts an executor must know

- **Runtime:** stock macOS Python (`/usr/bin/python3`, 3.9.6), **stdlib only** — no new dependencies. Modern annotations are fine only via the existing `from __future__ import annotations` pattern; no ≥3.10 runtime syntax.
- **Tests:** `/usr/bin/python3 -m unittest discover -s tests` — 59 pass as of hand-over. Must stay green on 3.9.6. New/changed non-test functions need Google-style docstrings; test functions need a one-line docstring (AGENTS.md).
- **Live schedule:** a launchd job runs `scripts/daily-refresh.sh` at 13:00 (machine local = Australia/Sydney) daily. It mutates `data/state.json` + `data/dog-index.md`, and commits **and pushes** `main` when the index's dog membership changed.
- **Run flow:** `prune` → `collect` (writes `runs/<ts>/pending.json` + `fetch_manifest.json`, updates state) → headless `claude` judge (writes `runs/<ts>/verdicts.json`) → `apply` (merges verdicts, re-renders index) → conditional commit/push → usage parsing.
- **Key invariant:** code owns `state.json` and the rendered region of `dog-index.md`; the LLM's only write is `verdicts.json`. Preserve this in every change.

## 2. Ground rules for executors

1. **Sequence with the live job; don't pause it.** Do not `launchctl unload`. Don't leave the repo in a broken or half-migrated condition across 13:00 — finish and commit a work package, or don't start it. (Owner decision §3.9.)
2. **Commit straight to `main`**, one work package per commit, AGENTS.md message format (`Claude: <summary>` + one paragraph; **no** Co-Authored-By). The daily job may auto-push your commits — accepted. Never `git add` more than your own files; `data/*` is routinely dirty from daily runs — leave it unstaged.
3. **Paid verification runs are authorized** when a work package requires end-to-end verification (WP9 does; most don't): invoke `scripts/daily-refresh.sh` manually, capped at `--max-budget-usd 2.5` (the existing cap — do not raise it). Protocol in §6. Prefer unit tests wherever they suffice.
4. **Update documentation in the same commit** that makes it stale (AGENTS.md). Each WP below lists its doc obligations; WP13 covers only *pre-existing* drift.
5. §7 lists things deliberately **out of scope** — do not "improve" them in passing.

---

## 3. Owner decisions (final — treat as constraints)

1. **Labradoodle sources:** labradoodles are categorically excluded (typically >10 kg; also fail the coat rule). Drop the *Australian Labradoodle Association rehoming* source; **keep DoodleAid** (it also carries qualifying small oodles).
2. **Multi-dog URLs:** a URL is *not* a reliable per-dog identifier. When one page hosts several dogs (e.g. PAWS `FosterCareDogs.html`), **all** of them must be representable — the state key must be extended (WP7). Cross-*source* duplicates are a different matter — see 3.
3. **Cross-listing duplicates accepted:** the same dog listed under two sources (own-site + PetRescue) may appear twice. No dedup logic. Document it.
4. **No "code-delegation refactor":** it is not planned. Remove the stale README reference. The judge re-judging browser-shelter dogs every run is an accepted cost. Budget cap stays at $2.50/run — this also caps verification runs.
5. **Browser-dog rechecks** go through the **browser-MCP subagent path**, not WebFetch (browser shelters are exactly the WebFetch-blocked ones). **Removal requires positive evidence** (dead per-dog URL, or explicit adopted/rehomed content); unreachability alone means retry next run.
6. **Source vs shelter split approved** (WP8): the index must show the real shelter, not "PetRescue NSW poodle search (aggregator)".
7. **Prompt intent on state.json:** the judge must never *edit* `state.json`/`dog-index.md` itself; *invoking the deterministic pipeline* (which owns those files) is allowed. Reword the prompt to say exactly that (WP13).
8. **Judge permissions:** replace `--dangerously-skip-permissions` with an explicit allowlist (WP9).
9. **Coordination:** sequence between daily runs (no launchctl changes); commit to main.
10. **CI is dropped** (do not add GitHub Actions). **`flag_disappeared` removal is in scope** (WP12).

Accepted defaults (owner saw these; encode as-is): browser-dog staleness threshold **N = 3 days**; HTTP mapping for rechecks: **404/410 → flag, 403/5xx/timeout → transient (no flag)**; lock contention → **skip the run** with a log line; run-artifact retention **30 days**; index displays the real **shelter** (discovering source stays in state only).

---

## 4. Work packages

Order: WP1–WP6 are independent (any order). WP7 before WP8 (both touch state shape). WP12 after WP2+WP3. WP9 any time, but its paid verification run last in its day. WP13 last.

### WP1 — Confirmed rechecks must count as "seen"
- **Problem:** `_recheck_qualified_details` ([pipeline.py:216-240](src/pipeline.py)) confirms a dog live daily but never bumps `last_seen`; only list cards do ([store.py:117](src/store.py)). A long-on-hold dog delisted from list renders is pruned at 90 days *despite daily confirmations* and silently vanishes from the index.
- **Change:** on the confirmed path (status parsed, not adopted), set `entry["last_seen"]` to the run timestamp (pass `ts` into the function).
- **Accept:** unit test — confirmed entry's `last_seen` == run ts; flagged/unreachable entries' `last_seen` unchanged. Suite green.

### WP2 — `FetchError` carries HTTP status; recheck records a reason
- **Problem:** [fetch.py](src/fetch.py) collapses 404 / 403 / timeout into one string. Permanent 4xx get a pointless retry; `_recheck_qualified_details` flags `maybe_adopted` on *any* failure (mass false flags on an outage day); the judge is told nothing about *why* a dog was flagged and re-fetches to rediscover it.
- **Change:**
  - `FetchError` gains `status: int | None` (from `urllib.error.HTTPError.code`). No retry when `400 <= status < 500`.
  - `_recheck_qualified_details`: 404/410 → flag with `entry["recheck_reason"] = "http_gone"`; explicit adopted status → `"status_adopted"`; 403/5xx/timeout/transport → do **not** flag (per-dog analogue of the shelter-outage philosophy), log it.
  - `flag_disappeared` sets `recheck_reason = "vanished_from_list"`. `apply_verdicts` clears the reason with the flag. Reason rides along into `pending.json` automatically (entries are serialized whole).
  - Prompt (`prompts/daily-refresh.md` step 4): tell the judge it may trust `recheck_reason == "http_gone"` as strong evidence (confirm with one fetch, don't investigate from scratch).
- **Accept:** unit tests for the status mapping (no-retry on 404, retry on 5xx/URLError, flag vs no-flag per status, reasons recorded). Suite green.

### WP3 — Staleness detection for browser-sourced dogs *(after WP2)*
- **Problem:** `flag_disappeared` excludes `source_kind == "browser"` ([store.py:150](src/store.py)) and the detail recheck skips them (no parser) — nothing ever questions a browser-found qualified dog. Evidence (2026-07-05): two of eight index entries were 23 and 35 days stale, shown "available". Their only exit is the 90-day prune — a silent, unconfirmed drop.
- **Change:**
  - In `collect`, flag qualified, non-removed `browser` entries whose `last_seen` is older than **3 days** with `recheck = "maybe_adopted"`, `recheck_reason = "stale_browser"`.
  - Prompt step 4: for `stale_browser` entries, verify via the **browser-MCP subagent path** (WebFetch is expected to fail on these sites — a WebFetch failure is NOT evidence). Emit `removed: true` **only on positive evidence** (per-dog page dead, or page shows adopted/rehomed/absent from its shelter's rendered list). Otherwise emit the dog as still qualified (which bumps `last_seen` via `apply_verdicts`) — inconclusive means leave it and retry next run.
- **Note:** present browser dogs get `last_seen` bumped because the judge re-emits verdicts for re-scraped browser shelters each run (accepted behavior, §3.4) — N=3 tolerates a couple of missed/failed browser passes without false flags.
- **Accept:** unit test for the flagging predicate (age, source_kind, qualified, not already flagged). Prompt change reviewed against §3.5. Suite green.

### WP4 — Stop counting `EMPTY_OK` as an error
- **Problem:** `collect`'s `n_errors` includes `EMPTY_OK` ([pipeline.py:311](src/pipeline.py)); ~6 legitimately-empty shelters read as "6 source error(s)" daily, eroding the fail-loud signal.
- **Change:** `n_errors` = PARSE_ERROR + FETCH_ERROR only; add `n_empty` and print it separately in `main()`'s summary line.
- **Accept:** unit test on the stats dict. Suite green.

### WP5 — Launcher hardening (`scripts/daily-refresh.sh`)
- **Changes (one commit):**
  - Overlap lock: `mkdir`-based lock (zsh-safe, atomic) around the whole body; on contention, log and **exit** (skip the run). Remove the lock dir on exit via trap.
  - `git commit -m "…" -- "$INDEX" "$STATE"` so a user's staged files are never swept in.
  - Line 164: `python3` → `/usr/bin/python3`.
  - `index-check` subparser help in [pipeline.py:448](src/pipeline.py): "…if a dog was **added or dropped** since HEAD…".
- **Accept:** shellcheck-clean-ish (no new warnings); manual double-invocation test shows the second exits immediately; suite green (help-text change).

### WP6 — Drop the Australian Labradoodle Association source
- **Change:** remove that one entry from `config/shelters.json`. Keep DoodleAid. Add a line to README *Assumptions*: breed-specific sources whose breed is categorically disqualified (labradoodle: >10 kg typical + shedding parent) are not monitored.
- **Check:** confirm no state entries have that source as their `shelter` and `verdict: qualified` (none expected — it was browser-path; any strays age out via prune, same as the documented doggierescue case).
- **Accept:** JSON valid; collect dry-run (`python3 -m src.pipeline collect … --out /tmp/…` style, or just the JSON load) passes.

### WP7 — Per-dog identity on shared-URL pages
- **Problem:** state is keyed by `canonical(url)` and [dedup.canonical()](src/dedup.py) strips fragments, so one URL = at most one dog. PAWS lists many dogs on one page (`…/FosterCareDogs.html`); the current entry ("Bindi") occupies the slot and the next PAWS dog the judge emits would silently overwrite her — a lost dog, the exact failure the project exists to avoid.
- **Change (owner decision §3.2):**
  - `canonical()` **preserves the fragment**. Backwards-compatible: no existing state key carries one, and PetRescue card hrefs (`/listings/\d+`) never do.
  - Prompt step 2: when a shelter page lists multiple dogs under one URL, subagents/judge must emit each dog's `url` as `<page-url>#<stable-slug>` (lowercase dog name, hyphenated); the slug must be reproducible run-to-run. Two same-named dogs on one page is accepted as unresolvable.
  - Migration: rekey the existing PAWS entry (`…FosterCareDogs.html` → `…FosterCareDogs.html#bindi`, both key and `url` field) via a one-off `python3 - <<…` against state, committed with the code change. The index URL gains a harmless fragment; the membership "change" will trigger one automated commit — fine.
  - README *Assumptions*: rewrite "a listing URL is a stable, unique identity" to reflect the new rule (URL+fragment for shared pages; cross-source duplicates accepted per §3.3).
- **Accept:** unit tests — `canonical` keeps fragments, drops nothing else new; two fragment-distinct dogs coexist through `apply_verdicts`. Suite green.

### WP8 — Split `source` vs `shelter` *(after WP7)*
- **Problem:** `card.shelter = card.shelter or name` ([pipeline.py:164](src/pipeline.py)) stores the *config source name* as the dog's shelter; 4 of 8 index entries read "Shelter: PetRescue NSW poodle search (aggregator)" — misleading in the one artifact a human trusts.
- **Change:**
  - New entry field `source` = config source name (what found it). `shelter` = the actual organization.
  - PetRescue `parse_detail` extracts the rescue-group name — the detail page links to `/groups/<id>/<Name-Slug>` (confirmed present in `tests/fixtures/petrescue_detail.html`: `groups/10748/RSPCA-Illawarra-Shelter`); prefer the anchor's text if it parses cleanly, else un-slug the URL tail. `ParseError` is NOT warranted if absent — leave `shelter` None (index falls back to `source`).
  - Wollongong parser: `shelter = "Wollongong Pet Connection"` (single-org site). Browser dogs: subagents already return a `shelter` field; `source` comes from the config name at merge.
  - Migration: for all existing entries, set `source` from the current `shelter` value; null out `shelter` where it matches a *config source name that isn't a real org* (the aggregator searches). Qualified dogs will self-heal on the next daily detail recheck (which re-parses details); everything else may keep `shelter = None` harmlessly.
  - `render_block`: show `shelter`, falling back to `source` when unset. `_recheck_qualified_details` and `upsert_listing` refresh `shelter` when the parser now supplies it.
  - `flag_disappeared` scoping uses `source` (that's what `fetched_shelters` contains) — if WP12 already removed it, skip this.
  - Docs: README *Architecture* note on the source/shelter distinction.
- **Accept:** fixture test extracts the group name from `petrescue_detail.html`; render test shows real shelter; migration idempotent (safe to re-run). Suite green. After the next daily run, spot-check the index: aggregator-found dogs show a real shelter.

### WP9 — Judge permission allowlist (replaces `--dangerously-skip-permissions`)
- **Problem:** the judge reads arbitrary scraped web content with unrestricted local authority — prompt injection has file, shell, and git reach. The design needs only a narrow tool set.
- **Confirmed tool usage** (from `runs/20260705-130000/run.stream.jsonl`, main thread): `Agent`, `Read`, `ToolSearch`, `WebFetch`, `Write` — notably **no Bash**. Subagents additionally use browser-MCP tools; enumerate them from a stream that had a browser pass before finalizing (check an `Agent`-spawning run's subagent events, or capture one via the verification run).
- **Change:** in `scripts/daily-refresh.sh`, drop `--dangerously-skip-permissions`; allow: `Read`, `WebFetch`, `Agent`/`Task`, `ToolSearch`, the browser-MCP tools the subagents need, and `Write` scoped to the run directory (`$RUNDIR`) — via `--allowedTools` patterns or a checked-in settings file (executor picks the mechanism the installed CLI version supports; prefer a tracked settings file for auditability). No Bash: in scheduled runs the artifacts always exist, so the prompt's "run collect yourself" escape hatch applies only to interactive use under normal interactive permissions — note that in the prompt (coordinates with WP13's rewording).
- **Verify (paid, §6):** one manual `scripts/daily-refresh.sh` run. Pass = `verdicts.json` written and non-empty, report step-6 output present, **zero permission-denied events** in the stream, browser subagents produced results for at least one `NEEDS_BROWSER` shelter. On failure, revert the script change (single commit) and record the denied tool in the commit message for the next attempt.
- **Docs:** README *Key design decisions* — replace any skip-permissions mention; document the allowlist and why.

### WP10 — Sanitize rendered content; cap verdict fields
- **Problem:** `render_block` interpolates scraped/LLM text into Markdown verbatim (an HTML leak already shipped once — f723508); `apply_verdicts` accepts arbitrary fields for unknown URLs; the index auto-pushes to GitHub.
- **Change:** in [render.py](src/render.py), escape/strip Markdown-significant sequences and raw HTML tags in every interpolated field (a small `_sanitize()` on `_value`'s output path); in `apply_verdicts`, length-cap fields (name/breed/summary etc., e.g. 200 chars) and ignore unknown keys (already implicit — keep it that way).
- **Accept:** unit tests — a name like `](http://evil) <script>` renders inert; over-long summary truncated. Existing index re-renders without visible diffs beyond genuinely dirty data. Suite green.

### WP11 — Run/log retention
- **Change:** launcher deletes `runs/<ts>` directories older than **30 days** (guard the glob so a bad `RUNS` var can't rm elsewhere; only match the `[0-9]{8}-[0-9]{6}` dir shape). Delete the legacy flat `runs/run-2026*` files once, in this commit. Optional: cap `logs/*.log` at a few MB by truncating the head.
- **Docs:** README gains one line under *Key design decisions* (retention windows: 90d state, 30d run artifacts).
- **Accept:** dry-run the find/delete expression against the live `runs/` listing before enabling; next scheduled run logs the sweep.

### WP12 — Remove `flag_disappeared` *(after WP2 + WP3)*
- **Rationale (owner-approved):** since the per-dog detail recheck (137cc35), every qualified non-browser dog is re-fetched directly each run and both failure modes (gone, adopted) are caught there; WP3 covers browser dogs. `flag_disappeared`'s only residual value is parsers lacking `parse_detail` — none exist.
- **Change:** delete `flag_disappeared` and its call site/tests; add a test asserting **every registered parser module exposes `parse_detail`** (this becomes a hard requirement — state it in [base.py](src/parsers/base.py)'s module docstring and README). Add/keep a regression test proving the recheck path flags a vanished-and-404 dog (the case `flag_disappeared` used to catch). The `present` set bookkeeping in `collect` simplifies accordingly.
- **Accept:** suite green; a grep shows no dangling references; README *Architecture* updated in the same commit.

### WP13 — Residual documentation fixes (one commit)
Pre-existing drift not owned by the WPs above:
- README: add a **Test** section (`/usr/bin/python3 -m unittest discover -s tests`; note it must pass on stock 3.9.6). Remove the "code-delegation refactor" sentence (§3.4). Document: cross-listing duplicates accepted; unknown species counts as dog; aggregator searches are NSW-only (`state_id=1`) so ACT coverage rests on the three ACT sources; a missing `state.json` rebuilds silently from empty; dropped sources should clean up their state entries (doggierescue precedent, 9faef8d).
- `data/dog-index.md` (human region, outside the markers): fix the "Monitored shelters" link — it points at `shelters.json` relative to `data/` (broken); correct to `../config/shelters.json`. "cron job" → launchd.
- `prompts/daily-refresh.md`: reword the state.json constraint per §3.7 — e.g. "Never edit `data/state.json` or `data/dog-index.md` yourself; if this run's artifacts are missing (interactive use only), generate them by running the pipeline — the pipeline, not you, writes state."
- `scripts/daily-refresh.sh`: remove the undefined "Phase 2" numbering from comments.
- `src/parse_usage.py`: Google-style docstring for `main()`.

---

## 5. Parameters (single source of truth for the knobs above)

| Knob | Value |
|---|---|
| Browser-dog staleness threshold (WP3) | 3 days |
| Recheck HTTP mapping (WP2) | 404/410 → flag; 403/5xx/timeout → transient, no flag |
| Lock contention (WP5) | skip run, log line |
| Run-artifact retention (WP11) | 30 days |
| State retention (existing) | 90 days — unchanged |
| Judge budget, incl. verification runs | $2.50 (`--max-budget-usd 2.5`) — unchanged |
| Field length cap (WP10) | 200 chars |

## 6. Paid verification-run protocol

1. Run outside the 13:00 window; check no run is in progress (`ps` for `claude`/the script; after WP5, the lock enforces this).
2. Invoke `scripts/daily-refresh.sh` directly. Cost cap is the built-in $2.50.
3. Pass criteria: non-empty `runs/<ts>/verdicts.json`; report present; no permission-denied / auth / watchdog events in `run.stream.jsonl`; `logs/daily-refresh.log` shows a clean apply.
4. A verification run is a *real* run — it may legitimately commit and push an "Automated run" commit. That's fine (owner accepts main auto-publish).
5. If it fails, revert your change (the WPs are single commits) before the next 13:00 slot.

## 7. Out of scope — do not do

- Cross-listing dedup (owner accepted duplicates), including any fuzzy matching.
- Raising/lowering the $2.50 budget cap.
- The "code-delegation refactor" / feeding known URLs to browser subagents to cut re-judging cost.
- CI (explicitly dropped), lint configs, packaging (`pyproject.toml`), new dependencies.
- robots.txt handling; changing scrape cadence/delays.
- Rewriting state to another format; touching the `runs/`+`logs/` gitignore policy.
- Any change letting the LLM write files other than `verdicts.json`.

---

## Appendix A — Review findings not converted to work packages (context)

- **Minor, unfixed (acceptable):** `_detect_status` matches any `>Adopted<` text node on a detail page (false-positive risk on template drift); `apply_verdicts` can create verdict-less orphan entries if the judge omits `verdict` (defensive defaulting would help — fold into WP10 if convenient); `canonical()` doesn't sort query params (unobserved in practice); partial-pagination failure leaves `status=OK` and relies on the detail recheck to prevent false flags (works, ordering-dependent — worth a comment if touching that code).
- **Operational history that shaped the design:** 2026-06-14 hang → watchdog; 2026-06-22→07-04 expired-login outage (12 days silent) → no-verdicts notification; 2026-07-04 02:41 run aborted at $2.51 (`error_max_budget_usd`) — full spend, zero verdicts; cap stays regardless (§3.4).
- **State hygiene:** 109 orphaned `source_kind: "doggierescue"` entries from the deliberate parser removal (9faef8d) age out via the 90-day prune; the lesson (clean up state when dropping a source) is documented via WP13.

## Appendix B — Verified healthy; don't re-litigate

- Atomic state writes (`tempfile` + `os.replace`), sorted/indented JSON for stable diffs.
- Fail-loud parser philosophy: `ParseError` on drift, `EMPTY_OK` distinct from `OK`, per-source manifest; registry host-matching rejects lookalike domains (`sydneypetrescue.com.au` ≠ `petrescue.com.au`).
- Layered vanish detection with shelter-outage scoping and detail-page override (ff44827) — being simplified by WP12, not because it was broken.
- Membership-gated auto-commit verified against git history; watchdog + notification address both observed failure modes.
- Tests: 59 green on the launcher's own interpreter; fixtures and regression coverage are good; docstring discipline holds (one gap → WP13).
- `CLAUDE.md → AGENTS.md` symlink keeps a single source of truth.
