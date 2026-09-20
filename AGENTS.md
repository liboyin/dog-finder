This file owns the working principles for this repository. Agents MUST follow it and explicit user instructions. Capitalized requirement words use the meanings defined by BCP 14 (RFC 2119 and RFC 8174).

# Document Boundaries

- **AGENTS.md:** working principles and engineering standards.
- **[USER_STORIES.md](USER_STORIES.md):** product behaviour, accepted defaults, and open product decisions.
- **[DESIGN.md](DESIGN.md):** selected architecture, capacity and budget constraints, implementation sequence, and proposals still requiring validation.
- **[README.md](README.md):** implemented behaviour and verified setup, run, and test procedures. It may describe the personal pipeline until the SaaS replacement exists.

Link to the owning document instead of duplicating its procedures. Distinguish implemented behaviour, accepted future decisions, proposals, and unverified assumptions. Resolve conflicts using explicit user decisions; do not silently treat a design proposal as an accepted product change.

# Scope and Decisions

- Read relevant code and documentation and inspect repository status before editing. Preserve unrelated work.
- Each change MUST have a clear intent, dependencies, non-goals, validation strategy, and completion criteria. Keep this proportionate to the task; a small change does not need a separate planning document.
- Revalidate written tasks against the actual code. Do not implement stale instructions mechanically or broaden material scope unilaterally.
- Accepted decisions and authorization persist. Do not ask again about settled choices. Clarify unresolved choices that materially affect scope, architecture, correctness, privacy, cost, or user-visible behaviour before dependent work; continue independent work where possible.
- Routine implementation choices MAY be resolved using repository evidence and judgment. Report material assumptions and limitations in the handoff.
- The initial service has a 250-active-subscriber cap, five searches per address, a US$50 monthly target, and a US$100 ceiling before tax. DESIGN.md owns the detailed accounting and admission rules. Do not raise limits, drop eligible work, or weaken matching to make a cost estimate fit.
- Work on the SaaS does not itself authorize retiring or modifying the running personal pipeline, its timer, or its data. Keep migration and retirement within their explicitly authorized scope.
- A local Python environment is supported; Docker is optional. Do not require a container solely to work on this repository.

# Design and Python Standards

- Prefer the simplest cohesive implementation within scope and established libraries that materially reduce implementation or maintenance work.
- Follow the selected Django/PostgreSQL/Procrastinate architecture. Keep pages server-rendered and provider integrations small. Additional services, agent frameworks, or a preference rules engine need a demonstrated reason and an explicit design decision.
- Give functions, classes, and modules clear responsibilities. Prefer pure matching and lifecycle logic with isolated database, network, and filesystem effects.
- Use Python 3.12-compatible code, uv-managed dependencies and a committed lockfile once bootstrapped. Use Django migrations for application schema changes and the library's supported migration mechanism for queue tables.
- Add useful type annotations. Avoid `Any` and blanket `type: ignore`; narrowly justified exceptions must explain the external constraint and remain localized.
- New or changed non-test functions, methods, and classes MUST have Google-style docstrings describing purpose and non-obvious contracts, side effects, or constraints. Keep simple docstrings short. Test names describe the protected behaviour and tests have a one-line docstring.
- Respect lint limits without splitting cohesive code solely for length. Explain narrow exceptions in terms of the responsibility or invariant they preserve.
- Before removing a layer, identify the behaviour it carries, including errors, ordering, timing, diagnostics, and public interfaces. Give retained behaviour an explicit owner and preserve its verification.
- Verify changing framework, library, API, pricing, and source-access assumptions against version-appropriate primary documentation or direct evidence. Label cost scenarios as estimates and record their assumptions and date.
- Update the owning documentation when behaviour or accepted decisions change. Never document unrun commands as verified procedures.

# Correctness and External Effects

- Ingest a listing once for the whole service and reuse it across searches. A failed refresh or missing page is not evidence that a dog was adopted. Do not replace a good source snapshot with a failed or incomplete run.
- Preserve the baseline, criteria-revision, overflow, renewal, and sent-listing rules in USER_STORIES.md. Persist progress before acknowledging work; retries and overlapping workers must not recreate logical operations.
- Enforce quotas and lifecycle transitions atomically in PostgreSQL. Use consistent lock ordering. Do not rely on in-memory counters for service-wide capacity or spending limits.
- Treat listing text and search descriptions as untrusted data. Validate model responses, retain uncertainty, and retry failures rather than treating them as rejected dogs. Bound request size, concurrency, output, retries, and spending.
- Email acceptance is not inbox delivery. An ambiguous SES send MUST NOT be retried blindly. Preserve the durable intent and reconcile provider events before deciding what happened.
- Recheck cancellation, expiry, suppression, and criteria revision before sending. Cancellation and suppression must prevent future queued sends; already in-flight provider requests need the documented boundary.
- Management links are credentials. Keep them and personal data out of logs, analytics, error reports, test fixtures, and AI requests except for the explicitly permitted description/listing text.
- Browser GET requests MUST NOT activate, edit, renew, or cancel searches. Use explicit protected mutations and the separately scoped native unsubscribe endpoint.
- Treat secrets and `.env` values as confidential. Do not echo, log, commit, or transmit them. Use least-privilege credentials outside the repository.
- Unit and integration tests do not authorize live scraping, paid AI calls, real email, cloud provisioning, production migrations, or deployment. Use real services only within an explicitly authorized integration or operational task, with bounded usage.

# Testing and State Ownership

- Tests MUST protect behaviour or an invariant and fail when it breaks. Prefer controlled inputs, injected clocks, and explicit completion over sleeps.
- For important changed invariants, demonstrate that a plausible regression fails a relevant test. Use an isolated scratch copy for deliberate mutations; never mutate production or user-owned state. Test both allowed and forbidden cases where appropriate so an implementation that rejects everything cannot pass.
- Before removing or weakening coverage, identify where the protected behaviour remains verified. Investigate surviving regressions rather than deleting inconvenient tests.
- Import the module under test as `import package.module as testee`, using the actual package name. Call `testee.function_name` and patch attributes with `patch.object(testee, "attribute", ...)` when mocking is necessary. Prefer injected dependencies over extensive patching.
- Automated tests MUST NOT contact PetRescue, DeepSeek, SES, or other external services. Use sanitized fixtures and controlled responses for parser and provider tests.
- Database tests MUST use a disposable, explicitly identified test PostgreSQL database and test-owned queue state. Never point tests at the development or production database. Do not substitute SQLite for tests of PostgreSQL locking or queue behaviour.
- Use test-owned filesystem paths, environment variables, settings, and clients, with fixtures such as `tmp_path` and `monkeypatch` owning teardown. Do not write to `data/state.json`, the personal index, real service configuration, or host browser profiles.
- Background tasks, threads, and asynchronous clients MUST be stopped or awaited at test teardown, including after timeouts and failures. No test may leave work running against later tests' state. Tests must be order-independent.
- Prioritize concurrency and failure tests for activation caps, baseline publication, edits during matching, send ambiguity, duplicated events, cancellation, suppression, and atomic spending reservations.
- Keep model-quality and cost evaluation separate from deterministic CI tests. Record model/prompt versions, fixture provenance, usage, and limitations; paid evaluations require an authorized budget.

# Validation and Handoff

- Establish the relevant baseline before implementation where runnable checks exist. Reuse evidence only for the same unchanged revision and relevant environment. Report existing failures and missing infrastructure; do not silently repair unrelated issues.
- Use focused checks during development. For the final code/configuration candidate, run relevant tests and configured lint, formatting, typing, coverage, and framework checks. Investigate new warnings and non-zero exits.
- Once the corresponding tooling is configured, expected commands include `uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .`. Django changes also require `uv run python manage.py check`; model changes require checking for missing migrations with `uv run python manage.py makemigrations --check --dry-run`. Use test/development settings and a disposable database where required.
- The repository's actual configuration and README own executable commands and coverage thresholds. Do not claim a nonexistent coverage script, mypy setup, Django project, or test suite has passed. Bootstrap required checks with the implementation rather than adding unrelated tooling to a documentation task.
- Database and queue changes need verification of transaction behaviour and migrations against disposable PostgreSQL. UI/email changes need checks of the affected rendered output, including error states and plain-text email where applicable.
- Documentation-only changes are exempt from application test gates. Check references, consistency, completeness, and whitespace/diff instead.
- No mandatory adversarial review process applies at this stage. Ordinary self-review and relevant validation still apply.
- Clean up only processes and artifacts you created. Identify owned PIDs before terminating them; never use broad process-killing patterns. Destructive database, volume, or personal-pipeline operations require explicit authorization.
- Before finishing, recheck this file, the task boundary, repository status, and the final diff. Report what changed, what was actually verified, and any remaining limitations. Historical results do not certify current validation.

# Version Control

- Keep functionally independent changes in separate, self-contained commits when committing is authorized. Honor requests to leave drafts uncommitted.
- Stage explicit paths and inspect the staged diff and repository status immediately before committing. Exclude unrelated work. NEVER use `git add -A` or `git commit -a`.
- Commit messages MUST start with `<agent name>: <one-line summary>`, for example `Codex: Add subscription lifecycle models`, followed by a blank line and explanatory paragraphs. Do not add a `Co-Authored-By` line.

Adapted from the user's [youtube-whisperer working principles](https://raw.githubusercontent.com/liboyin/youtube-whisperer/refs/heads/main/AGENTS.md), with project-specific architecture, state ownership, and validation rules. Its Docker-only constraint, media-service details, and adversarial review procedure do not apply here.
