# Implementation work

Read [USER_STORIES.md](USER_STORIES.md), [DESIGN.md](DESIGN.md), and [AGENTS.md](AGENTS.md)
before implementation. README owns verified setup and current behaviour.

## Accepted decisions

| ID | Decision | Status |
|---|---|---|
| E1 | LiteLLM adapter and dependency-free service tests | Superseded by E2; retained here for traceability |
| E2 | HTTPX DeepSeek adapter, Django/PostgreSQL, uv, pytest and pytest-django | Accepted in DESIGN.md and explicitly confirmed for pytest; minimizes dependencies while allowing realistic framework/database tests |
| E3 | Retire personal automation immediately | Authorized 2026-09-20; timer disabled and runner removed; personal data preserved |

## Completed

- S1: Python 3.12/uv environment, locked dependencies, Django settings and probes,
  pytest/Ruff/coverage configuration, local PostgreSQL configuration, CI definition,
  and development documentation. Validation details belong in the implementation handoff.

- S3a completed: validated creation, local confirmation capture, scanner-safe activation,
  scoped management/cancellation, quota concurrency checks, postcode import, and housekeeping.
  Production registration stays disabled. See README for the implemented preview boundary.

- S3b editing slice completed: shared validation, immutable owner address, stale-form
  protection, matching revisions, and baseline-preserving renames. PostgreSQL concurrency
  tests cover competing edits and cancellation. Matching queue integration remains in S5.

- S3b renewal slice completed: protected manual renewal, non-stacking terms, expiry/grace
  status, and quota-safe reactivation. Active renewals preserve baselines; grace renewals
  advance the matching revision. Concurrent renewals, activation, and cancellation are
  verified against PostgreSQL; reminder delivery and matching integration remain below.

- S3b native unsubscribe receiver completed: separate cancellation-only credentials,
  RFC 8058 form POST validation, scanner-safe method restrictions, idempotent replies,
  and shared cancellation locking. Migration rollback and credential/race tests verified;
  outgoing headers, HTTPS/DKIM deployment, and queued-send integration remain in S4.

- S3b recovery/dashboard slice completed: local recovery email, seven-day single-use
  confirmation, shared creation/recovery limits, and isolated address-wide access to
  active/grace searches. PostgreSQL concurrency, scope, rendered pages, and migration
  rollback verified. Live delivery remains outstanding.

- S3b exposed-link replacement completed: opt-in mailbox recovery atomically rotates
  address-wide and individual management credentials without changing search state or
  native unsubscribe credentials. Stale browser cancellation is checked under the same
  lock; replay, competing replacements, and unchanged default recovery are verified.

- S3b reminder preview completed: unique search/expiry records, seven-day planning,
  current-link HTML/text rendering, and local-only capture with lifecycle rechecks.
  Deduplication, failure rollback, concurrency, and migration rollback verified.
  Scheduling and provider send/acceptance semantics remain in S4/S6.

- S3b suppression transition completed: internal address-wide blocking, search
  cancellation/criteria erasure, recovery revocation, and pending reminder invalidation
  under one lifecycle lock. Idempotency, failure rollback, housekeeping persistence,
  admission release, and concurrent transitions verified. No public/provider endpoint added.

## Next tasks

- S2: Validate permitted PetRescue access and benchmark representative DeepSeek matching
  quality/cost within an explicitly allocated evaluation budget. No live source access or
  paid requests are part of scaffolding.
- S3b: Set retention policy and implement minimal retained suppression records.
- S4: Add Procrastinate and the durable email-intent/SES event flow; exercise ambiguous
  acceptance, suppression, and cancellation races before enabling delivery.
- S5: Adapt shared ingestion, source publication, baselines, candidates, and direct AI
  matching; preserve overflow and enforce atomic spend reservations.
- S6: Complete daily scheduling, retention, backup/restore, monitoring, deployment, and
  capacity/quality validation before public launch.

Keep stable IDs. Before implementing a task, record its intent, dependencies, non-goals,
validation, and completion criteria. Remove completed active entries and keep a concise
disposition. Record superseding decisions with their reasoning before committing.
