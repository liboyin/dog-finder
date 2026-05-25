# dog-finder

A daily-refreshed adoption index of small, low-shedding, low-odour dogs available at
shelters within ~4 hours of Sydney (NSW + ACT). A scheduled job runs every night and
maintains a single human-reviewed markdown index, [`data/dog-index.md`](data/dog-index.md):
prepending newly-found qualifying dogs and pruning ones that have been adopted.

This document explains *why* the project is shaped the way it is. For step-by-step
operational commands and the in-progress refactor plan, see [`HANDOVER.md`](HANDOVER.md).

## What it produces

`data/dog-index.md` is the artifact a human reads — the current qualifying dogs, newest
first. Its authoritative backing is `data/state.json`, a machine-owned record of every
listing ever seen (keyed by URL) with its fields, the LLM's qualify verdict, and first/last
seen timestamps. The index is *rendered* from state; the git history of both is the record
of which dogs appeared and were adopted over time. The workflow is human-in-the-loop: the
system maintains state and index, a person reviews the index.

## Architecture

The work splits along a judgment/determinism line, and state lives with code rather than in
the prose Markdown:

- **Code does the rote work and owns the state.** Fetching static pages, parsing listing
  cards, deduping, and tracking what's been seen are deterministic and belong in Python. The
  `src/pipeline.py collect` phase runs first each night: it fetches and parses the
  server-rendered PetRescue shelters (the majority), dedups against `state.json`, detail-fetches
  each genuinely new dog for breed/fee, flags qualified dogs that vanished as `maybe_adopted`,
  and writes `pending.json` (dogs needing a verdict) + `fetch_manifest.json`. The
  `apply` phase then merges the LLM's verdicts back into state and re-renders the index.
- **The LLM does only judgment.** It decides whether a breed/cross meets the low-shed criteria,
  writes the ≤25-word summaries, resolves geo-borderline cases, and confirms vanished dogs as
  adopted — emitting a single `verdicts.json`. It never hand-edits the index or state; code
  renders `data/dog-index.md` from `state.json`, touching only the region between the
  `<!-- DOGS:BEGIN/END -->` markers so human-authored prose is preserved.
- **JS-rendered shelters use a browser MCP.** Shelters whose listings are JavaScript-rendered
  (`render: js`) or non-PetRescue own-sites with no code parser are flagged `NEEDS_BROWSER` in
  the manifest; the LLM drives Playwright / Claude-in-Chrome MCP (typically via a Haiku
  subagent) for those and judges the results alongside the pipeline's candidates.

## Key design decisions

- **Runs locally via launchd, not the cloud.** The job is a macOS `launchd` agent
  (`com.dog-finder.daily-refresh`, 21:00 Australia/Sydney). The cloud "Routines" feature can't
  reach local files, and the index lives on disk, so the schedule must be local too.
- **Lives outside `~/Documents`.** macOS TCC blocks launchd agents from reading the Documents
  folder, which would silently break the unattended run. The project is self-contained under
  its repo root and references no paths outside it.
- **Fail loud, fix externally.** Parsers raise on markup drift; a run records the error per
  source in the manifest, skips that shelter, and continues. "HTTP 200 but 0 cards" is also
  treated as an error so a silently-broken parser can't quietly drop a shelter. A human fixes
  the parser code out-of-band and commits — the failure is visible, not swallowed.
- **A budget cap, not a throttle.** The headless `claude` invocation aborts cleanly at
  `--max-budget-usd 2.5` rather than being throttled into a multi-hour death-crawl. The figure
  comes from observed per-run cost (a low-shed run hit US$2.72); it will be revisited once the
  code-delegation refactor lowers per-run cost.
- **Git tracks the valuable artifacts and their inputs.** `state.json` (the authoritative
  record), the rendered index, shelter config, prompt, code, and deploy files are tracked. The
  per-run artifacts (`pending.json`, `verdicts.json`, `fetch_manifest.json`, stream/report) and
  logs are generated, not authored, so they are gitignored under `runs/` and `logs/`. Each
  nightly run auto-commits any change to `state.json`/`dog-index.md` (`Automated run on
  YYYY-MM-DD`) so the day-to-day history lives in git.

## Assumptions

- Single-user, single-machine: paths are specific to this install
  (`/Users/fanguard/Code/dog-finder`) because launchd plists cannot expand `~`.
- The 5-hour rolling rate-limit window — not a monthly quota — is the binding usage constraint.
- Legacy index entries predating the 2026-05-24 low-shed criteria change are left to age out
  rather than retroactively pruned; a header note in the index flags them.
- `state.json` is kept bounded by a 90-day retention sweep at the start of each run: entries
  not seen on any shelter for 90 days are dropped (keyed on `last_seen`, so still-listed dogs
  never age out). A dog that reappears after being pruned is simply re-discovered as new.
