#!/usr/bin/env python3
"""Parse a Claude Code stream-json run.

Args: <stream_file> <report_file> <ts> <exit_code>
- Writes the human-readable final result text to <report_file>.
- Prints an aggregate + per-model usage block to stdout (appended to usage.log
  by the caller).
"""
import json
import sys
from datetime import datetime


def main() -> int:
    """Parse a run's stream-json for its result and emit usage stats.

    Reads the four positional CLI args (``<stream_file> <report_file> <ts>
    <exit_code>``), writes the judge's human-readable final result text to
    ``report_file``, and prints an aggregate plus per-model usage block to stdout
    (the launcher appends it to ``usage.log``). A stream that is missing or has no
    ``result`` event (a hard failure) prints a ``NO_RESULT`` marker instead, and
    ``report_file`` is left unwritten.

    Returns:
        0 always; failures are reported in the printed line, not the exit code.
    """
    stream_file, report_file, ts, exit_code = sys.argv[1:5]

    result = None
    try:
        with open(stream_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "result":
                    result = obj  # keep the last one
    except FileNotFoundError:
        pass

    stamp = datetime.now().strftime("%F %T %Z").strip()

    if result is None:
        # No result event — usually a hard failure (e.g. rate limit, crash).
        print(f"[{stamp}] ts={ts} exit={exit_code} NO_RESULT "
              f"(no result event in stream; see daily-refresh.log)")
        return 0

    # Readable report text
    with open(report_file, "w", encoding="utf-8") as out:
        out.write(result.get("result", "") or "")

    total_cost = result.get("total_cost_usd", 0) or 0
    turns = result.get("num_turns", 0) or 0
    dur_s = (result.get("duration_ms", 0) or 0) / 1000.0
    subtype = result.get("subtype", "")
    model_usage = result.get("modelUsage", {}) or {}

    # True totals = sum across all models/agents. (The top-level `usage` block
    # only reflects the main thread's last iteration, NOT the grand total, so
    # we aggregate modelUsage instead. Cost comes from the authoritative
    # total_cost_usd field.)
    tot_in = sum((m.get("inputTokens", 0) or 0) for m in model_usage.values())
    tot_out = sum((m.get("outputTokens", 0) or 0) for m in model_usage.values())
    tot_cr = sum((m.get("cacheReadInputTokens", 0) or 0) for m in model_usage.values())
    tot_cc = sum((m.get("cacheCreationInputTokens", 0) or 0) for m in model_usage.values())

    print(f"[{stamp}] ts={ts} exit={exit_code} subtype={subtype}")
    print(f"  TOTAL  cost=${total_cost:.4f}  turns={turns}  dur={dur_s:.1f}s  "
          f"in={tot_in}  out={tot_out}  cache_read={tot_cr}  cache_creation={tot_cc}")

    # Per-model breakdown: coordinator (Sonnet) vs crawlers (Haiku), etc.
    for model, mu in model_usage.items():
        print(f"  MODEL  {model}  cost=${mu.get('costUSD', 0):.4f}  "
              f"in={mu.get('inputTokens', 0)}  out={mu.get('outputTokens', 0)}  "
              f"cache_read={mu.get('cacheReadInputTokens', 0)}  "
              f"cache_creation={mu.get('cacheCreationInputTokens', 0)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
