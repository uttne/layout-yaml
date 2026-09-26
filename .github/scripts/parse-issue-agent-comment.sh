#!/usr/bin/env bash
# Parse @agent subcommand from an Issue comment body.
# Sets GITHUB_OUTPUT: mode=plan|go, or writes invalid=1 and posts usage (when ISSUE_NUMBER set).

set -euo pipefail

body=""
if [[ -n "${TRIGGER_COMMENT_PATH:-}" && -f "$TRIGGER_COMMENT_PATH" ]]; then
  body="$(tr -d '\r' < "$TRIGGER_COMMENT_PATH")"
elif [[ -n "${TRIGGER_COMMENT_BODY:-}" ]]; then
  body="${TRIGGER_COMMENT_BODY}"
fi

if [[ -z "$body" ]]; then
  echo "Trigger comment body is empty (set TRIGGER_COMMENT_PATH or TRIGGER_COMMENT_BODY)."
  exit 1
fi

# Subcommand is the first word on the same line as @agent.
# [[:blank:]] is space/tab only, so a newline does not pull the next
# paragraph in as a subcommand (`@agent` then `PR ...` stays plan).
# Empty token and "plan" are plan; "go" is go.
mode=""
token=""
if [[ "$body" =~ @agent[[:blank:]]*([A-Za-z0-9_]*) ]]; then
  token="${BASH_REMATCH[1],,}"
fi

case "$token" in
  "" | plan) mode="plan" ;;
  go) mode="go" ;;
esac

if [[ -z "$mode" ]]; then
  echo "invalid=true" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT required}"
  echo "No supported @agent subcommand (bare @agent | plan | go). token=${token:-<none>}"
  if [[ -n "${ISSUE_NUMBER:-}" && -n "${REPOSITORY:-}" && -n "${GH_TOKEN:-}" ]]; then
    usage=$'⚠️ `@agent` の指定を認識できませんでした。\n\n| コメント | 動作 |\n| --- | --- |\n| `@agent` または `@agent plan` | 方針の会話（コメント返信） |\n| `@agent sync` | 議論を Issue 概要に反映 |\n| `@agent go` | 実装・PR 作成 |\n\n同じコメントの続きと、`@agent` が無い過去コメントも読みます。'
    gh issue comment "$ISSUE_NUMBER" --repo "$REPOSITORY" --body "$usage" || true
  fi
  exit 0
fi

{
  echo "mode=$mode"
  echo "invalid=false"
} >> "$GITHUB_OUTPUT"

echo "Parsed @agent mode: $mode"
