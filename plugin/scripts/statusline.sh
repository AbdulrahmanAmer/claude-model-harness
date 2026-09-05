#!/bin/sh
# Optional status line that caches model.id for the harness (fallback rank 3, see FINDINGS §1) and
# prints a short status. Status line stdin JSON has model.id / model.display_name [src: S22].
# Install: copy to ~/.claude/harness/statusline.sh and set settings.json "statusLine": {"type":"command","command":"~/.claude/harness/statusline.sh"}
set -u
IN=$(cat 2>/dev/null || true)
DIR="${HARNESS_HOME:-$HOME/.claude}/harness"
if command -v jq >/dev/null 2>&1; then
  ID=$(printf '%s' "$IN" | jq -r '.model.id // empty' 2>/dev/null)
  NAME=$(printf '%s' "$IN" | jq -r '.model.display_name // empty' 2>/dev/null)
  SID=$(printf '%s' "$IN" | jq -r '.session_id // empty' 2>/dev/null)
  EFF=$(printf '%s' "$IN" | jq -r '.effort.level // empty' 2>/dev/null)
  if [ -n "$ID" ]; then
    mkdir -p "$DIR" 2>/dev/null && printf '{"model_id":"%s","source":"statusline:model.id","session_id":"%s","ts":"%s"}\n' \
      "$ID" "$SID" "$(date +%Y-%m-%dT%H:%M:%S 2>/dev/null)" > "$DIR/model.json" 2>/dev/null
  fi
  printf '[%s | %s%s]' "${NAME:-?}" "${ID:-unknown}" "${EFF:+ | effort $EFF}"
else
  printf '[harness: jq missing]'
fi
exit 0
