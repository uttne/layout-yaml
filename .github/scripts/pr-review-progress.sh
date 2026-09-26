#!/usr/bin/env bash
# Post or update a single PR comment showing @agent review checkpoints.
# Usage: pr-review-progress.sh <stage>
# Stages: received | pr_resolved | checked_out | cli_ready | agent_running | posting | completed | failed

set -euo pipefail

stage="${1:?stage required}"

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPOSITORY:?REPOSITORY is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"

PROGRESS_COMMENT_ID_FILE="${RUNNER_TEMP}/pr-review-progress-comment-id"
RUN_URL="${RUN_URL:-${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID:-unknown}}"
TRIGGERED_BY="${TRIGGERED_BY:-}"
HEAD_SHORT="${PR_HEAD_SHA:-}"
if [[ -n "$HEAD_SHORT" && ${#HEAD_SHORT} -gt 7 ]]; then
  HEAD_SHORT="${HEAD_SHORT:0:7}"
fi

CHECKPOINTS=(
  "リクエスト受付"
  "PR 情報の取得"
  "差分のチェックアウト"
  "レビュー環境の準備（Cursor CLI）"
  "エージェントによる分析"
  "レビュー結果の投稿"
  "完了"
)

stage_index() {
  case "$1" in
    received) echo 0 ;;
    pr_resolved) echo 1 ;;
    checked_out) echo 2 ;;
    cli_ready) echo 3 ;;
    agent_running) echo 4 ;;
    posting) echo 5 ;;
    completed) echo 6 ;;
    *) echo 0 ;;
  esac
}

ACTIVE_INDEX_FILE="${RUNNER_TEMP}/pr-review-progress-active-index"

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
  local i status icon
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

  local meta=""
  if [[ -n "$TRIGGERED_BY" ]]; then
    meta+="依頼: @${TRIGGERED_BY}  "
  fi
  if [[ -n "$HEAD_SHORT" ]]; then
    meta+=$'\n'"Head: \`${HEAD_SHORT}\`"
  fi

  cat <<EOF
## @agent レビュー進捗

${meta}

| チェックポイント | 状態 |
| --- | --- |
${lines}
[ワークフロー実行](${RUN_URL})

_このコメントはチェックポイントごとに自動更新されます。完了後に別コメントでレビュー本文を投稿します。_
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
      "repos/$REPOSITORY/issues/$PR_NUMBER/comments" \
      -f body="$body" \
      --jq .id
  )"
  echo "$comment_id" > "$PROGRESS_COMMENT_ID_FILE"
fi

echo "Progress comment updated (stage=$stage, id=$comment_id)."
