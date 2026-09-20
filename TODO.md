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

## Next tasks

- S2: Validate permitted PetRescue access and benchmark representative DeepSeek matching
  quality/cost within an explicitly allocated evaluation budget. No live source access or
  paid requests are part of scaffolding.
- S3b: Extend S3a with editing, link recovery/rotation, address-wide management, renewal,
  reminders, native one-click unsubscribe, and complete retention/suppression semantics.
- S4: Add Procrastinate and the durable email-intent/SES event flow; exercise ambiguous
  acceptance, suppression, and cancellation races before enabling delivery.
- S5: Adapt shared ingestion, source publication, baselines, candidates, and direct AI
  matching; preserve overflow and enforce atomic spend reservations.
- S6: Complete daily scheduling, retention, backup/restore, monitoring, deployment, and
  capacity/quality validation before public launch.

Keep stable IDs. Before implementing a task, record its intent, dependencies, non-goals,
validation, and completion criteria. Remove completed active entries and keep a concise
disposition. Record superseding decisions with their reasoning before committing.
