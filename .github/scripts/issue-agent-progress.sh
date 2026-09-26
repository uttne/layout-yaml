#!/usr/bin/env bash
# Post or update a single Issue comment showing @agent plan/go checkpoints.
# Usage: issue-agent-progress.sh <stage>
# Env: ISSUE_NUMBER, REPOSITORY, AGENT_MODE (plan|go), optional BRANCH_NAME

set -euo pipefail

stage="${1:?stage required}"

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPOSITORY:?REPOSITORY is required}"
: "${ISSUE_NUMBER:?ISSUE_NUMBER is required}"
: "${AGENT_MODE:?AGENT_MODE is required}"

PROGRESS_COMMENT_ID_FILE="${RUNNER_TEMP}/issue-agent-progress-comment-id"
RUN_URL="${RUN_URL:-${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID:-unknown}}"
TRIGGERED_BY="${TRIGGERED_BY:-}"

if [[ "$AGENT_MODE" == "plan" ]]; then
  CHECKPOINTS=(
    "リクエスト受付"
    "Issue コンテキストの取得"
    "リポジトリのチェックアウト"
    "エージェント環境の準備（Cursor CLI）"
    "方針の整理"
    "Issue への返信投稿"
    "完了"
  )
else
  CHECKPOINTS=(
    "リクエスト受付"
    "Issue コンテキストの取得"
    "リポジトリのチェックアウト"
    "作業ブランチの準備"
    "エージェント環境の準備（Cursor CLI）"
    "実装・テスト"
    "push と PR 作成"
    "完了"
  )
fi

stage_index() {
  case "$AGENT_MODE:$1" in
    plan:received) echo 0 ;;
    plan:issue_loaded) echo 1 ;;
    plan:checked_out) echo 2 ;;
    plan:cli_ready) echo 3 ;;
    plan:agent_running) echo 4 ;;
    plan:posting) echo 5 ;;
    plan:completed) echo 6 ;;
    go:received) echo 0 ;;
    go:issue_loaded) echo 1 ;;
    go:checked_out) echo 2 ;;
    go:branch_ready) echo 3 ;;
    go:cli_ready) echo 4 ;;
    go:agent_running) echo 5 ;;
    go:publishing) echo 6 ;;
    go:completed) echo 7 ;;
    *) echo 0 ;;
  esac
}

ACTIVE_INDEX_FILE="${RUNNER_TEMP}/issue-agent-progress-active-index"

if [[ "$stage" == "failed" ]]; then
  if [[ -f "$ACTIVE_INDEX_FILE" ]]; then
    active_index="$(<"$ACTIVE_INDEX_FILE")"
  else
    active_index=0
  fi
else
  active_index="$(stage_index "$stage")"
  echo "$active_index" > "$ACTIVE_INDEX_FILE"
fi

render_body() {
  local i icon
  local lines=""
  for i in "${!CHECKPOINTS[@]}"; do
    if [[ "$stage" == "failed" && "$i" -eq "$active_index" ]]; then
      icon="❌"
    elif [[ "$stage" == "completed" || "$i" -lt "$active_index" ]]; then
      icon="✅"
    elif [[ "$i" -eq "$active_index" && "$stage" != "completed" ]]; then
      icon="🔄"
    else
      icon="⏳"
    fi
    lines+="| ${CHECKPOINTS[$i]} | ${icon} |"$'\n'
  done

  local meta="モード: \`@agent ${AGENT_MODE}\`"
  if [[ -n "$TRIGGERED_BY" ]]; then
    meta+=$'\n'"依頼: @${TRIGGERED_BY}"
  fi
  if [[ -n "${BRANCH_NAME:-}" ]]; then
    meta+=$'\n'"ブランチ: \`${BRANCH_NAME}\`"
  fi

  cat <<EOF
## @agent Issue 進捗

${meta}

| チェックポイント | 状態 |
| --- | --- |
${lines}
[ワークフロー実行](${RUN_URL})

_このコメントはチェックポイントごとに自動更新されます。_
EOF
}

body="$(render_body)"

if [[ -f "$PROGRESS_COMMENT_ID_FILE" ]]; then
  comment_id="$(<"$PROGRESS_COMMENT_ID_FILE")"
  gh api --method PATCH \
    -H "Accept: application/vnd.github+json" \
    "repos/$REPOSITORY/issues/comments/$comment_id" \
    -f body="$body" >/dev/null
else
  comment_id="$(
    gh api --method POST \
      -H "Accept: application/vnd.github+json" \
      "repos/$REPOSITORY/issues/$ISSUE_NUMBER/comments" \
      -f body="$body" \
      --jq .id
  )"
  echo "$comment_id" > "$PROGRESS_COMMENT_ID_FILE"
fi

echo "Issue progress updated (mode=$AGENT_MODE, stage=$stage, id=$comment_id)."
