#!/usr/bin/env bash
set -euo pipefail

AGENT_MODE="${AGENT_MODE:?AGENT_MODE must be plan or go}"
: "${REPOSITORY:?REPOSITORY is required}"
: "${ISSUE_NUMBER:?ISSUE_NUMBER is required}"
PROMPT_TEMPLATE_PATH="${PROMPT_TEMPLATE_PATH:-.github/workflows/prompts/issue-agent-${AGENT_MODE}.md}"
PROJECT_CONTEXT_PATH="${PROJECT_CONTEXT_PATH:-.cursor/issue-agent.md}"
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

substitute_prompt_vars() {
  sed \
    -e "s|\$REPOSITORY|${REPOSITORY}|g" \
    -e "s|\$ISSUE_NUMBER|${ISSUE_NUMBER}|g" \
    -e "s|\$TRIGGERED_BY|${TRIGGERED_BY}|g" \
    -e "s|\$ISSUE_REPLY_OUTPUT_PATH|${ISSUE_REPLY_OUTPUT_PATH}|g" \
    -e "s|\$DEFAULT_BRANCH|${DEFAULT_BRANCH:-main}|g" \
    -e "s|\$WORK_BRANCH|${WORK_BRANCH:-}|g"
}

# Full comment body may contain newlines and sed delimiters; inject via env block in prompt assembly.
read_trigger_comment() {
  if [[ -n "${TRIGGER_COMMENT_PATH:-}" && -f "$TRIGGER_COMMENT_PATH" ]]; then
    tr -d '\r' < "$TRIGGER_COMMENT_PATH"
    return
  fi
  if [[ -n "${TRIGGER_COMMENT_BODY:-}" ]]; then
    printf '%s' "$TRIGGER_COMMENT_BODY" | tr -d '\r'
    return
  fi
  echo "Trigger comment body is missing (set TRIGGER_COMMENT_PATH or TRIGGER_COMMENT_BODY)." >&2
  exit 1
}

project_context=""
if [[ -f "$PROJECT_CONTEXT_PATH" ]]; then
  project_context="$(substitute_prompt_vars < "$PROJECT_CONTEXT_PATH")"
  echo "Including project context from ${PROJECT_CONTEXT_PATH}."
fi

prompt="$(substitute_prompt_vars < "$PROMPT_TEMPLATE_PATH" | sed '/<!-- PROJECT_ISSUE_CONTEXT -->/d')"

trigger_comment="$(read_trigger_comment)"
if [[ -n "$project_context" ]]; then
  prompt="${prompt}

## プロジェクト固有の作業指針

${project_context}"
fi

prompt="${prompt}

## 依頼者のコメント（全文・必読）

次の Markdown ブロックは、今回のワークフローを起動した Issue コメントの**全文**です。
\`@agent ${AGENT_MODE}\` 以外の行も、制約・優先順位・スコープとして**すべて尊重**してください。

\`\`\`markdown
${trigger_comment}
\`\`\`"

if [[ -f ".github/scripts/issue-agent-progress.sh" ]]; then
  bash .github/scripts/issue-agent-progress.sh agent_running
fi

echo "Starting @agent ${AGENT_MODE} for issue #${ISSUE_NUMBER}..."
rm -f "$ISSUE_REPLY_OUTPUT_PATH"

agent_args=(--force --model "${MODEL:-composer-2.5[fast=false]}" --output-format=text --print "$prompt")

if ! cursor-agent "${agent_args[@]}"; then
  echo "cursor-agent failed."
  exit 1
fi

if [[ "$AGENT_MODE" == "plan" ]]; then
  if [[ ! -s "$ISSUE_REPLY_OUTPUT_PATH" ]]; then
    echo "Plan reply was not written to ${ISSUE_REPLY_OUTPUT_PATH}."
    exit 1
  fi
  if [[ -f ".github/scripts/issue-agent-progress.sh" ]]; then
    bash .github/scripts/issue-agent-progress.sh posting
  fi
  footer=$'\n\n---\n_Cursor エージェント（`@agent plan`）— [workflow run]('"$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"')_'
  {
    cat "$ISSUE_REPLY_OUTPUT_PATH"
    printf '%s\n' "$footer"
  } > "${ISSUE_REPLY_OUTPUT_PATH}.posted"
  gh issue comment "$ISSUE_NUMBER" --repo "$REPOSITORY" --body-file "${ISSUE_REPLY_OUTPUT_PATH}.posted"
  echo "Posted plan reply on issue #${ISSUE_NUMBER}."
fi
