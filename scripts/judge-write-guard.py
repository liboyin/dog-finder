#!/usr/bin/python3
"""PreToolUse hook guarding the headless judge's file writes.

Claude Code 2.1.202 ignores path-scoped permission rules for the Write tool
(probed 2026-07-17: ``Write(runs/**)``, ``Write(//abs/**)``, and ``./``-prefixed
forms all fail to match on BOTH the allow and the deny side; only an unscoped
``"Write"`` rule works, which would grant filesystem-wide writes). This hook
enforces the intended scope deterministically instead: a Write/Edit-family tool
call is allowed only when its target resolves under the repo's ``runs/``
directory, and denied anywhere else. If this script itself fails, no allow
decision is emitted and the permission system falls through to dontAsk's
default deny — fail-closed.

stdin: the hook event JSON. stdout: a permission decision carrying both the
current ``hookSpecificOutput.permissionDecision`` schema and the legacy
``decision`` field, for CLI-version tolerance.
"""
from __future__ import annotations

import json
import os
import sys

ALLOWED_ROOT = "/Users/fanguard/Code/dog-finder/runs"


def decide(path: str) -> tuple[bool, str]:
    """Decide whether a write target is inside the allowed runs/ area.

    Args:
        path: The tool call's target path (absolute or cwd-relative).

    Returns:
        An (allowed, reason) tuple. The parent directory is resolved through
        symlinks so a link planted inside runs/ can't redirect the write
        elsewhere; the leaf may not exist yet (a new file).
    """
    if not path:
        return False, "no file path in tool input"
    allowed_root = os.path.realpath(ALLOWED_ROOT)
    target = os.path.abspath(path)
    resolved = os.path.join(
        os.path.realpath(os.path.dirname(target)), os.path.basename(target)
    )
    if resolved.startswith(allowed_root + os.sep):
        return True, "run-artifact area"
    return False, f"judge may write only under {ALLOWED_ROOT}; got {path!r}"


def main() -> int:
    """Read the hook event from stdin and emit an allow/deny decision."""
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    allowed, reason = decide(path)
    print(json.dumps({
        "decision": "approve" if allowed else "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if allowed else "deny",
            "permissionDecisionReason": reason,
        },
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
