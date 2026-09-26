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

mode=""
if [[ "$body" =~ @agent[[:space:]]+(plan|go)([^[:alnum:]_]|$) ]]; then
  mode="${BASH_REMATCH[1],,}"
fi

if [[ -z "$mode" ]]; then
  echo "invalid=true" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT required}"
  echo "No supported @agent subcommand (plan | go)."
  if [[ -n "${ISSUE_NUMBER:-}" && -n "${REPOSITORY:-}" && -n "${GH_TOKEN:-}" ]]; then
    usage=$'⚠️ この Issue コメントでは `@agent` のサブコマンドを認識できませんでした。\n\n| コマンド | 用途 | workflow |\n| --- | --- | --- |\n| `@agent plan` | 方針のすり合わせ（コメント返信） | cursor-issue-agent.yml |\n| `@agent sync` | 議論を Issue 概要に反映 | cursor-issue-sync.yml |\n| `@agent go` | 実装・PR 作成 | cursor-issue-agent.yml |\n\n**同じコメント内の追加メッセージ**もエージェントが読みます。'
    gh issue comment "$ISSUE_NUMBER" --repo "$REPOSITORY" --body "$usage" || true
  fi
  exit 0
fi

{
  echo "mode=$mode"
  echo "invalid=false"
} >> "$GITHUB_OUTPUT"

echo "Parsed @agent mode: $mode"
