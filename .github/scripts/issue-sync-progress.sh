#!/usr/bin/env bash
# Progress comment for @agent sync workflow.
set -euo pipefail

stage="${1:?stage required}"

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPOSITORY:?REPOSITORY is required}"
: "${ISSUE_NUMBER:?ISSUE_NUMBER is required}"

PROGRESS_COMMENT_ID_FILE="${RUNNER_TEMP}/issue-sync-progress-comment-id"
RUN_URL="${RUN_URL:-${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID:-unknown}}"
TRIGGERED_BY="${TRIGGERED_BY:-}"

CHECKPOINTS=(
  "リクエスト受付"
  "Issue・コメントの読み取り"
  "リポジトリのチェックアウト"
  "エージェント環境の準備"
  "概要文案の生成"
  "Issue 本文の更新"
  "同期記録の投稿"
  "完了"
)

stage_index() {
  case "$1" in
    received) echo 0 ;;
    context_loaded) echo 1 ;;
    checked_out) echo 2 ;;
    cli_ready) echo 3 ;;
    agent_running) echo 4 ;;
    updating_body) echo 5 ;;
    posting_record) echo 6 ;;
    completed) echo 7 ;;
    *) echo 0 ;;
  esac
}

ACTIVE_INDEX_FILE="${RUNNER_TEMP}/issue-sync-progress-active-index"

if [[ "$stage" == "failed" ]]; then
  active_index="$(<"${ACTIVE_INDEX_FILE:-/dev/null}" 2>/dev/null || echo 0)"
else
  active_index="$(stage_index "$stage")"
  echo "$active_index" > "$ACTIVE_INDEX_FILE"
fi

meta="モード: \`@agent sync\`"
if [[ -n "$TRIGGERED_BY" ]]; then
  meta+=$'\n'"依頼: @${TRIGGERED_BY}"
fi

lines=""
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

body="$(cat <<EOF
## @agent sync 進捗

${meta}

| チェックポイント | 状態 |
| --- | --- |
${lines}
[ワークフロー実行](${RUN_URL})

_このコメントはチェックポイントごとに自動更新されます。_
EOF
)"

if [[ -f "$PROGRESS_COMMENT_ID_FILE" ]]; then
  comment_id="$(<"$PROGRESS_COMMENT_ID_FILE")"
  gh api --method PATCH \
    "repos/$REPOSITORY/issues/comments/$comment_id" \
    -f body="$body" >/dev/null
else
  comment_id="$(
    gh api --method POST \
      "repos/$REPOSITORY/issues/$ISSUE_NUMBER/comments" \
      -f body="$body" \
      --jq .id
  )"
  echo "$comment_id" > "$PROGRESS_COMMENT_ID_FILE"
fi

echo "Sync progress updated (stage=$stage, id=$comment_id)."
