#!/usr/bin/env bash
# Reuse the Issue's implementation branch when one already exists.
# Writes work_branch and resumed to GITHUB_OUTPUT.

set -euo pipefail

: "${REPOSITORY:?REPOSITORY is required}"
: "${ISSUE_NUMBER:?ISSUE_NUMBER is required}"
: "${DEFAULT_BRANCH:?DEFAULT_BRANCH is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"

preferred="agent/issue-${ISSUE_NUMBER}"
work_branch=""
resumed="false"

remote_has() {
  git ls-remote --exit-code --heads origin "$1" >/dev/null 2>&1
}

comment_branch="$(
  gh api --paginate "repos/$REPOSITORY/issues/$ISSUE_NUMBER/comments" \
    --jq '.[] | select(.body | contains("layout-yaml-agent-go")) | .body' \
    | sed -n 's/^branch:[[:space:]]*//p' \
    | tail -n 1 \
    || true
)"

if [[ -n "$comment_branch" ]] && remote_has "$comment_branch"; then
  work_branch="$comment_branch"
  resumed="true"
fi

if [[ -z "$work_branch" ]]; then
  pr_branch="$(
    gh pr list --repo "$REPOSITORY" --state open --json headRefName,body \
      --jq ".[] | select(.body | test(\"Closes #${ISSUE_NUMBER}([^0-9]|$)\")) | .headRefName" \
      | tail -n 1 \
      || true
  )"
  if [[ -n "$pr_branch" ]] && remote_has "$pr_branch"; then
    work_branch="$pr_branch"
    resumed="true"
  fi
fi

if [[ -z "$work_branch" ]] && remote_has "$preferred"; then
  work_branch="$preferred"
  resumed="true"
fi

if [[ -z "$work_branch" ]]; then
  git fetch origin "+refs/heads/${preferred}*:refs/remotes/origin/${preferred}*" || true
  legacy="$(
    git for-each-ref --sort=-committerdate --format='%(refname:short)' "refs/remotes/origin/${preferred}*" \
      | head -n 1 \
      || true
  )"
  legacy="${legacy#origin/}"
  if [[ -n "$legacy" ]]; then
    work_branch="$legacy"
    resumed="true"
  fi
fi

if [[ -z "$work_branch" ]]; then
  work_branch="$preferred"
  git checkout -B "$work_branch"
else
  git fetch origin "$work_branch"
  git checkout -B "$work_branch" "origin/$work_branch"
fi

{
  echo "work_branch=$work_branch"
  echo "resumed=$resumed"
} >> "$GITHUB_OUTPUT"
printf 'WORK_BRANCH=%s\n' "$work_branch" > "${RUNNER_TEMP}/go-branch.env"

echo "Work branch: $work_branch (resumed=$resumed)"
