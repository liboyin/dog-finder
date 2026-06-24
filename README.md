# dog-finder

A daily-refreshed adoption index of small, low-shedding, low-odour dogs at shelters within
~4 hours of Sydney (NSW + ACT). A daily job maintains a single human-reviewed Markdown index,
[`data/dog-index.md`](data/dog-index.md): prepending newly-found qualifying dogs and pruning
adopted ones.

This document explains *why* the project is shaped the way it is; see *Deploy* at the end for how to install and run it.

## What it produces

`data/dog-index.md` is the artifact a human reads — qualifying dogs, newest first. It is
*rendered* from `data/state.json`, a machine-owned record of every listing ever seen (keyed by
URL) with its fields, the LLM's qualify verdict, and first/last-seen timestamps. The git history
of both records which dogs appeared and were adopted over time. The workflow is human-in-the-loop:
the system maintains state and index; a person reviews the index.

## Design goals

The architecture and design decisions below all serve a handful of objectives:

- **A trustworthy shortlist, not a firehose.** A small, high-precision list matching a narrow
  brief — small (≤~10 kg / toy / small), low-shedding *and* low-odour by breed, in NSW + ACT
  within ~4 hours' drive of Sydney — so a person can skim it and trust every entry rather than
  re-filter raw listings. Genuinely borderline cases are kept with a `verify …` tag, not dropped.
- **Spend tokens only on judgment.** LLM time is the expensive, rate-limited resource, so
  everything deterministic — fetching, parsing, deduping, state-tracking, rendering — runs in
  Python (system install + stdlib only); the model is invoked only where judgment is unavoidable
  (does this breed/cross qualify, is this borderline location in range, is a vanished dog
  adopted). This drives the judgment/determinism split in *Architecture* and the budget cap in
  *Key design decisions*.
- **Unattended daily operation.** A daily job keeps the index current with no human in the loop
  for the run itself; a person only reads and reviews the result.
- **The human makes the final call.** The system curates and maintains but never decides which
  dog to adopt — which is why the primary artifact is a reviewable Markdown index, not a database.
- **Never silently miss a dog.** A single missed listing could be *the* dog, so the system fails
  loudly: a broken parser surfaces an error and skips its shelter rather than quietly returning
  nothing (see *Fail loud, fix externally*).
- **The search keeps a memory.** The git history of `state.json` and the index is a durable,
  auditable record of which dogs appeared and were adopted over time — a trail, not just a current
  snapshot.

## Architecture

The work splits along a judgment/determinism line, with state living in code rather than the
prose Markdown:

- **Code does the rote work and owns the state.** Fetching static pages, parsing listing cards,
  deduping, and tracking what's been seen are deterministic and belong in Python. The
  `src/pipeline.py collect` phase runs first each run: it fetches and parses the server-rendered
  PetRescue shelters (the majority), dedups against `state.json`, detail-fetches each genuinely
  new dog for breed/fee, flags vanished qualified dogs as `maybe_adopted`, and writes
  `pending.json` (dogs needing a verdict) plus `fetch_manifest.json`. The `apply` phase then
  merges the LLM's verdicts into state and re-renders the index.
- **The LLM does only judgment.** It decides whether a breed/cross meets the low-shed criteria,
  writes the ≤25-word summaries, resolves geo-borderline cases, and confirms vanished dogs as
  adopted — emitting a single `verdicts.json`. It never hand-edits the index or state; code
  renders `data/dog-index.md` from `state.json`, touching only the region between the
  `<!-- DOGS:BEGIN/END -->` markers so human-authored prose is preserved.
- **JS-rendered shelters use a browser MCP.** Shelters whose listings are JavaScript-rendered
  (`render: js`), or non-PetRescue own-sites with no code parser, are flagged `NEEDS_BROWSER` in
  the manifest; the LLM drives Playwright / Claude-in-Chrome MCP (typically via a Haiku subagent)
  for those and judges them alongside the pipeline's candidates.

## Key design decisions

- **Runs locally via launchd, not the cloud.** The job is a macOS `launchd` agent
  (`com.dog-finder.daily-refresh`, 13:00 Australia/Sydney). The cloud "Routines" feature can't
  reach local files, and the index lives on disk, so the schedule must be local too.
- **Lives outside `~/Documents`.** macOS TCC blocks launchd agents from reading the Documents
  folder, which would silently break the unattended run. The project is self-contained under its
  repo root and references no paths outside it.
- **Fail loud, fix externally.** Parsers raise on markup drift; a run records the error per source
  in the manifest, skips that shelter, and continues. "HTTP 200 but 0 cards" is also an error, so
  a silently-broken parser can't quietly drop a shelter. A human fixes the parser out-of-band and
  commits — the failure is visible, not swallowed.
- **A budget cap, not a throttle.** The headless `claude` invocation aborts cleanly at
  `--max-budget-usd 2.5` rather than being throttled into a multi-hour death-crawl. The figure
  comes from observed per-run cost (a low-shed run hit US$2.72) and will be revisited once the
  code-delegation refactor lowers it.
- **Git tracks the valuable artifacts and their inputs.** Tracked: `state.json` (the authoritative
  record), the rendered index, shelter config, prompt, code, and deploy files. The per-run
  artifacts (`pending.json`, `verdicts.json`, `fetch_manifest.json`, stream/report) and logs are
  generated, not authored, so they are gitignored under `runs/` and `logs/`. A daily run
  auto-commits and pushes `state.json`/`dog-index.md` (`Automated run on YYYY-MM-DD`) to `origin`
  **only when the dog list's membership changes** — a dog added or dropped. In-place edits that
  keep the same set of dogs stay local, so commit history tracks membership changes, not every run.

## Assumptions

- **Breed predicts coat.** Listings never state shedding or odour, so the whole filter rests on
  breed: a stated breed — or, for a cross, every named parent — is assumed to reliably imply coat
  behaviour. A listing with no explicit breed, or a cross naming an unknown or shedding parent,
  can't be judged and is excluded.
- **Listing fields are taken at face value.** Breed, size, sex, location, and fee are trusted as
  stated; the LLM WebFetches a listing only to confirm an ambiguous field. The pipeline doesn't
  otherwise second-guess a shelter's data.
- **Place name approximates drive time.** "Within ~4 hours of Sydney" is judged from the stated
  town/region against known NSW + ACT geography, not a routing API; borderline towns are kept with
  a `verify drive time` tag.
- **A listing URL is a stable, unique identity.** State and dedup are keyed by URL, so each dog is
  assumed to map to one durable listing URL. A re-listed dog with a new URL is treated as new; a
  qualified dog that vanishes is treated as adopted, confirmed via a 404 or adopted page.
- **PetRescue's server-rendered listings are the common case.** Most shelters syndicate to
  PetRescue in a static, parseable format the code handles directly; JS-rendered sites and
  own-sites are the exception, flagged for the browser path. The parser assumes that static
  structure stays stable enough to parse — and fails loud when it drifts.
- **Single-user, single-machine.** Paths are specific to this install
  (`/Users/fanguard/Code/dog-finder`) because launchd plists cannot expand `~`.
- **Legacy entries age out rather than being pruned.** Index entries predating the 2026-05-24
  low-shed criteria change are left to age out rather than retroactively removed; a header note
  flags them.
- **State stays bounded by a 90-day sweep.** At each run's start, entries not seen on any shelter
  for 90 days are dropped from `state.json` (keyed on `last_seen`, so still-listed dogs never age
  out). A pruned dog that reappears is simply re-discovered as new.

## Deploy

The job runs **locally only**, as a macOS `launchd` agent — never as a cloud routine (see *Runs
locally via launchd, not the cloud* above). All steps run on this machine, from the repo root:

- **Install:** copy the agent definition into `LaunchAgents` and load it —
  `cp deploy/com.dog-finder.daily-refresh.plist ~/Library/LaunchAgents/` then
  `launchctl load ~/Library/LaunchAgents/com.dog-finder.daily-refresh.plist`.
- **Change the schedule (or any field):** edit `deploy/com.dog-finder.daily-refresh.plist` — its
  `StartCalendarInterval` sets the run time — then copy it over the installed copy as above and
  reload it: run `launchctl unload` then `launchctl load`, both on
  `~/Library/LaunchAgents/com.dog-finder.daily-refresh.plist`.
- **Verify & inspect:** `launchctl list | grep dog-finder` confirms it is registered;
  `logs/daily-refresh.log` records each run. To run once on demand without waiting for the
  schedule, invoke `scripts/daily-refresh.sh` directly.
