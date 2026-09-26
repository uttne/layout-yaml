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
    usage=$'⚠️ この Issue コメントでは `@agent` のサブコマンドを認識できませんでした。\n\n| コマンド | 用途 |\n| --- | --- |\n| `@agent plan` | 実装方針のすり合わせ（リポジトリは変更しない） |\n| `@agent go` | 実装開始・PR 作成 |\n\n**同じコメント内の追加メッセージ**（改行以降の指示・制約・優先順位など）もエージェントが読みます。\n\n例:\n```\n@agent go\n\n#4 の合格基準どおり。コミットメッセージに (#4) を付けて。\n```'
    gh issue comment "$ISSUE_NUMBER" --repo "$REPOSITORY" --body "$usage" || true
  fi
  exit 0
fi

{
  echo "mode=$mode"
  echo "invalid=false"
} >> "$GITHUB_OUTPUT"

echo "Parsed @agent mode: $mode"
