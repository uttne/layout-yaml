#!/usr/bin/env bash
# Push the go branch without workflow file changes, open a PR if needed,
# and upsert one Issue comment that records implementation progress.

set -euo pipefail

: "${REPOSITORY:?REPOSITORY is required}"
: "${ISSUE_NUMBER:?ISSUE_NUMBER is required}"
: "${WORK_BRANCH:?WORK_BRANCH is required}"
: "${DEFAULT_BRANCH:?DEFAULT_BRANCH is required}"

GO_STATUS_PATH="${GO_STATUS_PATH:-$RUNNER_TEMP/go-status.md}"
omitted_workflows="false"

discard_workflow_worktree() {
  if [[ -d .github/workflows ]]; then
    git checkout -- .github/workflows 2>/dev/null || true
    git clean -fd -- .github/workflows
  fi
}

commit_leftover_changes() {
  discard_workflow_worktree
  git add -A
  git restore --staged -- .github/workflows 2>/dev/null || true
  if ! git diff --cached --quiet; then
    git commit -m "Save in-progress work for #${ISSUE_NUMBER}."
  fi
}

omit_workflow_commits() {
  local base="origin/${DEFAULT_BRANCH}"
  local changed
  changed="$(git diff --name-only "${base}...HEAD" -- .github/workflows || true)"
  if [[ -z "$changed" ]]; then
    return 0
  fi
  echo "Removing .github/workflows changes from the branch before push."
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if git cat-file -e "${base}:${path}" 2>/dev/null; then
      git checkout "$base" -- "$path"
    else
      git rm -f -- "$path" || true
    fi
  done <<< "$changed"
  git add -A -- .github/workflows
  if ! git diff --cached --quiet; then
    git commit -m "Omit .github/workflows changes (Actions does not push workflow files)."
    omitted_workflows="true"
  fi
}

upsert_progress_comment() {
  local head_sha head_short pr_url status_body body comment_id
  head_sha="$(git rev-parse HEAD)"
  head_short="${head_sha:0:7}"
  pr_url="$(
    gh pr list --repo "$REPOSITORY" --head "$WORK_BRANCH" --json url --jq '.[0].url // empty'
  )"

  if [[ -s "$GO_STATUS_PATH" ]]; then
    status_body="$(cat "$GO_STATUS_PATH")"
  else
    status_body=$'### ここまでできたこと\n\n（エージェントの記録ファイルが無いため、ブランチのコミットを確認してください）\n\n### まだ残っていること\n\n（未記録）'
  fi

  if [[ "$omitted_workflows" == "true" ]]; then
    status_body+=$'\n\n- `.github/workflows/` の変更は Actions から push していない。workflow ファイルは手元で追加する。'
  fi

  body="$(cat <<EOF
## @agent go 実装記録

| 項目 | 値 |
| --- | --- |
| ブランチ | \`${WORK_BRANCH}\` |
| HEAD | \`${head_short}\` |
| PR | ${pr_url:-未作成} |
| 再開 | 次の \`@agent go\` はこのブランチの続きから行う |

${status_body}

<!-- layout-yaml-agent-go
branch: ${WORK_BRANCH}
head_sha: ${head_sha}
pr_url: ${pr_url}
-->
EOF
)"

  comment_id="$(
    gh api --paginate "repos/$REPOSITORY/issues/$ISSUE_NUMBER/comments" \
      --jq '.[] | select(.body | contains("layout-yaml-agent-go")) | .id' \
      | tail -n 1 \
      || true
  )"

  if [[ -n "$comment_id" ]]; then
    gh api --method PATCH \
      "repos/$REPOSITORY/issues/comments/$comment_id" \
      -f body="$body" >/dev/null
    echo "Updated go progress comment $comment_id."
  else
    gh issue comment "$ISSUE_NUMBER" --repo "$REPOSITORY" --body "$body" >/dev/null
    echo "Posted go progress comment."
  fi
}

git fetch origin "$DEFAULT_BRANCH"
commit_leftover_changes
omit_workflow_commits

ahead="$(git rev-list --count "origin/${DEFAULT_BRANCH}..HEAD")"
if [[ "$ahead" == "0" ]]; then
  echo "No commits ahead of ${DEFAULT_BRANCH}; skip push and pull request."
  upsert_progress_comment
  exit 0
fi

git push -u origin "HEAD:${WORK_BRANCH}"

pr_url="$(
  gh pr list --repo "$REPOSITORY" --head "$WORK_BRANCH" --json url --jq '.[0].url // empty'
)"
if [[ -z "$pr_url" ]]; then
  title="$(gh issue view "$ISSUE_NUMBER" --repo "$REPOSITORY" --json title --jq .title)"
  gh pr create \
    --repo "$REPOSITORY" \
    --base "$DEFAULT_BRANCH" \
    --head "$WORK_BRANCH" \
    --title "$title" \
    --body "$(printf 'Closes #%s\n' "$ISSUE_NUMBER")"
fi

upsert_progress_comment
