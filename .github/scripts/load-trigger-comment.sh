#!/usr/bin/env bash
# Fetch the triggering issue comment body into RUNNER_TEMP and set TRIGGER_COMMENT_PATH.
set -euo pipefail

: "${REPOSITORY:?REPOSITORY is required}"
: "${COMMENT_ID:?COMMENT_ID is required}"

gh api "repos/$REPOSITORY/issues/comments/$COMMENT_ID" | jq -r .body > "$RUNNER_TEMP/trigger-comment.md"
echo "TRIGGER_COMMENT_PATH=$RUNNER_TEMP/trigger-comment.md" >> "${GITHUB_ENV:?GITHUB_ENV is required}"
