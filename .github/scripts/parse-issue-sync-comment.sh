#!/usr/bin/env bash
# Require @agent sync in the trigger comment.
set -euo pipefail

body=""
if [[ -n "${TRIGGER_COMMENT_PATH:-}" && -f "$TRIGGER_COMMENT_PATH" ]]; then
  body="$(tr -d '\r' < "$TRIGGER_COMMENT_PATH")"
elif [[ -n "${TRIGGER_COMMENT_BODY:-}" ]]; then
  body="${TRIGGER_COMMENT_BODY}"
fi

if [[ -z "$body" ]]; then
  echo "Trigger comment body is empty."
  exit 1
fi

if [[ ! "$body" =~ @agent[[:space:]]+sync([^[:alnum:]_]|$) ]]; then
  echo "invalid=true" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT required}"
  if [[ -n "${ISSUE_NUMBER:-}" && -n "${REPOSITORY:-}" && -n "${GH_TOKEN:-}" ]]; then
    usage=$'⚠️ `@agent sync` を認識できませんでした。\n\nIssue コメントで次の形式を使ってください:\n\n```\n@agent sync\n\n（任意: 反映の指示・除外したいコメントなど）\n```\n\n`@agent plan` / `@agent go` は `.github/workflows/cursor-issue-agent.yml` を参照してください。'
    gh issue comment "$ISSUE_NUMBER" --repo "$REPOSITORY" --body "$usage" || true
  fi
  exit 0
fi

echo "invalid=false" >> "$GITHUB_OUTPUT"
echo "Parsed @agent sync."
