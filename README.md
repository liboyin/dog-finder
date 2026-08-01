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
  adopted). This drives the judgment/determinism split in *Architecture*.
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
  new dog for breed/fee, re-fetches the detail page of each already-qualified dog to refresh its
  status (e.g. `available` → `on-hold`) since a still-listed card never re-exposes that on its own,
  and flags a qualified dog whose detail page died or now reports adopted as `maybe_adopted`. That
  per-dog detail re-fetch is the sole vanish-detection path for static shelters, so **every
  registered parser must define `parse_detail`** (a registry test enforces it); browser-sourced
  dogs have no static detail page and are flagged separately once unseen for 3 days. `collect` then
  writes `pending.json` (dogs needing a verdict) plus `fetch_manifest.json`. The `apply` phase
  merges the LLM's verdicts into state and re-renders the index.
- **The LLM does only judgment.** It decides whether a breed/cross meets the low-shed criteria,
  writes the ≤25-word summaries, resolves geo-borderline cases, and confirms vanished dogs as
  adopted — emitting a single `verdicts.json`. The response has exactly one explicit outcome for
  every pending URL; an inconclusive `maybe_adopted` browser re-check may be `deferred`, which
  leaves its state entry unchanged for retry. Browser discoveries must carry browser lifecycle
  metadata (`source_kind: "browser"`). It never hand-edits the index or state; code renders
  `data/dog-index.md` from `state.json`, touching only the region between the
  `<!-- DOGS:BEGIN/END -->` markers so human-authored prose is preserved.
- **`source` and `shelter` are distinct.** `source` records *what found* a dog — the config
  entry that surfaced it, which for the aggregator searches is a query like "PetRescue NSW poodle
  search", not an organization. `shelter` is the *real* rescue group or council that holds the dog,
  extracted from the listing's own detail page (the PetRescue group link, or a fixed name for
  single-org sites). The index shows `shelter`, falling back to `source` then "unknown", so a human
  sees the actual shelter rather than the aggregator that surfaced it. Because there is no
  cross-source dedup, the same dog found under its own-site *and* via a PetRescue search appears as
  two entries with two URLs — an accepted consequence of keying on URL.
- **JS-rendered shelters use a browser MCP.** Shelters whose listings are JavaScript-rendered
  (`render: js`), or non-PetRescue own-sites with no code parser, are flagged `NEEDS_BROWSER` in
  the manifest; Codex drives the configured Playwright MCP with a managed, headless Firefox
  browser for those and judges them alongside the pipeline's candidates.

## Key design decisions

- **Runs locally via systemd, not the cloud.** The job is a Linux `systemd --user` timer
  (`dog-finder-daily-refresh`, 13:00 Australia/Sydney). The cloud can't reach local files, and
  the index lives on disk, so the schedule must be local too.
- **Fail loud, fix externally.** Parsers raise on markup drift; a run records the error per source
  in the manifest, skips that shelter, and continues. "HTTP 200 but 0 cards" is also an error, so
  a silently-broken parser can't quietly drop a shelter. A human fixes the parser out-of-band and
  commits — the failure is visible, not swallowed. The same applies to the judge itself: if it
  produces no complete, valid `verdicts.json` response (crash, auth failure, timeout, missing, or
  duplicate pending verdict), the service exits before applying or committing state. A deferred
  outcome counts only for a pending re-check and is deliberately a no-op, so an unreachable
  browser cannot silently mutate or discard a dog. Browser discoveries without the required
  `source_kind: "browser"` lifecycle metadata also fail validation. A broken judge went unnoticed
  for 12 days (2026-06-22 to 2026-07-04, an expired local login) before this check existed.
- **The unattended judge bypasses Codex approvals and sandboxing.** Codex currently requires
  `--dangerously-bypass-approvals-and-sandbox` for noninteractive Playwright MCP calls. This is a
  deliberate owner-approved tradeoff to retain browser-only shelter coverage; scraped content can
  influence an agent with full local authority. The prompt restricts the task and Playwright's
  configuration exposes only read-oriented browser tools, but neither is a hard filesystem
  boundary. The CLI writes the schema-validated final response to `runs/<ts>/verdicts.json`; the
  launcher owns the intended state, index, and git mutations. It uses `gpt-5.6-luna`, chosen for
  this recurring, high-volume classification workload.
- **A service timeout, not an in-process watchdog.** `TimeoutStartSec=90min` in the systemd unit
  caps the complete service cgroup, including children, so one bad run cannot block later timer
  slots indefinitely.
- **Git tracks the valuable artifacts and their inputs.** Tracked: `state.json` (the authoritative
  record), the rendered index, shelter config, prompt, code, and deploy files. The per-run
  artifacts (`pending.json`, `verdicts.json`, `fetch_manifest.json`, stream/report) and logs are
  generated, not authored, so they are gitignored under `runs/` and `logs/`. A daily run
  auto-commits and pushes `state.json`/`dog-index.md` (`Automated run on YYYY-MM-DD`) to `origin`
  **only when the dog list's membership changes** — a dog added or dropped. In-place edits that
  keep the same set of dogs stay local, so commit history tracks membership changes, not every run.
- **Two retention windows keep things bounded.** State entries unseen for 90 days are pruned from
  `state.json` at each run's start; per-run artifact directories under `runs/` older than 30 days
  are swept at each run's end. Both are self-maintaining, so neither the tracked state nor the
  gitignored run artifacts grow without limit.

## Assumptions

- **Breed predicts coat.** Listings never state shedding or odour, so the whole filter rests on
  breed: a stated breed — or, for a cross, every named parent — is assumed to reliably imply coat
  behaviour. A listing with no explicit breed, or a cross naming an unknown or shedding parent,
  can't be judged and is excluded.
- **Listing fields are taken at face value.** Breed, size, sex, location, and fee are trusted as
  stated; an ambiguous breed is kept with a `verify coat/breed` tag rather than triggering another
  static fetch. The pipeline doesn't otherwise second-guess a shelter's data.
- **Place name approximates drive time.** "Within ~4 hours of Sydney" is judged from the stated
  town/region against known NSW + ACT geography, not a routing API; borderline towns are kept with
  a `verify drive time` tag.
- **A URL (with its fragment) is a dog's identity.** State and dedup are keyed by the canonical URL
  *including* the fragment, so a dog normally maps to one durable listing URL, but a page that hosts
  several dogs at one URL (e.g. PAWS) distinguishes them by a reproducible `url#name-slug` anchor —
  without which every dog on the page would collapse into one entry and all but the last would be
  lost. A re-listed dog with a new URL is treated as new; a qualified dog that vanishes is treated as
  adopted, confirmed via a 404 or adopted page. The same dog cross-listed under two sources
  (own-site and PetRescue) has two distinct URLs and is accepted as two entries — there is no
  cross-source dedup.
- **PetRescue's server-rendered listings are the common case.** Most shelters syndicate to
  PetRescue in a static, parseable format the code handles directly; JS-rendered sites and
  own-sites are the exception, flagged for the browser path. The parser assumes that static
  structure stays stable enough to parse — and fails loud when it drifts.
- **Single-user, single-machine.** The systemd user unit assumes the checkout is at
  `~/Code/dog-finder`; the launcher itself derives the repository root from its own location.
- **Legacy entries age out rather than being pruned.** Index entries predating the 2026-05-24
  low-shed criteria change are left to age out rather than retroactively removed; a header note
  flags them.
- **State stays bounded by a 90-day sweep.** At each run's start, entries not seen on any shelter
  for 90 days are dropped from `state.json` (keyed on `last_seen`, so still-listed dogs never age
  out). A pruned dog that reappears is simply re-discovered as new.
- **Breed-specific sources whose breed is categorically disqualified are not monitored.** A source
  that only ever lists a breed the filter always excludes (labradoodles: typically >10 kg and a
  shedding parent) earns no coverage. DoodleAid was initially kept for its qualifying small oodles
  but dropped on 2026-07-17 after its page turned out to list UK dogs — outside the NSW/ACT scope,
  so it never yields a candidate either.
- **Unknown species is treated as a dog.** A listing whose species can't be parsed is kept as a
  candidate rather than dropped (`base.is_dog` returns True for an unknown species), so a mislabelled
  or unlabelled dog is never silently missed — the LLM filters any non-dog that slips through.
- **Aggregator searches cover NSW only.** The PetRescue aggregator searches are pinned to
  `state_id=1` (NSW), so ACT coverage rests entirely on the three ACT-specific sources (RSPCA ACT,
  ACT Domestic Animal Services, ACT Canberra Pooch Rescue); there is no ACT aggregator sweep.
- **A missing `state.json` silently rebuilds from empty.** `load_state` returns a fresh empty
  document when the file is absent, so a first run (or a deleted state file) starts clean and
  re-discovers every current listing as new rather than erroring.
- **A dropped source's state entries are left to age out.** Removing a source from `shelters.json`
  doesn't retroactively purge its listings; its orphaned entries simply stop being seen and age out
  via the 90-day prune (the doggierescue parser removal, 9faef8d, set the precedent).

## Test

The suite is plain `unittest` with no network and no third-party dependencies. From the repo root:

```
python3 -m unittest discover -s tests
```

It must pass on the Linux `python3` interpreter used by the systemd service; this is the gate for
every change. Tests use HTML fixtures under `tests/fixtures/` rather than live fetches.

## Deploy

The job runs **locally only**, as a Linux `systemd --user` timer — never as a cloud routine (see
*Runs locally via systemd, not the cloud* above). The checkout must be at `~/Code/dog-finder`.

- **Prerequisites:** install Node.js 22 and register Playwright MCP with headless Firefox:
  `codex mcp add playwright -- npx -y @playwright/mcp@0.0.78 --browser firefox --headless --isolated`.
  Install the matching managed browser runtime with
  `npx -y @playwright/mcp@0.0.78 install-browser firefox`, then set this exact read-oriented
  allowlist in `~/.codex/config.toml`:

  ```toml
  enabled_tools = [
    "browser_console_messages", "browser_find", "browser_navigate",
    "browser_navigate_back", "browser_network_request", "browser_network_requests",
    "browser_snapshot", "browser_tabs", "browser_wait_for",
  ]
  ```

  Keep the MCP version pinned; review and test any version update before changing it in that
  configuration.
- **Install:** copy the two unit files and activate the timer:
  `mkdir -p ~/.config/systemd/user && cp deploy/dog-finder-daily-refresh.{service,timer} ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now dog-finder-daily-refresh.timer`.
  Run `loginctl enable-linger "$USER"` once if the timer must run while you are logged out.
- **Change the schedule:** edit `deploy/dog-finder-daily-refresh.timer`, copy it over as above,
  then run `systemctl --user daemon-reload && systemctl --user restart dog-finder-daily-refresh.timer`.
- **Verify & inspect:** `systemctl --user list-timers dog-finder-daily-refresh.timer` confirms it
  is registered; `journalctl --user -u dog-finder-daily-refresh.service` and
  `logs/daily-refresh.log` record each run. To run once on demand, use
  `systemctl --user start dog-finder-daily-refresh.service`.
