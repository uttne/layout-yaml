#!/usr/bin/env python3
"""Reflect an Issue discussion into the Issue description (@agent sync)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agentlib


def read_trigger_comment() -> str:
    path = os.environ.get("TRIGGER_COMMENT_PATH", "")
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").replace("\r", "")
    body = os.environ.get("TRIGGER_COMMENT_BODY", "")
    if body:
        return body.replace("\r", "")
    raise SystemExit("Trigger comment body is missing.")


def build_prompt() -> str:
    template_path = Path(os.environ.get("PROMPT_TEMPLATE_PATH") or ".github/workflows/prompts/issue-agent-sync.md")
    if not template_path.is_file():
        raise SystemExit(f"Prompt template not found: {template_path}")
    body_path = os.environ.get("ISSUE_BODY_OUTPUT_PATH") or str(agentlib.runner_temp() / "issue-body.md")
    record_path = os.environ.get("SYNC_RECORD_OUTPUT_PATH") or str(agentlib.runner_temp() / "issue-sync-record.md")
    mapping = {
        "REPOSITORY": os.environ.get("REPOSITORY", ""),
        "ISSUE_NUMBER": os.environ.get("ISSUE_NUMBER", ""),
        "TRIGGERED_BY": os.environ.get("TRIGGERED_BY", ""),
        "TRIGGER_COMMENT_ID": os.environ.get("TRIGGER_COMMENT_ID", ""),
        "GITHUB_RUN_ID": os.environ.get("GITHUB_RUN_ID", ""),
        "ISSUE_BODY_OUTPUT_PATH": body_path,
        "SYNC_RECORD_OUTPUT_PATH": record_path,
    }
    template = template_path.read_text(encoding="utf-8")
    kept = [
        line
        for line in agentlib.substitute(template, mapping).splitlines(keepends=True)
        if "<!-- PROJECT_ISSUE_CONTEXT -->" not in line
    ]
    prompt = "".join(kept).rstrip() + "\n"
    context_path = Path(os.environ.get("PROJECT_CONTEXT_PATH") or ".cursor/issue-agent.md")
    if context_path.is_file():
        context = agentlib.substitute(context_path.read_text(encoding="utf-8"), mapping).rstrip()
        prompt += f"\n## プロジェクト固有の作業指針\n\n{context}\n"
    trigger = read_trigger_comment().rstrip("\n")
    prompt += "\n## 依頼者のコメント（全文・必読）\n\n```markdown\n" + trigger + "\n```\n"
    return prompt


def main() -> None:
    if not os.environ.get("CURSOR_API_KEY"):
        raise SystemExit("CURSOR_API_KEY is not configured.")
    if shutil.which("cursor-agent") is None:
        raise SystemExit("cursor-agent was not found in PATH.")
    repository = agentlib.require_env("REPOSITORY")
    number = agentlib.require_env("ISSUE_NUMBER")
    agentlib.require_env("TRIGGER_COMMENT_ID")
    body_path = Path(os.environ.get("ISSUE_BODY_OUTPUT_PATH") or agentlib.runner_temp() / "issue-body.md")
    record_path = Path(os.environ.get("SYNC_RECORD_OUTPUT_PATH") or agentlib.runner_temp() / "issue-sync-record.md")
    prompt = build_prompt()
    agentlib.update_workflow_progress("sync", "agent_running")
    print(f"Starting @agent sync for issue #{number}...")
    body_path.unlink(missing_ok=True)
    record_path.unlink(missing_ok=True)
    status = agentlib.run_cursor_agent(prompt, model=agentlib.selected_model_id())
    if status != 0:
        print("cursor-agent failed.", file=sys.stderr)
        raise SystemExit(status)
    if not body_path.is_file() or body_path.stat().st_size == 0:
        raise SystemExit(f"Issue body was not written to {body_path}.")
    if not record_path.is_file() or record_path.stat().st_size == 0:
        raise SystemExit(f"Sync record was not written to {record_path}.")
    agentlib.update_workflow_progress("sync", "updating_body")
    agentlib.gh(["issue", "edit", number, "--repo", repository, "--body-file", str(body_path)])
    print(f"Updated issue #{number} body.")
    agentlib.update_workflow_progress("sync", "posting_record")
    record = record_path.read_text(encoding="utf-8") + agentlib.agent_footer("`@agent sync`")
    comment_id = agentlib.write_result(
        agentlib.runner_temp() / "issue-sync-progress-comment-id",
        "ISSUE_NUMBER",
        record,
    )
    print(f"Replaced progress comment {comment_id} with the sync record.")


if __name__ == "__main__":
    main()
