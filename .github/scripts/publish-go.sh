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

sync_issue_record() {
  local pr_url="$1"
  local create_pr="$2"
  local here pr_body_file
  here=$(cd "$(dirname "$0")" && pwd)
  pr_body_file="${RUNNER_TEMP}/pr-body.md"
  python3 "$here/issue_agent.py" pr-body > "$pr_body_file"
  if [[ -z "$pr_url" && "$create_pr" == "true" ]]; then
    title="$(gh issue view "$ISSUE_NUMBER" --repo "$REPOSITORY" --json title --jq .title)"
    gh pr create \
      --repo "$REPOSITORY" \
      --base "$DEFAULT_BRANCH" \
      --head "$WORK_BRANCH" \
      --title "$title" \
      --body-file "$pr_body_file"
    pr_url="$(
      gh pr list --repo "$REPOSITORY" --head "$WORK_BRANCH" --json url --jq '.[0].url // empty'
    )"
  elif [[ -n "$pr_url" ]]; then
    gh pr edit "$pr_url" --repo "$REPOSITORY" --body-file "$pr_body_file"
  fi
  PR_URL="$pr_url" \
    HEAD_SHA="$(git rev-parse HEAD)" \
    OMITTED_WORKFLOWS="$omitted_workflows" \
    python3 "$here/issue_agent.py" sync-record
}

git fetch origin "$DEFAULT_BRANCH"
commit_leftover_changes
omit_workflow_commits

ahead="$(git rev-list --count "origin/${DEFAULT_BRANCH}..HEAD")"
if [[ "$ahead" == "0" ]]; then
  echo "No commits ahead of ${DEFAULT_BRANCH}; skip push."
  pr_url="$(
    gh pr list --repo "$REPOSITORY" --head "$WORK_BRANCH" --json url --jq '.[0].url // empty'
  )"
  sync_issue_record "$pr_url" false
  exit 0
fi

git push -u origin "HEAD:${WORK_BRANCH}"

pr_url="$(
  gh pr list --repo "$REPOSITORY" --head "$WORK_BRANCH" --json url --jq '.[0].url // empty'
)"
sync_issue_record "$pr_url" true
