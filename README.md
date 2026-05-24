# dog-finder

A daily-refreshed adoption index of small, low-shedding, low-odour dogs available at
shelters within ~4 hours of Sydney (NSW + ACT). A scheduled job runs every night and
maintains a single human-reviewed markdown index, [`data/dog-index.md`](data/dog-index.md):
prepending newly-found qualifying dogs and pruning ones that have been adopted.

This document explains *why* the project is shaped the way it is. For step-by-step
operational commands and the in-progress refactor plan, see [`HANDOVER.md`](HANDOVER.md).

## What it produces

`data/dog-index.md` is the only artifact a human reads, and the one whose git history
carries lasting value — it is the record of which dogs appeared and were adopted over
time. The workflow is human-in-the-loop: the agent maintains the index, a person reviews it.

## Architecture

The work splits along a judgment/determinism line:

- **The LLM does judgment.** A top-level Claude agent is the planner/coordinator. It decides
  whether a breed or cross meets the low-shed/low-odour criteria, writes the per-dog summaries,
  resolves geo-borderline cases, classifies adoption status, and edits the index. Judgment is
  irreducibly model work, so it stays with the model.
- **Code does the rote work.** Fetching static pages, parsing listing cards into structured
  records, deduping against the known-URL set, and building the run manifest are deterministic
  and belong in Python, not in model context. The `src/pipeline.py` CLI runs first each night:
  it fetches and parses the server-rendered PetRescue shelters (the majority), dedups new dogs
  against the index, fetches each new listing's detail page for breed/fee, and writes a compact
  `candidates.json` plus a per-source `fetch_manifest.json`. The LLM then judges that candidate
  list instead of ingesting raw HTML.
- **JS-rendered shelters use a browser MCP.** Shelters whose listings are JavaScript-rendered
  (`render: js` in the shelter list) can't be read by a plain HTTP fetch. These are handled by
  the LLM driving Playwright / Claude-in-Chrome MCP, typically via a Haiku subagent.

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
- **Git tracks the valuable artifact and its inputs.** The index, shelter config, prompt, code,
  and deploy files are tracked. Logs and per-run stream/report artifacts are generated, not
  authored, so they are gitignored.

## Assumptions

- Single-user, single-machine: paths are specific to this install
  (`/Users/fanguard/Code/dog-finder`) because launchd plists cannot expand `~`.
- The 5-hour rolling rate-limit window — not a monthly quota — is the binding usage constraint.
- Legacy index entries predating the 2026-05-24 low-shed criteria change are left to age out
  rather than retroactively pruned; a header note in the index flags them.
