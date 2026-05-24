# Hand-over: dog-finder project

This document is a complete, self-contained brief for setting up a proper Git repo for the
**dog-finder** project and (later) refactoring it to delegate deterministic parsing to code.
A fresh session with no prior context should be able to execute **Phase 1** from this document
alone. **Phase 2** is a design spec to implement afterwards.

Author date: 2026-05-25. Machine: macOS, user shell `zsh`, `/usr/bin/python3` = 3.9.6,
`claude` = `/usr/local/bin/claude` v2.1.142 (native binary, no node).

> **Naming note:** the project is **dog-finder**. The repo root will be `~/dog-finder`. The
> code currently lives in `~/poodle-index` (the old name) and Phase 1 renames it. The
> human-reviewed output file stays named `dog-index.md`.

---

## 1. What this project is

A **daily-refreshed adoption index** of small, low-shedding, low-odour dogs available at
shelters within ~4 hours of Sydney (NSW + ACT). A scheduled job runs every night at
**21:00 Australia/Sydney**, scrapes monitored shelter sites, and maintains a single
human-readable markdown index (`dog-index.md`): prepending newly-found qualifying dogs and
pruning ones that have been adopted. **A human reviews the index** — this is a
human-in-the-loop workflow.

It runs **locally** via macOS `launchd` (NOT the cloud "Routines" feature, which can't reach
local files). It lives **outside `~/Documents`** because macOS TCC blocks launchd agents from
the Documents folder. The project is **self-contained under `~/dog-finder`** and references no
paths outside that directory.

---

## 2. Decided architecture & principles (agreed with the user)

1. **Keep the workflow LLM-driven.** The top-level Claude agent stays the planner/coordinator
   and does all *judgment* (does this breed/cross meet the low-shed criteria? write the summary,
   resolve geo-borderline cases, classify adoption status, edit the index). The coordinator
   **may still spawn Haiku subagents** — in particular to **drive the Claude-in-Chrome or
   Playwright MCP** for JS-rendered sites (see §7.2), and for any other parallelizable work.
2. **Delegate deterministic logic to code.** Fetching static pages, parsing listing cards into
   structured records, dedup against the known-URL set, and building the run manifest are rote
   and belong in Python — NOT in model context. Today the LLM ingests ~1.1M tokens of raw HTML
   per run (see §8); moving parse to code is expected to cut that ~10×.
3. **Fail loud, human fixes externally.** Parsers **raise on markup drift** and the run
   **records the error in the manifest and skips that source**, then continues. The human fixes
   the parser code out-of-band and commits. Critically, "HTTP 200 but 0 cards parsed" must also
   be treated as an error so a silently-broken parser can't quietly drop a shelter.
4. **JS-rendered sites use a browser MCP.** `render:js` shelters are handled by the LLM via
   **Playwright MCP or Claude-in-Chrome MCP** (both available to the user), not plain HTTP —
   typically driven through a Haiku subagent (see principle 1).
5. **Python deps: stdlib-first, `uv` if needed (decision deferred).** Start by attempting the
   parsers with the standard library (`urllib.request` + `html.parser`/`re`) — that needs no
   venv and runs on `/usr/bin/python3` immediately. **If** parsing proves too painful in stdlib
   and an external dep (e.g. `beautifulsoup4`, `lxml`) is genuinely warranted, **manage it with
   [`uv`](https://docs.astral.sh/uv/)** — a `pyproject.toml` + `uv.lock` at the repo root, run
   via `uv run`. uv is preferred over a hand-rolled `python -m venv` (faster, lockfile,
   reproducible, manages the interpreter). Either way the venv stays gitignored. Make the call
   when actually writing the parsers in Phase 2, preferring the lowest-dependency option that
   keeps the parser code maintainable.
6. **Budget cap: `--max-budget-usd 2.5`.** The `claude` invocation aborts cleanly (logged) if a
   run would exceed US$2.50, rather than being throttled into a death-crawl. Added in Phase 1.
7. **Git tracks the valuable artifact.** History over `dog-index.md` is the record of which dogs
   appeared/were adopted over time. Code, config, and the prompt are tracked too; logs and run
   artifacts are ignored.

---

## 3. Current on-disk state (before repo setup)

All real files currently live in **`~/poodle-index/`** (Phase 1 renames this to `~/dog-finder/`):

| File | Role |
|---|---|
| `dog-index.md` | The human-reviewed output index. **Most valuable file.** |
| `shelters.json` | 60 entries: `{name, region, listing_url, petrescue_url?, render?}`. `render` ∈ {absent/`static`, `js` (5), `dead` (1)}. |
| `daily-refresh-prompt.md` | The agent prompt. Header (lines 1–5) + `---` + the actual prompt. **Still describes the OLD Haiku-subagent scraping architecture** (see §7). Header text still says "poodle-index". |
| `daily-refresh.sh` | launchd launcher. `DIR="$HOME/poodle-index"`. Extracts prompt after first `---`, runs `claude -p ... --model sonnet --dangerously-skip-permissions --output-format stream-json --verbose`, then calls `parse_usage.py`. No budget cap yet. |
| `parse_usage.py` | Parses the final `result` event from a stream-json run → aggregate + per-model usage block to `usage.log`; writes report text. Path-agnostic (takes argv). |
| `daily-refresh.log`, `daily-refresh.launchd.log`, `usage.log` | Logs. |
| `runs/run-<ts>.stream.jsonl`, `runs/run-<ts>.report.txt` | Per-run artifacts (8 files currently). |

**launchd agent:** `~/Library/LaunchAgents/com.poodle-index.daily-refresh.plist`
- Label: `com.poodle-index.daily-refresh` (Phase 1 renames to `com.dog-finder.daily-refresh`)
- `ProgramArguments`: `/bin/zsh ~/poodle-index/daily-refresh.sh`
- `StartCalendarInterval`: Hour 21, Minute 0 (local time = 9pm AEST)
- `StandardOutPath`/`StandardErrorPath`: `~/poodle-index/daily-refresh.launchd.log`
- Loaded in `gui/$(id -u)` domain.

**No git repo exists yet.**

---

## 4. Target repo structure

```
~/dog-finder/                         # git repo root (TCC-safe; self-contained)
├── README.md
├── .gitignore
├── HANDOVER.md                       # this file (commit it, or delete once Phase 2 lands)
├── pyproject.toml                    # ONLY if external deps are adopted in Phase 2 (uv-managed); + uv.lock
├── config/
│   └── shelters.json
├── prompts/
│   └── daily-refresh.md              # moved from daily-refresh-prompt.md
├── src/
│   ├── parse_usage.py                # moved as-is
│   ├── pipeline.py                   # Phase 2: CLI entrypoint (fetch→parse→dedup→candidates.json+manifest)
│   ├── fetch.py                      # Phase 2: HTTP fetch + render routing
│   ├── parsers/
│   │   ├── petrescue.py              # Phase 2
│   │   └── generic.py                # Phase 2
│   ├── dedup.py                      # Phase 2
│   └── manifest.py                   # Phase 2
├── scripts/
│   └── daily-refresh.sh              # moved + path-updated + budget cap
├── deploy/
│   └── com.dog-finder.daily-refresh.plist   # tracked copy; install to ~/Library/LaunchAgents
├── data/
│   └── dog-index.md                  # moved from repo root
├── runs/                             # gitignored (per-run artifacts; switch to runs/<ts>/ folders)
└── logs/                             # gitignored (daily-refresh.log, *.launchd.log, usage.log)
```

In Phase 1, create `src/parsers/` with a `.gitkeep`; the parser modules arrive in Phase 2.

---

## 5. PHASE 1 — repo setup (execute this now)

Do it as one atomic reorganization, then re-validate launchd. All paths use `~`.

### 5.1 Rename the project directory
```
mv ~/poodle-index ~/dog-finder
cd ~/dog-finder
```

### 5.2 Create directories and move files
```
mkdir -p config prompts src/parsers scripts deploy data logs
mv shelters.json             config/shelters.json
mv daily-refresh-prompt.md   prompts/daily-refresh.md
mv parse_usage.py            src/parse_usage.py
mv daily-refresh.sh          scripts/daily-refresh.sh
mv dog-index.md              data/dog-index.md
mv daily-refresh.log         logs/daily-refresh.log
mv daily-refresh.launchd.log logs/daily-refresh.launchd.log
mv usage.log                 logs/usage.log
touch src/parsers/.gitkeep
# runs/ stays at runs/ (gitignored)
```

### 5.3 Update ALL path references (do every one)

**a) `prompts/daily-refresh.md`** — the two absolute paths in the "## Files" section:
- index path → `~/dog-finder/data/dog-index.md`
- shelter list path → `~/dog-finder/config/shelters.json`
Also update stale "poodle-index" naming in the header line to "dog-finder".

**b) `scripts/daily-refresh.sh`** — change:
```
DIR="$HOME/dog-finder"
PROMPT_FILE="$DIR/prompts/daily-refresh.md"
LOG="$DIR/logs/daily-refresh.log"
USAGE_LOG="$DIR/logs/usage.log"
RUNS="$DIR/runs"
```
- Add `mkdir -p "$DIR/logs"` next to the existing `mkdir -p "$RUNS"`.
- Update the parser call: `python3 "$DIR/src/parse_usage.py" ...`
- **Add the budget cap** to the `claude` invocation: `--max-budget-usd 2.5`.
- Update the header comment (says "poodle-index" / "Sydney poodle-index").
- (Recommended) per-run folders: `RUNDIR="$RUNS/$TS"; mkdir -p "$RUNDIR";
  STREAM="$RUNDIR/run.stream.jsonl"; REPORT="$RUNDIR/report.txt"`.

**c) `deploy/com.dog-finder.daily-refresh.plist`** — create the tracked copy with:
- Label → `com.dog-finder.daily-refresh`
- `ProgramArguments` → `/bin/zsh`, `~/dog-finder/scripts/daily-refresh.sh` (expand `~` to the
  absolute home path in the plist — launchd does not expand `~`; write `/Users/<you>/dog-finder/...`).
- `StandardOutPath`/`StandardErrorPath` → `~/dog-finder/logs/daily-refresh.launchd.log` (also absolute).
- Keep StartCalendarInterval 21:00.

> launchd plists cannot use `~` or `$HOME` — the file content needs the fully-expanded home
> path. This is the one place absolute paths are unavoidable.

### 5.4 Swap the launchd agent (remove old label, install new)
```
chmod +x scripts/daily-refresh.sh
launchctl bootout "gui/$(id -u)/com.poodle-index.daily-refresh" 2>/dev/null   # remove OLD
rm -f ~/Library/LaunchAgents/com.poodle-index.daily-refresh.plist
cp deploy/com.dog-finder.daily-refresh.plist ~/Library/LaunchAgents/
plutil -lint ~/Library/LaunchAgents/com.dog-finder.daily-refresh.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.dog-finder.daily-refresh.plist
```
Then a **cheap probe** (no full `claude` run — that costs tokens/quota): launch a tiny temporary
plist that `head`s `data/dog-index.md` and `scripts/daily-refresh.sh` and confirm both read OK.
This catches path typos and confirms the new label is loaded.

### 5.5 `.gitignore`
```
runs/
logs/
.venv/
__pycache__/
*.pyc
.DS_Store
```

### 5.6 README.md (write a real one)
Cover: what dog-finder is; the architecture (LLM judges / code parses / browser-MCP-via-Haiku
for JS); how the daily job runs (launchd, 21:00); how to run manually
(`launchctl kickstart -k "gui/$(id -u)/com.dog-finder.daily-refresh"`); how to watch it
(`tail -f logs/daily-refresh.log`); where usage lands (`logs/usage.log`); the US$2.50 budget cap;
and **how to fix a broken parser** (manifest shows `PARSE_ERROR` → edit `src/parsers/<x>.py` → commit).

### 5.7 git init & first commit
```
cd ~/dog-finder
git init
git add .gitignore README.md HANDOVER.md config prompts src scripts deploy data
git status   # verify runs/ and logs/ are NOT staged
git commit -m "Initial commit: dog-finder — scheduled low-shed dog adoption index (LLM-driven, launchd 9pm daily)"
```
Do not configure git user/remote unless the user asks.

---

## 6. PHASE 1 validation checklist
- [ ] `~/poodle-index` no longer exists; everything is under `~/dog-finder`.
- [ ] `git status` clean; `runs/` and `logs/` ignored.
- [ ] `plutil -lint` passes; `launchctl print "gui/$(id -u)/com.dog-finder.daily-refresh"` shows the agent loaded with the new script path. Old `com.poodle-index.*` label is gone.
- [ ] Probe confirms launchd can read `data/dog-index.md` and `scripts/daily-refresh.sh`.
- [ ] `awk 'f; /^---$/{f=1}' prompts/daily-refresh.md` still yields a non-empty prompt body.
- [ ] `--max-budget-usd 2.5` is present in the `claude` call.
- [ ] No stale references: `grep -rn "poodle-index" scripts prompts deploy config src` returns nothing (ignore matches inside `runs/`).

---

## 7. PHASE 2 — code-delegation refactor (design spec, implement after Phase 1)

Goal: the LLM stops ingesting raw HTML. A Python CLI does fetch+parse+dedup and emits a compact
candidate list the LLM only has to *judge*.

### 7.1 `src/pipeline.py` (stdlib-first; see §2.5 for the deps decision)
CLI (stdlib path): `python3 -m src.pipeline --shelters config/shelters.json --index data/dog-index.md --out runs/<ts>/`
CLI (if deps adopted via uv): `uv run python -m src.pipeline ...` — and `scripts/daily-refresh.sh`
must call it through `uv run` too. **launchd PATH gotcha:** launchd gives a minimal PATH, so if
`uv` is used, add its install dir (e.g. `~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`) to
the `export PATH=...` line in the launcher and ensure `uv` is installed system-wide. Verify via
the cheap probe before relying on the 9pm run.

Behavior:
1. Load shelters; **skip `render:dead`**; collect `render:js` separately (NOT fetched by code —
   emitted into the manifest as `needs_browser` for the LLM to handle via MCP).
2. For each `static` shelter: `fetch.py` does an HTTP GET (User-Agent; timeout; one retry).
   Route to a parser in `src/parsers/` (PetRescue parser handles the majority; `generic.py` for
   own-sites). Parsers return records `{url, name, breed, age, sex, size, location, shelter, fee, status}`.
3. **Error policy:** a parser raises `ParseError` on unrecognized markup; pipeline catches
   **per source**, writes `{status:"PARSE_ERROR", detail, url}` to the manifest, skips, continues.
   Also flag `{status:"EMPTY_OK"}` when HTTP 200 but 0 records (likely broken parser).
4. `dedup.py`: parse the known-URL set from `data/dog-index.md` (URLs under both "Current
   candidates" and "Recently adopted"); mark each record `new` / `known`.
5. Write `runs/<ts>/candidates.json` (compact) and `runs/<ts>/fetch_manifest.json`
   (per-source: http_status, bytes, n_cards, n_new, status, error).

### 7.2 New prompt (`prompts/daily-refresh.md`) flow
Rewrite the OLD scraping steps to:
1. Run `python3 -m src.pipeline ...` via Bash; read `candidates.json` + `fetch_manifest.json`.
2. For shelters flagged `needs_browser` (render:js): drive **Playwright/Chrome MCP** — typically
   by launching a **Haiku subagent** per site/batch to operate the browser and return the same
   record shape — then append to the candidate set.
3. Apply the **qualifying criteria** (keep the current criteria verbatim — size ≤~10kg,
   low-shed/low-odour breed list, strict all-parents-low-shed cross rule, geo filter), write
   ≤25-word summaries, classify status.
4. Edit `data/dog-index.md` (same format as the current step 5).
5. Report, and surface any `PARSE_ERROR`/`EMPTY_OK` sources from the manifest so the human knows
   what to fix.

### 7.3 Budget guardrail
Already added in Phase 1: `--max-budget-usd 2.5`. Revisit the figure once Phase 2 establishes the
new (much lower) per-run cost.

---

## 8. Cost & observability context (why Phase 2 matters)

Measured per-run usage (from `logs/usage.log`):
| Run | Criteria | Haiku input tokens (HTML) | Total cost | Outcome |
|---|---|---|---|---|
| 20260524-001550 | poodle (old) | 693,782 | $1.40 | completed |
| 20260524-094648 | low-shed (new) | 1,111,263 | $2.72 | hit 5-hr limit |

- Cost is **~100% Haiku ingesting raw HTML** (input tokens dominate; coordinator/Sonnet input is
  ~15 tokens). The new criteria *increased* load (more aggregator searches + shelters).
- The crawler **rebalancing works**: batches split evenly to `15/15/15/14` (60 − 1 dead = 59).
- Rate limit is the **5-hour rolling window** ("resets 2:30pm Australia/Sydney"), NOT monthly.
  Confirm anytime with `/usage` in an interactive `claude` session.
- `parse_usage.py` already emits TOTAL + per-model token/cost per run. Phase 2 adds the
  per-source `fetch_manifest.json` for shelter-level observability.
- The US$2.72 run is what motivated the §2.6 budget cap of US$2.50.

---

## 9. Operational quick reference
- **Run now:** `launchctl kickstart -k "gui/$(id -u)/com.dog-finder.daily-refresh"` (returns immediately; runs in background).
- **Watch:** `tail -f ~/dog-finder/logs/daily-refresh.log`
- **Usage history:** `cat ~/dog-finder/logs/usage.log`
- **Remove the schedule:** `launchctl bootout "gui/$(id -u)/com.dog-finder.daily-refresh"` then delete the plist.
- `claude` is invoked headless with `--dangerously-skip-permissions` (needed for unattended
  WebFetch/Edit/Bash/subagents/MCP) and `--max-budget-usd 2.5`. It runs only against the user's
  own files under `~/dog-finder`.

---

## 10. Open items / decisions still pending
- **Legacy index entries** predate the low-shed criteria change (e.g. Kev = Poodle×Pug,
  Milo = Labradoodle) and don't meet it; the user accepted leaving them to age out. A `data/`
  header note already flags pre-2026-05-24 entries.
- **Phase 2 parser coverage:** PetRescue first (majority of sources); council JS sites via
  browser MCP; some own-sites may stay best-effort.
- **Deps decision** (stdlib vs uv) — made when writing the Phase 2 parsers (§2.5).
