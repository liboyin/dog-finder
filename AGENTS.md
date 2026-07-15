This document contains guidelines that all AI agents MUST follow.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, NOT RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted as described in BCP 14 (IETF RFC 2119 and RFC 8174) when, and only when, they appear in all capitals, as shown here.

# Meta Guidelines

- You MUST read relevant code & documentation, and plan your actions before making a file change.
- State assumptions explicitly. When you notice an ambiguity that materially affects the project (e.g. scope, architecture, dataflow, correctness, or security), you MUST confirm with the user before continuing.
- Isolated subtasks (tasks that require little or no additional context from the main conversation and produce a small, well-bounded result for follow-up work) SHOULD be executed in subagents to keep the main context window clean.
- Before considering a task done, you MUST re-check that all instructions in this file are followed.

# Documentation Guidelines

- Each document SHOULD own its assigned topic, and other docs SHOULD link or summarize without becoming competing sources of truth.
- Documentation MUST be updated as soon as its content no longer reflects the latest state of the project.
- `README.md` describes project structure, architecture, dataflow, and build & test procedures.
- Design decisions & assumptions MUST be documented in whichever document fits best (e.g. README, a design doc, or the task's execution log), and SHOULD record the reasoning behind them.
- New or modified functions/methods in non-test scripts MUST have Google-style docstrings; unit test functions MUST have a one-line docstring.

# Implementation Guidelines

- Implement only what was asked with small, surgical changes. Do not add features or unrelated refactors unless explicitly asked to.
- Prefer the simplest implementation. Each function/class/module MUST have a single responsibility and a well-defined interface; other SOLID principles MAY be relaxed in favor of simplicity.
- Implementations MUST be easy to test with minimal mocking. Pure functions are preferred, and side effects SHOULD be isolated.

# Test Guidelines

- Tests MUST encode WHY behavior matters, not just WHAT it does. A test that does not fail when business logic changes is wrong.
- Order test functions to match the source file's function order.
- Import the module under test as `import src.my_module as testee`; call functions as `testee.function_name` and mock attributes via `patch.object(testee, 'attribute', ...)`.

# Review Guidelines

Before committing, perform an adversarial review of the changes in a subagent running Fable 5 in plan mode:

- Does it achieve the intended purpose?
- Is it bug-free?
- Can it be simplified?
- Is it consistent with the documentation?
- Are there design flaws or anti-patterns?
- Are there design choices that make testing or validation unnecessarily difficult?
- Anything else a senior reviewer would push back on? (Use judgment)

If issues are surfaced, the main agent MUST fix all blocking issues and trivial issues. Repeat the review-fix loop until there are no blocking issues left.

# Version Control Guidelines

- Commit each functionally independent change once fully implemented, tested, and documented.
- Commit messages MUST follow this template. Do not add "Co-Authored-By" line:

```
<Your name: Claude/Codex/Antigravity/...>: <one-line summary>

<One paragraph describing the change in detail. If more than one paragraph is necessary to explain the change, the commit SHOULD be broken down.>
```
