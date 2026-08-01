# PLAN.md — post-migration hardening hand-over

This is the execution plan for hardening the Ubuntu/Codex migration in commit
`1c30f5c`. It replaces the completed July 2026 Claude/macOS plan. The next agent
must read `AGENTS.md` and `README.md` before starting and must keep this file
current as work packages are completed.

## 0. Objective and scope

The project now runs on Ubuntu 26.04 with system Python 3.14, Codex using
`gpt-5.6-luna`, and a pinned Playwright MCP driving headless Firefox. The
migration is structurally sound, but its adversarial review found six runtime
and data-integrity risks. This plan resolves all six and performs the final
end-to-end verification that the committed completeness gate has not yet
received.

In scope:

1. Represent an inconclusive browser recheck without changing the dog or
   failing an otherwise valid run.
2. Require exactly one explicit outcome for every pending input, including
   rejected and intentionally deferred dogs.
3. Make response URL validation identical to the URL validation used during
   state merge.
4. Ensure browser discoveries always retain browser lifecycle tracking.
5. Make apply failures fatal before Git operations and reduce the state/index
   inconsistency window.
6. Replace the ineffective user-level `network-online.target` dependency with
   a network check that exists on the target Ubuntu host.
7. Record Python 3.14 as the runtime, simplify module invocation, and eliminate
   the `HTTPError` resource warnings exposed by the new interpreter.
8. Run a controlled, isolated end-to-end refresh with the final code.

Out of scope unless the owner explicitly expands it:

- Changing the dog qualification criteria, source list, schedule, model, MCP
  version, or MCP tool allowlist.
- Weakening or removing complete pending-URL coverage.
- Adding automatic model retries, batching, or a different model merely to make
  a failed live verification pass.
- Broad modernization of every Python module just because Python 3.14 is
  available.
- Installing or enabling the user timer on the production checkout.
- Reverting, amending, or force-pushing existing commits.

## 1. Baseline and evidence

Record these facts before making changes; re-check them if the environment has
changed:

- Repository baseline: `1c30f5c` on `main`.
- Runtime observed during review: Python `3.14.4`, Node.js `22.22.1`, npm
  `9.2.0`, Codex CLI `0.146.0`.
- Browser integration: `@playwright/mcp@0.0.78`, Firefox, headless, isolated,
  with the nine read-oriented tools documented in `README.md`.
- Current unit baseline: 103 tests pass, but `tests/test_fetch.py` emits two
  `ResourceWarning` messages for unclosed `HTTPError` objects.
- Shell syntax, JSON parsing, systemd unit syntax, and the Sydney calendar
  expression pass their static checks.
- `systemctl --user show network-online.target` reports `LoadState=not-found`
  on this host. `/usr/bin/nm-online` is installed.
- The retained run `runs/20260801-110350` completed before the final coverage
  gate was committed. It contains 191 pending inputs but only 11 verdict
  objects, while its prose report claims 181 rejections. That run is evidence
  that the final committed contract still needs a fresh live test, not evidence
  that it already passed one.
- The systemd timer is not currently installed in the user manager. Do not
  install it merely to execute this plan.

Before each work package:

```bash
git status --short
python3 --version
python3 -m unittest discover -s tests
```

The primary worktree must be clean before implementation starts. Existing
changes from the owner must not be staged, reverted, or overwritten.

## 2. Invariants and settled design decisions

These decisions remove ambiguity for the implementing agent.

### 2.1 Response outcomes

Every entry in `pending.json` must appear exactly once in the final response.
The permitted outcomes are:

- `qualified`: apply the positive judgment normally.
- `rejected`: apply the negative judgment normally.
- `deferred`: the browser check was inconclusive, so count the URL as covered
  but make **no state mutation for that entry**.

`deferred` is only valid for a URL that was already present in this run's
pending input with a truthy `recheck` field and only when the browser result is
inconclusive. It is not valid for an ordinary new pending candidate or a newly
discovered browser URL. In particular, applying a deferred entry must not
change `last_seen`, `verdict`, `removed`, `summary`, `tags`, `recheck`, or
`recheck_reason`.

The completeness gate remains fail-closed:

- Missing pending URLs fail the run.
- Duplicate canonical URLs fail the run.
- Unsafe raw URLs fail the run before apply.
- Extra URLs are allowed only for valid browser discoveries.

### 2.2 Browser discovery lifecycle

Every response URL not present in `pending.json` is a browser discovery. It must
have `source_kind: "browser"`; null, empty, or another value is invalid. State
merge should still defensively hard-code `"browser"` for a genuinely new entry
rather than trusting response provenance, but validation is the primary
enforcement point.

### 2.3 Apply failure semantics

The state file remains authoritative. A normal render/validation failure must
happen before either state or index is written. Both outputs should use atomic
single-file replacement so a process interruption cannot truncate either file.
There is no portable atomic transaction spanning two files; do not build a
large transaction framework for this project. Instead:

1. Load state, verdicts, and the current index.
2. Apply verdicts to the in-memory state.
3. Render the new index completely in memory.
4. Atomically save state and atomically replace the index.
5. If any apply step exits nonzero, the launcher exits nonzero immediately and
   performs no Git add, commit, or push.

This ordering eliminates ordinary parse/render failures before mutation and
ensures any rare write/replace failure is visible and never committed
automatically. Document the remaining cross-file crash window rather than
claiming a two-file transaction.

### 2.4 Network readiness

The target is Ubuntu 26.04 with NetworkManager and `/usr/bin/nm-online`. Remove
the nonexistent user-manager `network-online.target` dependency. The service
should wait for a usable NetworkManager connection with a bounded
`ExecStartPre=/usr/bin/nm-online -q -t 300`. A timeout must fail the service
before collection starts.

Do not add silent network polling to Python or weaken fetch errors. If the
deployment must later support a host without NetworkManager, stop and ask the
owner rather than silently making this Ubuntu-specific contract vague.

### 2.5 Python 3.14 scope

`README.md` must state that the supported local runtime is Python 3.14 on
Ubuntu 26.04. Use that baseline where it removes real compatibility machinery,
but avoid repository-wide syntax churn.

- Invoke the validator as `python3 -m src.write_report` so it uses normal
  package imports.
- Remove the `try: from src ... except ModuleNotFoundError: import ...` fallback.
- Keep `from __future__ import annotations` consistently for now. Python 3.14's
  default deferred-annotation behavior is not identical to the future import's
  stringized behavior, so a bulk removal is not a mechanical cleanup.
- Do not introduce template strings, subinterpreters, free-threading, or other
  unrelated 3.14 features.

## 3. Work-package order

| WP | Title | Depends on | Status |
|---|---|---|---|
| WP1 | Make the verdict contract complete and represent deferred work | — | DONE |
| WP2 | Make apply fail-fast and keep outputs consistent | WP1 | TODO |
| WP3 | Use real Ubuntu network readiness in the user service | — | TODO |
| WP4 | Apply scoped Python 3.14 cleanup and close HTTP errors | WP1 | TODO |
| WP5 | Adversarial review and isolated end-to-end verification | WP1–WP4 | TODO |

WP1 and WP2 protect state and must land before any new paid/live judge run. WP3
and WP4 may be implemented independently after WP1, but the simplest execution
order is WP1 → WP2 → WP3 → WP4 → WP5.

## 4. WP1 — complete verdict contract and deferred outcome

### Purpose

Align the prompt, schema, validator, and state merge so every pending dog has an
explicit outcome while an inconclusive browser recheck remains untouched.
Also close the raw-URL and browser-source lifecycle gaps in the same response
boundary, which should remain the single validation point.

### Required changes

#### `prompts/daily-refresh.md`

- State unambiguously that the response must include exactly one verdict object
  for **every** `pending.json` entry, including every rejected dog.
- Explain that counts in `report` do not substitute for verdict objects.
- Add `deferred` for an inconclusive `maybe_adopted` browser check. Require the
  agent to copy the original pending fields, set `removed: false`, and preserve
  the URL; the deterministic merge will ignore the record.
- Prohibit `deferred` for ordinary new candidates and browser discoveries.
- Change the report template to include a deferred count, for example:
  `Refresh complete: X qualified, Y rejected, Z confirmed adopted, D deferred,
  W shelters needing browser.`
- Retain the rule that unreachable sources are reported for human attention.

#### `config/verdicts.schema.json`

- Add `deferred` to the `verdict` enum.
- Change `source_kind` from nullable text to a non-empty string. Current pending
  artifacts already use `petrescue` or `browser`, so this does not reject known
  production input.
- Keep the strict Codex schema requirements: every declared property remains in
  `required`, and `additionalProperties` remains false.
- Do not rely on JSON Schema `format: uri` for security or identity. Raw URL
  safety and canonical equality belong in Python, where they can be tested and
  shared with apply.

#### `src/store.py`

- Add a `DEFERRED` constant next to `PENDING`, `QUALIFIED`, and `REJECTED`.
- Make the existing verdict URL predicate public (for example,
  `valid_verdict_url`) without changing its accepted URL policy.
- In `apply_verdicts`, validate the raw URL with that shared predicate.
- Branch on `deferred` before looking up or mutating the state entry. A deferred
  record must be a complete no-op.
- For a genuinely new entry, store `source_kind: "browser"` rather than trusting
  response provenance. The validator should normally make this defense-in-depth
  behavior unnecessary.
- Preserve existing behavior for qualified, rejected, and removed records.

All modified/new non-test functions need Google-style docstrings.

#### `src/write_report.py`

- Validate every raw verdict URL with `store.valid_verdict_url` before applying
  canonicalization. This prevents whitespace or an uppercase scheme from
  passing coverage and then being ignored by merge.
- Continue comparing canonical keys for duplicates and pending coverage.
- Determine the canonical pending-key set once. For each response entry not in
  that set, require `source_kind == "browser"` and reject `deferred`.
- Permit `deferred` only when the matching pending record has a truthy `recheck`
  field, and count it as covered. Reject deferred outcomes for ordinary pending
  candidates.
- Return concise errors with counts and a small deterministic sample of URLs;
  never dump all scraped data into logs.
- Keep report writing after all validation so failure cannot leave a report that
  makes the run look healthy.

### Required tests

Update tests in source-function order and follow `AGENTS.md` import conventions.

`tests/test_write_report.py`:

- Complete qualified/rejected coverage succeeds.
- A pending deferred URL succeeds.
- A deferred ordinary pending candidate with no recheck fails.
- A deferred extra/browser-discovery URL fails.
- Missing and duplicate canonical URLs still fail.
- Leading/trailing whitespace and uppercase-scheme variants fail even when they
  canonicalize to a pending URL.
- An extra URL with `source_kind: null`, empty, or non-browser fails.
- A valid extra URL with `source_kind: "browser"` succeeds.

`tests/test_store.py`:

- Deferred on an existing recheck leaves the complete entry unchanged (compare
  a deep copy, including `last_seen` and both recheck fields).
- A new record with null/missing source kind is stored as browser when it reaches
  the defense-in-depth merge path.
- The public URL validator rejects the exact malformed variants rejected by
  response validation.

Add a small schema-contract test using `json.load` from the standard library to
assert that `deferred` is in the enum and `source_kind` is non-nullable. Do not
add a third-party JSON Schema dependency merely for this assertion.

### Documentation

Update `README.md` architecture/dataflow and fail-loud sections to describe:

- exactly-one outcome per pending URL;
- intentional deferred outcomes;
- deferred entries remaining unchanged for retry;
- browser discoveries requiring browser lifecycle metadata.

### Acceptance criteria

- The validator and merge use the same raw URL safety rule.
- A deferred recheck survives byte-for-byte at the entry level.
- No schema-valid browser discovery can be stored with a null source kind.
- The retained partial response from `runs/20260801-110350` is still rejected
  for its 180 missing URLs.
- Unit tests and diff checks pass.

Suggested independent commit:

```text
Codex: make verdict coverage explicit and deferrable

Add an intentional deferred outcome for inconclusive rechecks, enforce one safe canonical verdict per pending URL, and require browser lifecycle metadata for newly discovered dogs.
```

## 5. WP2 — fail-fast apply and consistent output preparation

### Purpose

Prevent a render/write failure from being downgraded to a warning, entering Git
logic, or making systemd report success. Move failure-prone rendering before
state persistence and make index replacement atomic.

### Required changes

#### `src/pipeline.py`

- Reorder `apply` so it reads the current index and renders the complete updated
  Markdown before saving state.
- Keep all verdict application in memory until rendering succeeds.
- Use a dedicated atomic index writer: write to a temporary file in the index's
  directory, flush/close it, and `os.replace` it onto the destination. The
  helper belongs in the module that owns index persistence; do not overload a
  parsing/rendering function with disk orchestration.
- Retain `store.save_state` for atomic state replacement.
- Clearly document that two independent atomic replacements are not a
  cross-file transaction. A failure must propagate to the caller.
- Do not catch broad exceptions merely to log and continue.

Prefer a small pure preparation function if needed for testing, such as one that
returns `(updated_state, updated_markdown)` from loaded inputs. Do not introduce
classes or a generalized transaction framework.

#### `scripts/daily-refresh.sh`

- Treat a nonzero Codex exit as fatal even if a last message happens to exist.
- Invoke response validation only after Codex exits zero.
- Replace the warning-only apply command with an explicit fatal branch. On
  apply failure, log `FATAL`, exit nonzero, and do not run index-check, Git add,
  commit, push, report mirroring, or the success footer.
- Keep the EXIT trap so the run lock is released.
- Ensure the final success exit code represents the entire pipeline, not only
  the earlier Codex process.

### Required tests

`tests/test_pipeline.py`:

- If `render.render_index` raises, state and index files remain unchanged.
- A successful apply updates both state and index.
- The index persistence helper never leaves a truncated destination when its
  write/replace preparation fails.
- A deferred verdict remains untouched through the full pipeline apply path.

Launcher verification:

- Exercise the fatal apply branch with a controlled fake `PYTHON_BIN` or a
  disposable clone. Assert nonzero exit, released lock, and no new Git
  commit. Keep this test local and deterministic; it must not call Codex or the
  network.
- If a maintainable automated shell harness would require invasive production
  hooks, document and run the exact manual reproduction instead of adding test-
  only behavior to the launcher.

### Documentation

Update `README.md` so “fail loud” covers deterministic apply/render failures,
not only missing judge output. State explicitly that failed runs never enter
automatic Git mutation.

### Acceptance criteria

- No apply exception can reach line-of-business Git commands.
- Render failure before persistence leaves both tracked files unchanged.
- Each individual output write is atomic.
- `systemd` receives a nonzero service result for Codex, validation, apply, or
  persistence failure.
- All unit/static checks pass.

Suggested independent commit:

```text
Codex: fail the refresh when apply cannot complete

Prepare rendered output before persistence, replace the index atomically, and stop the launcher before Git whenever Codex or deterministic apply fails.
```

## 6. WP3 — real user-service network readiness

### Purpose

Ensure a persistent catch-up run does not start before NetworkManager has a
usable connection. A user manager cannot order against the system manager's
`network-online.target` on this host.

### Required changes

#### `deploy/dog-finder-daily-refresh.service`

- Remove `Wants=network-online.target` and `After=network-online.target`.
- Add `ExecStartPre=/usr/bin/nm-online -q -t 300` before `ExecStart`.
- Keep the 90-minute service timeout for the main refresh. Confirm whether
  `TimeoutStartSec` includes `ExecStartPre` on the installed system; if it does,
  the combined five-minute network wait plus refresh must still fit comfortably
  under the existing cap.
- Do not suppress `nm-online` failure. It should make the unit fail before the
  launcher mutates state.

#### `README.md`

- Record NetworkManager and `/usr/bin/nm-online` as Ubuntu deployment
  prerequisites.
- Explain the five-minute bounded wait and how to inspect a pre-start failure in
  `journalctl --user`.
- Explain that the current timer has no immediate retry policy: a failed network
  preflight waits for the next timer activation or a manual service start. Do
  not add `Restart=` behavior without an explicit owner decision.
- Retain the explicit Australia/Sydney timer semantics and lingering guidance.

### Verification

Run:

```bash
command -v nm-online
nm-online -q -t 5
systemd-analyze verify \
  deploy/dog-finder-daily-refresh.service \
  deploy/dog-finder-daily-refresh.timer
systemd-analyze calendar '*-*-* 13:00:00 Australia/Sydney'
```

Also confirm that the unit file no longer references `network-online.target`.
Do not disable networking to test failure on the production host. If an offline
test is needed, run the unit in an isolated VM/container or substitute a known
failing `ExecStartPre` only in a temporary copied unit.

### Acceptance criteria

- The unit has no dependency on a missing user target.
- A missing connection fails before `scripts/daily-refresh.sh` starts.
- Unit and calendar validation pass.
- Deployment documentation matches the actual Ubuntu dependency.

Suggested independent commit:

```text
Codex: wait for NetworkManager before daily refresh

Replace the ineffective user-level network target with a bounded nm-online preflight and document the Ubuntu network dependency.
```

## 7. WP4 — scoped Python 3.14 cleanup and resource hygiene

### Purpose

Use the new runtime baseline to remove compatibility machinery that no longer
serves the launcher, while fixing the HTTP response resource warnings visible
under Python 3.14.

### Required changes

#### Runtime documentation

- Add Python 3.14 to the `README.md` prerequisites and test section.
- State that Ubuntu's system `python3` is the supported interpreter for the
  systemd service.
- Keep the standard-library-only dependency policy.

#### Module invocation

- Change the launcher from executing `src/write_report.py` by path to:
  `"$PYTHON_BIN" -m src.write_report ...`.
- In `src/write_report.py`, replace the conditional import with the normal
  package import (`from src import dedup`, plus the shared validation owner
  chosen in WP1).
- Remove the direct-file invocation compatibility test. Existing `main()` tests
  cover behavior; optionally retain one concise subprocess test using
  `python3 -m src.write_report` if it adds unique launcher-contract coverage.
- Do not convert unrelated modules or tests to `pathlib` solely for style.

#### HTTP error cleanup

- In `src/fetch.py`, close every caught `urllib.error.HTTPError` after recording
  its code/message, including retry paths. Use `try/finally` if needed so future
  branch changes cannot leak the response object.
- Update `tests/test_fetch.py` so each attempt gets its own controlled error
  object and cleanup is deterministic.
- Add a test proving an HTTP error response is closed for both permanent 4xx and
  retried 5xx paths. Preserve existing retry/status assertions.

### Verification

Run the complete suite normally and with resource warnings visible:

```bash
python3 -m unittest discover -s tests
PYTHONDEVMODE=1 python3 -m unittest discover -s tests
```

The second command must emit no `ResourceWarning` or unraisable cleanup output.

### Acceptance criteria

- `src.write_report` has one package import path and the launcher uses `-m`.
- README names Python 3.14 as the runtime.
- Both 4xx and 5xx HTTP error objects are closed.
- The suite is clean under Python development mode.
- No broad annotation or syntax churn is included.

Suggested independent commit:

```text
Codex: align scripts with Python 3.14 runtime

Use package-style validator invocation, document the Ubuntu Python baseline, and close HTTP error responses so the suite runs without resource warnings.
```

## 8. WP5 — final review and isolated end-to-end verification

### Purpose

Prove the final code—not the pre-gate intermediate launcher—can collect live
inputs, obtain a complete schema-valid Luna response, use Firefox MCP, apply the
result, and finish successfully without mutating or pushing from the primary
worktree.

### Preflight

1. Complete WP1–WP4 and ensure each intended commit is clean.
2. Follow `AGENTS.md`: run an adversarial GPT-5.6 Sol high-thinking subagent
   review. Fix every blocking and trivial issue; repeat until no blockers remain.
3. Run the full validation matrix in section 9.
4. Confirm the global MCP configuration still matches `README.md`:

   ```bash
   codex mcp get playwright
   npx -y @playwright/mcp@0.0.78 --version
   ```

5. Confirm no refresh is active and avoid the production 13:00 window.
6. Confirm that the execution request explicitly authorizes the paid live run.
   If it does not, stop and ask the owner. Remind the owner that the judge uses
   `--dangerously-bypass-approvals-and-sandbox` and consumes model/browser
   resources. Any expansion in tools or authority requires separate approval.

### Disposable-clone protocol

Use a standalone local clone so collection, state/index mutation, remote
configuration, and any automatic data commit cannot touch or push the primary
repository:

```bash
VERIFY_PARENT="$(mktemp -d)"
VERIFY_REPO="$VERIFY_PARENT/dog-finder"
git clone --no-hardlinks "$PWD" "$VERIFY_REPO"
git -C "$VERIFY_REPO" switch --detach HEAD
git -C "$VERIFY_REPO" remote set-url --push origin DISABLED
```

Verify that the clone has its own Git directory and that only its push URL is
disabled before running. Do not use `git worktree`: linked worktrees normally
share repository configuration, so changing `remote.origin.pushurl` there could
silently disable pushes in the primary checkout. Do not reuse the primary
repository as the test target. Run the disposable clone's launcher under a
90-minute cgroup or equivalent bounded supervision. Do not add a second in-
script watchdog to production code.

Preserve and inspect the verification artifacts before removing the clone:

- Launcher/service exit is zero.
- `pending.json`, `fetch_manifest.json`, `verdicts.json`, report, and event
  stream all exist and are non-empty where required.
- The response contains exactly one canonical outcome for each pending URL.
- Any deferred records correspond to pending URLs and leave their state entries
  unchanged after apply.
- All extra URLs have `source_kind: "browser"`.
- The event stream contains `turn.completed`, has no approval cancellation, and
  shows successful Playwright calls for browser coverage.
- The report counts equal the actual outcome counts in `verdicts.json`.
- `pipeline apply` completes and the disposable index/state are consistent.
- A data-membership change may create a detached local commit, but push must be
  disabled and expected to fail harmlessly.
- The primary worktree remains byte-for-byte clean.

If Luna again emits a prose count without all verdict objects, the test fails.
Do not weaken the gate or manually fabricate the missing output. Capture the
event stream/report and stop for an owner decision about one bounded repair
retry, deterministic batching, or a model change.

After recording the evidence, remove the disposable clone using explicit paths.
Do not delete it until the failure/success artifacts have been inspected.

### Production deployment boundary

The final live test does not authorize installing/enabling the timer or pushing
the implementation commits. If the owner later asks to deploy:

1. Copy the reviewed service/timer files to `~/.config/systemd/user/`.
2. Run `systemctl --user daemon-reload`.
3. Verify the timer and next Sydney elapse before enabling it.
4. Enable lingering only if logged-out operation is required.
5. Monitor the first production service result and journal.

### Acceptance criteria

- Final adversarial review has no blockers.
- The isolated full run exits zero under the committed completeness gate.
- Browser, deferred, apply, report, and count invariants all hold.
- No primary-worktree data or remote branch is changed by verification.
- The implementing agent reports exact commits, checks, run timestamp, verdict
  counts, deferred count, browser failures, and any remaining operational risk.

## 9. Full validation matrix

Run this matrix after every work package that touches the corresponding area,
and in full before WP5:

```bash
python3 -m unittest discover -s tests
PYTHONDEVMODE=1 python3 -m unittest discover -s tests
bash -n scripts/daily-refresh.sh
python3 -m json.tool config/verdicts.schema.json >/dev/null
systemd-analyze verify \
  deploy/dog-finder-daily-refresh.service \
  deploy/dog-finder-daily-refresh.timer
systemd-analyze calendar '*-*-* 13:00:00 Australia/Sydney'
git diff --check
git status --short
```

Additional targeted checks:

- Feed the retained 191-pending/11-verdict response to the validator; it must
  fail with 180 missing pending URLs.
- Feed a pending URL represented with leading whitespace or an uppercase scheme;
  raw URL validation must reject it even though canonicalization could match.
- Feed an inconclusive stale-browser recheck as `deferred`; validation must pass
  and apply must leave the original state entry unchanged.
- Feed an extra browser discovery with null source kind; validation must fail.
- Force render failure in a unit test; neither tracked output may change.
- Force apply failure in launcher verification; no Git command may run and the
  exit status must be nonzero.

## 10. Review and version-control protocol

Before each functionally independent commit:

1. Re-read `AGENTS.md` and this plan.
2. Run the relevant validation matrix.
3. Inspect `git diff` and `git diff --check`.
4. Run the required adversarial GPT-5.6 Sol high-thinking subagent review.
5. Fix all blocking and trivial findings, then repeat review as required.
6. Stage only the files in that work package. Never stage `data/state.json`,
   `data/dog-index.md`, `runs/`, logs, browser snapshots, or unrelated owner
   changes.
7. Use the exact commit-message structure required by `AGENTS.md`, with no
   `Co-Authored-By` line.

Do not push unless the owner explicitly asks. The disposable verification clone
must have its push URL disabled before the live launcher runs.

## 11. Stop conditions and final hand-over

Stop and ask the owner rather than guessing if any of these occurs:

- A schema accepted by Codex cannot represent `deferred` under the strict-output
  restrictions of the installed CLI/model.
- The complete response exceeds model limits or Luna repeatedly omits bulk
  rejections after the prompt is explicit.
- NetworkManager is no longer the target host's network manager.
- Correct apply behavior appears to require a generalized two-file transaction
  or destructive state rollback.
- The live test would overlap an active/production refresh.
- Verification requires enabling the timer, changing MCP tools, broadening
  filesystem authority, or pushing a branch.

The final report to the owner must include:

- work-package and commit list;
- tests/static checks and Python version;
- adversarial-review result;
- isolated live-run timestamp and exit status;
- pending, qualified, rejected, adopted, deferred, and extra-browser counts;
- browser sources that were unreachable;
- confirmation that primary data and remotes were untouched by verification;
- any residual risk or explicit follow-up decision.
