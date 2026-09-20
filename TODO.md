# TODO — Future Work

Read [USER_STORIES.md](USER_STORIES.md) and [README.md](README.md) before accepting an implementation task. This file owns outstanding work, accepted engineering decisions, dependencies, and task boundaries. README owns current architecture and operating instructions, and USER_STORIES owns product behavior.

**Status:** started 2026-09-18 to record engineering decisions for the planned multi-user service. The backlog will be derived from USER_STORIES once its open questions are resolved.

## Maintaining this plan

1. Give each decision and task a stable ID. Do not recycle IDs.
2. Record accepted decisions with their rationale and the work they affect. When a decision changes, record what supersedes it and why before the implementation commit.
3. Keep unassigned work compact. Before implementing a task, expand it into a full boundary: intent, dependencies, implementation direction, non-goals, validation, and done criteria.
4. In each implementation commit, remove the completed task's active entry and keep at most a short disposition needed for traceability.

## Accepted engineering decisions

| ID | Date | Decision | Rationale | Affects |
|---|---|---|---|---|
| E1 | 2026-09-18 | The service calls LLMs through LiteLLM with provider API keys, starting with DeepSeek. The personal Codex subscription is not used. | A personal subscription can't serve a multi-user SaaS. LiteLLM keeps the provider swappable without rewriting call sites. | Free-text matching, retiring the personal pipeline |

### Constraints that follow from E1

- Automated tests for the service must not depend on a third-party package or access the network. LiteLLM calls MUST sit behind one narrow adapter, so matching logic is tested against a fake and never imports LiteLLM.
- Only a search's free-text description and public listing text reach the provider. Email address, postcode, interstate-adoption choice, and search name never do (USER_STORIES *Privacy and Consent*).
- Before relying on them, verify against version-appropriate documentation: LiteLLM's DeepSeek support, structured (JSON) output, rate limits, pricing, and the data-retention terms needed for the privacy page. Pin the LiteLLM version.
