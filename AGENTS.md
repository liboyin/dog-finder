This file owns the working principles for this repository. All agents MUST follow it and explicit user instructions. CAPITALIZED requirement words have the meanings defined by BCP 14 (RFC 2119 and RFC 8174).

# Document Boundaries

- **AGENTS.md:** concise working principles and required standards.
- **[Adversarial review skill](.agents/skills/adversarial-review/SKILL.md):** how to conduct review, including dispatch, snapshots, investigation, triage, and reporting.
- **[PLAN.md](PLAN.md):** the execution plan for in-flight work — work packages, accepted decisions, execution boundaries, and its own maintenance rules.
- **[README.md](README.md):** current architecture, dataflow, design decisions and assumptions, product intent, and build/test/deploy procedures.
- **[prompts/daily-refresh.md](prompts/daily-refresh.md):** the contract for the unattended LLM judge — its inputs, the required one-verdict-per-pending-URL coverage, and the browser re-check rules.

Link to the owning document instead of duplicating its procedure. Operational instructions do not override the safety and ownership principles here.

# Scope and Decisions

- Read relevant code and documentation and inspect repository status before editing. Preserve unrelated work.
- Each change MUST have a boundary: intent, dependencies, non-goals, validation strategy, and done criteria. Revalidate written tasks against the affected code; do not implement them mechanically or broaden their material scope unilaterally.
- State assumptions. Confirm unresolved choices that materially affect scope, architecture, dataflow, correctness, security, or user-visible behavior before dependent work; continue independent work where possible.
- Accepted decisions and user authorization persist. Do not ask again about settled choices. Document superseding decisions and their reasoning before committing the affected change.
- Non-material assumptions MAY be made when repository evidence supports them and they preserve the requested outcome. Name the assumption, evidence, and effect in the handoff.
- Isolated subtasks with small, bounded results SHOULD use subagents. The main agent remains accountable for integration and verification.

# Design and Documentation

- Prefer the simplest cohesive implementation within the assigned scope. Give each function, class, and module a clear responsibility; prefer pure logic, isolated side effects, and minimal mocking over unnecessary abstractions.
- Do not split cohesive code solely for length, or restructure unrelated modules for style. A narrow exception MUST explain the responsibility or invariant it preserves.
- Before removing a layer, identify all unique behavior it carries, including copy, errors, ordering, timing, diagnostics, and index/output formatting. Give retained behavior an explicit owner and preserve its verification.
- Verify changing language, framework, library, and service assumptions empirically or against version-appropriate documentation.
- Update documentation when the change makes it stale. Distinguish current behavior, accepted future decisions, proposals, and unverified hypotheses.
- Verify current empirical claims before recording them. Historical evidence MUST identify its revision, relevant environment, provenance, and limitations; it does not certify current validation.
- Every new or changed non-test function or method MUST have a Google-style docstring covering its purpose and any non-obvious contract, side effects, or constraints. Unit test functions MUST have a one-line docstring describing the protected behavior. Comments should explain non-obvious reasons or trade-offs.

# Test Guidelines

- Tests MUST protect behavior or an invariant and fail when it breaks. Prefer controlled inputs and `tests/fixtures/` HTML over live fetches, and explicit assertions over elapsed-time waits.
- For each added or changed invariant, mutation evidence MUST cover a revert, a plausible regression, and an over-restriction where applicable. Each applicable mutant MUST fail a relevant test in an isolated scratch copy. Explain inapplicable categories; evidence belongs to the invariant and MAY be shared across assertions.
- Before removing or weakening coverage, demonstrate that a mutant breaking the protected property still fails another test. A surviving mutant requires investigation, not automatic removal of coverage.
- Import the module under test as `import src.my_module as testee`; call functions as `testee.function_name` and patch its attributes with `patch.object(testee, 'attribute', ...)`. Order test functions to match the source file's function order.
- Automated tests MUST NOT perform network access, launch a real browser or the Codex CLI, depend on a third-party package, or mutate real repository state, even temporarily. Operate on in-memory structures or a `tempfile`-provided path, never the repository's real `data/state.json`, `data/dog-index.md`, `runs/`, or Git state. Snapshot/restore is permitted only for state the test owns.
- Any subprocess, temporary directory, or monkeypatch a test creates MUST be cleaned up in that test, including after failures and timeouts.
- `python3 -m unittest discover -s tests` passing on the Ubuntu 26.04 system Python 3.14 interpreter (`python3`) is the coverage policy; there is no separate coverage tool. Planned changes to test scope belong in PLAN.md. Record unperformed manual checks as limitations.

# Validation and Review

- Establish a passing baseline at HEAD before implementation. Reuse baseline evidence only for the same unchanged revision and relevant environment, with provenance. A failing baseline SHOULD be fixed in a separate, authorized change first.
- Use focused checks during development. The final code, test, or configuration candidate MUST pass the full suite — `python3 -m unittest discover -s tests` — on the Ubuntu 26.04 system Python 3.14 interpreter, with no `ResourceWarning` or other new warnings; explain any accepted tooling warning. Shell, JSON, and systemd-unit changes MUST pass their static checks (e.g. `bash -n`, a JSON parse, `systemd-analyze verify`).
- Every non-trivial code, test, or configuration change MUST pass the review skill's complete procedure before commit. A change is non-trivial if it could affect runtime behavior, test guarantees, build/deploy output, security, state or index dataflow, Git-mutation behavior, or the content of `data/dog-index.md`. When uncertain, run the review.
- The reviewer owns classification and verdict; the main agent owns independent investigation, implementation, and required user dispositions. After fixes or rollback, repeat full gates and obtain a fresh review. Finish only when no Blocking finding remains and every surfaced finding has its required disposition. Never silently discard or reclassify a finding.
- Documentation-only changes and read-only assessments are exempt from application gates and formal adversarial review. Verify their claims, references, completeness, and diff instead. Report what was actually checked.
- Verify success with checks that distinguish failure. Explain non-zero exits, verify absence directly, and verify rollback against the recorded pre-change state.
- Clean up processes and artifacts you create. Identify owned PIDs before using `kill`; NEVER use `pkill -f`. Re-check this file and the task boundary before finishing.

# Version Control

- Keep functionally independent changes in separate, self-contained commits once implemented, validated, and documented. Honor requests to leave drafts uncommitted.
- Stage explicit paths, inspect the staged diff and repository status immediately before committing, and exclude unrelated work. NEVER use `git add -A` or `git commit -a`.
- Commit messages MUST start with `<Claude/Codex/Antigravity/...>: <one-line summary>`, followed by a blank line and explanatory paragraphs. Do not add a `Co-Authored-By` line. (The unattended daily launcher's own `Automated run on YYYY-MM-DD` commits are a documented exception; see README.)
