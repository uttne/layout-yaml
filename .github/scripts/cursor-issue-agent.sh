#!/usr/bin/env bash
set -euo pipefail

AGENT_MODE="${AGENT_MODE:?AGENT_MODE must be plan or go}"
: "${REPOSITORY:?REPOSITORY is required}"
: "${ISSUE_NUMBER:?ISSUE_NUMBER is required}"
PROMPT_TEMPLATE_PATH="${PROMPT_TEMPLATE_PATH:-.github/workflows/prompts/issue-agent-${AGENT_MODE}.md}"
ISSUE_REPLY_OUTPUT_PATH="${ISSUE_REPLY_OUTPUT_PATH:-$RUNNER_TEMP/issue-agent-reply.md}"

if [[ -z "${CURSOR_API_KEY:-}" ]]; then
  echo "CURSOR_API_KEY is not configured."
  exit 1
fi
if [[ ! -f "$PROMPT_TEMPLATE_PATH" ]]; then
  echo "Prompt template not found: $PROMPT_TEMPLATE_PATH"
  exit 1
fi
if ! command -v cursor-agent >/dev/null 2>&1; then
  echo "cursor-agent was not found in PATH."
  exit 1
fi

here=$(cd "$(dirname "$0")" && pwd)
py=(python3 "$here/issue_agent.py")
prompt_file="${RUNNER_TEMP}/issue-agent-prompt.md"
"${py[@]}" prompt > "$prompt_file"

"${py[@]}" progress agent_running
echo "Starting @agent ${AGENT_MODE} for issue #${ISSUE_NUMBER}..."
rm -f "$ISSUE_REPLY_OUTPUT_PATH"

poll_pid=""
stop_note_poll() {
  if [[ -n "$poll_pid" ]]; then
    kill "$poll_pid" 2>/dev/null || true
    wait "$poll_pid" 2>/dev/null || true
    poll_pid=""
  fi
}
trap stop_note_poll EXIT
if [[ "$AGENT_MODE" == "go" && -n "${GO_NOTE_PATH:-}" ]]; then
  "${py[@]}" poll &
  poll_pid=$!
fi

agent_status=0
cursor-agent \
  --force \
  --model "${MODEL:-composer-2.5[fast=false]}" \
  --output-format=text \
  --print "$(cat "$prompt_file")" || agent_status=$?
stop_note_poll
trap - EXIT

if [[ "$agent_status" -ne 0 ]]; then
  echo "cursor-agent failed."
  exit "$agent_status"
fi

if [[ "$AGENT_MODE" == "plan" ]]; then
  if [[ ! -s "$ISSUE_REPLY_OUTPUT_PATH" ]]; then
    echo "Plan reply was not written to ${ISSUE_REPLY_OUTPUT_PATH}."
    exit 1
  fi
  "${py[@]}" progress posting
  footer=$'\n\n---\n_Cursor エージェント（`@agent plan`）— [workflow run]('"$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"')_'
  {
    cat "$ISSUE_REPLY_OUTPUT_PATH"
    printf '%s\n' "$footer"
  } > "${ISSUE_REPLY_OUTPUT_PATH}.posted"
  gh issue comment "$ISSUE_NUMBER" --repo "$REPOSITORY" --body-file "${ISSUE_REPLY_OUTPUT_PATH}.posted"
  echo "Posted plan reply on issue #${ISSUE_NUMBER}."
fi
