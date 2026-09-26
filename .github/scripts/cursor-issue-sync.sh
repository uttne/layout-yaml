#!/usr/bin/env bash
set -euo pipefail

: "${REPOSITORY:?REPOSITORY is required}"
: "${ISSUE_NUMBER:?ISSUE_NUMBER is required}"
: "${TRIGGER_COMMENT_ID:?TRIGGER_COMMENT_ID is required}"

PROMPT_TEMPLATE_PATH="${PROMPT_TEMPLATE_PATH:-.github/workflows/prompts/issue-agent-sync.md}"
PROJECT_CONTEXT_PATH="${PROJECT_CONTEXT_PATH:-.cursor/issue-agent.md}"
ISSUE_BODY_OUTPUT_PATH="${ISSUE_BODY_OUTPUT_PATH:-$RUNNER_TEMP/issue-body.md}"
SYNC_RECORD_OUTPUT_PATH="${SYNC_RECORD_OUTPUT_PATH:-$RUNNER_TEMP/issue-sync-record.md}"

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

read_trigger_comment() {
  if [[ -n "${TRIGGER_COMMENT_PATH:-}" && -f "$TRIGGER_COMMENT_PATH" ]]; then
    tr -d '\r' < "$TRIGGER_COMMENT_PATH"
    return
  fi
  if [[ -n "${TRIGGER_COMMENT_BODY:-}" ]]; then
    printf '%s' "$TRIGGER_COMMENT_BODY" | tr -d '\r'
    return
  fi
  echo "Trigger comment body is missing." >&2
  exit 1
}

substitute_prompt_vars() {
  sed \
    -e "s|\$REPOSITORY|${REPOSITORY}|g" \
    -e "s|\$ISSUE_NUMBER|${ISSUE_NUMBER}|g" \
    -e "s|\$TRIGGERED_BY|${TRIGGERED_BY:-}|g" \
    -e "s|\$TRIGGER_COMMENT_ID|${TRIGGER_COMMENT_ID}|g" \
    -e "s|\$GITHUB_RUN_ID|${GITHUB_RUN_ID}|g" \
    -e "s|\$ISSUE_BODY_OUTPUT_PATH|${ISSUE_BODY_OUTPUT_PATH}|g" \
    -e "s|\$SYNC_RECORD_OUTPUT_PATH|${SYNC_RECORD_OUTPUT_PATH}|g"
}

project_context=""
if [[ -f "$PROJECT_CONTEXT_PATH" ]]; then
  project_context="$(substitute_prompt_vars < "$PROJECT_CONTEXT_PATH")"
fi

prompt="$(substitute_prompt_vars < "$PROMPT_TEMPLATE_PATH" | sed '/<!-- PROJECT_ISSUE_CONTEXT -->/d')"
if [[ -n "$project_context" ]]; then
  prompt="${prompt}

## プロジェクト固有の作業指針

${project_context}"
fi

trigger_comment="$(read_trigger_comment)"
prompt="${prompt}

## 依頼者のコメント（全文・必読）

\`\`\`markdown
${trigger_comment}
\`\`\`"

if [[ -f ".github/scripts/issue-sync-progress.sh" ]]; then
  bash .github/scripts/issue-sync-progress.sh agent_running
fi

echo "Starting @agent sync for issue #${ISSUE_NUMBER}..."
rm -f "$ISSUE_BODY_OUTPUT_PATH" "$SYNC_RECORD_OUTPUT_PATH"

if ! cursor-agent --force --model "${MODEL:-composer-2.5[fast=false]}" --output-format=text --print "$prompt"; then
  echo "cursor-agent failed."
  exit 1
fi

if [[ ! -s "$ISSUE_BODY_OUTPUT_PATH" ]]; then
  echo "Issue body was not written to ${ISSUE_BODY_OUTPUT_PATH}."
  exit 1
fi

if [[ ! -s "$SYNC_RECORD_OUTPUT_PATH" ]]; then
  echo "Sync record was not written to ${SYNC_RECORD_OUTPUT_PATH}."
  exit 1
fi

if [[ -f ".github/scripts/issue-sync-progress.sh" ]]; then
  bash .github/scripts/issue-sync-progress.sh updating_body
fi

gh issue edit "$ISSUE_NUMBER" --repo "$REPOSITORY" --body-file "$ISSUE_BODY_OUTPUT_PATH"
echo "Updated issue #${ISSUE_NUMBER} body."

if [[ -f ".github/scripts/issue-sync-progress.sh" ]]; then
  bash .github/scripts/issue-sync-progress.sh posting_record
fi

footer=$'\n\n---\n_Cursor エージェント（`@agent sync`）— [workflow run]('"$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"')_'
{
  cat "$SYNC_RECORD_OUTPUT_PATH"
  printf '%s\n' "$footer"
} > "${SYNC_RECORD_OUTPUT_PATH}.posted"

gh issue comment "$ISSUE_NUMBER" --repo "$REPOSITORY" --body-file "${SYNC_RECORD_OUTPUT_PATH}.posted"
echo "Posted sync record on issue #${ISSUE_NUMBER}."
