#!/usr/bin/env bash
# Update the single @agent checkpoint comment.
# Usage: issue-agent-progress.sh <stage>
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
exec python3 "$here/issue_agent.py" progress "$@"
