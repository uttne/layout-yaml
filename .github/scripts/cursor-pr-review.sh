#!/usr/bin/env bash
set -euo pipefail

REVIEW_OUTPUT_PATH="${REVIEW_OUTPUT_PATH:-$RUNNER_TEMP/pr-review.md}"
PROMPT_TEMPLATE_PATH="${PROMPT_TEMPLATE_PATH:-.github/workflows/prompts/pr-review-agent.md}"
PROJECT_REVIEW_CONTEXT_PATH="${PROJECT_REVIEW_CONTEXT_PATH:-.cursor/pr-review.md}"

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
    -e "s|\$PR_NUMBER|${PR_NUMBER}|g" \
    -e "s|\$PR_HEAD_SHA|${PR_HEAD_SHA}|g" \
    -e "s|\$PR_BASE_SHA|${PR_BASE_SHA}|g" \
    -e "s|\$TRIGGERED_BY|${TRIGGERED_BY}|g" \
    -e "s|\$REVIEW_OUTPUT_PATH|${REVIEW_OUTPUT_PATH}|g"
}

project_context=""
if [[ -f "$PROJECT_REVIEW_CONTEXT_PATH" ]]; then
  project_context="$(substitute_prompt_vars < "$PROJECT_REVIEW_CONTEXT_PATH")"
  echo "Including project review context from ${PROJECT_REVIEW_CONTEXT_PATH}."
else
  echo "No project review context at ${PROJECT_REVIEW_CONTEXT_PATH} (skipping)."
fi

prompt="$(substitute_prompt_vars < "$PROMPT_TEMPLATE_PATH" | sed '/<!-- PROJECT_REVIEW_CONTEXT -->/d')"
if [[ -n "$project_context" ]]; then
  prompt="${prompt}

## プロジェクト固有のレビュー指針

${project_context}"
fi

if [[ -f ".github/scripts/pr-review-progress.sh" ]]; then
  bash .github/scripts/pr-review-progress.sh agent_running
fi

echo "Starting agent review for PR #${PR_NUMBER}..."
rm -f "$REVIEW_OUTPUT_PATH"

if ! cursor-agent --force --model "${MODEL:-composer-2.5[fast=false]}" --output-format=text --print "$prompt"; then
  echo "cursor-agent failed."
  exit 1
fi

if [[ ! -s "$REVIEW_OUTPUT_PATH" ]]; then
  echo "Review output was not written to ${REVIEW_OUTPUT_PATH}."
  exit 1
fi

if [[ -f ".github/scripts/pr-review-progress.sh" ]]; then
  bash .github/scripts/pr-review-progress.sh posting
fi

footer=$'\n\n---\n_Cursor エージェントによるレビュー（[workflow run]('"$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"')）_'

{
  cat "$REVIEW_OUTPUT_PATH"
  printf '%s\n' "$footer"
} > "${REVIEW_OUTPUT_PATH}.posted"

gh pr comment "$PR_NUMBER" --repo "$REPOSITORY" --body-file "${REVIEW_OUTPUT_PATH}.posted"
echo "Posted PR conversation comment."
