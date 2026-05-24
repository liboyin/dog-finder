#!/bin/zsh
# Daily-refresh launcher for the Sydney poodle-index.
# Invoked by launchd (com.poodle-index.daily-refresh) at 21:00 local time.
# Lives outside ~/Documents so the launchd agent isn't blocked by macOS TCC.
#
# Captures usage two ways:
#   Tier 1 (aggregate + per-model): parsed from the final result event into usage.log
#   Tier 2 (full event stream):     saved to runs/run-<ts>.stream.jsonl for per-subagent analysis
# The agent prompt is extracted live from daily-refresh-prompt.md (everything
# after the first "---" line) so that file stays the single source of truth.

DIR="$HOME/poodle-index"
PROMPT_FILE="$DIR/daily-refresh-prompt.md"
LOG="$DIR/daily-refresh.log"
USAGE_LOG="$DIR/usage.log"
RUNS="$DIR/runs"

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "$RUNS"
cd "$DIR" || { echo "$(date '+%F %T %Z') FATAL: cannot cd to $DIR" >> "$LOG"; exit 1; }

TS="$(date '+%Y%m%d-%H%M%S')"
STREAM="$RUNS/run-$TS.stream.jsonl"
REPORT="$RUNS/run-$TS.report.txt"

echo "===== run started $(date '+%F %T %Z') (ts=$TS) =====" >> "$LOG"

PROMPT="$(awk 'f; /^---$/{f=1}' "$PROMPT_FILE")"
if [ -z "$PROMPT" ]; then
  echo "$(date '+%F %T %Z') FATAL: empty prompt extracted from $PROMPT_FILE" >> "$LOG"
  exit 1
fi

# Tier 2: full event stream -> STREAM ; human-readable progress/errors -> LOG
/usr/local/bin/claude -p "$PROMPT" \
  --model sonnet \
  --dangerously-skip-permissions \
  --output-format stream-json --verbose > "$STREAM" 2>>"$LOG"
CODE=$?

# Tier 1: parse the final result event for aggregate + per-model usage.
python3 "$DIR/parse_usage.py" "$STREAM" "$REPORT" "$TS" "$CODE" >> "$USAGE_LOG" 2>>"$LOG"

# Mirror the readable report into the main log if we got one.
if [ -s "$REPORT" ]; then
  echo "--- report (ts=$TS) ---" >> "$LOG"
  cat "$REPORT" >> "$LOG"
fi

echo "===== run finished $(date '+%F %T %Z') (exit $CODE) =====" >> "$LOG"
exit $CODE
