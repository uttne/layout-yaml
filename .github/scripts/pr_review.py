#!/usr/bin/env python3
"""Run an @agent pull request review and post the result."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agentlib


def build_prompt() -> str:
    template_path = Path(os.environ.get("PROMPT_TEMPLATE_PATH") or ".github/workflows/prompts/pr-review-agent.md")
    if not template_path.is_file():
        raise SystemExit(f"Prompt template not found: {template_path}")
    output_path = os.environ.get("REVIEW_OUTPUT_PATH") or str(agentlib.runner_temp() / "pr-review.md")
    mapping = {
        "REPOSITORY": os.environ.get("REPOSITORY", ""),
        "PR_NUMBER": os.environ.get("PR_NUMBER", ""),
        "PR_HEAD_SHA": os.environ.get("PR_HEAD_SHA", ""),
        "PR_BASE_SHA": os.environ.get("PR_BASE_SHA", ""),
        "TRIGGERED_BY": os.environ.get("TRIGGERED_BY", ""),
        "REVIEW_OUTPUT_PATH": output_path,
    }
    template = template_path.read_text(encoding="utf-8")
    kept = [line for line in agentlib.substitute(template, mapping).splitlines(keepends=True) if "<!-- PROJECT_REVIEW_CONTEXT -->" not in line]
    prompt = "".join(kept).rstrip() + "\n"
    context_path = Path(os.environ.get("PROJECT_REVIEW_CONTEXT_PATH") or ".cursor/pr-review.md")
    if context_path.is_file():
        print(f"Including project review context from {context_path}.")
        context = agentlib.substitute(context_path.read_text(encoding="utf-8"), mapping).rstrip()
        prompt += f"\n## プロジェクト固有のレビュー指針\n\n{context}\n"
    else:
        print(f"No project review context at {context_path} (skipping).")
    return prompt


def main() -> None:
    if not os.environ.get("CURSOR_API_KEY"):
        raise SystemExit("CURSOR_API_KEY is not configured.")
    if shutil.which("cursor-agent") is None:
        raise SystemExit("cursor-agent was not found in PATH.")
    repository = agentlib.require_env("REPOSITORY")
    number = agentlib.require_env("PR_NUMBER")
    output_path = Path(os.environ.get("REVIEW_OUTPUT_PATH") or agentlib.runner_temp() / "pr-review.md")
    prompt = build_prompt()
    agentlib.update_workflow_progress("pr", "agent_running")
    print(f"Starting agent review for PR #{number}...")
    output_path.unlink(missing_ok=True)
    status = agentlib.run_cursor_agent(prompt, model=agentlib.selected_model_id())
    if status != 0:
        print("cursor-agent failed.", file=sys.stderr)
        raise SystemExit(status)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise SystemExit(f"Review output was not written to {output_path}.")
    agentlib.update_workflow_progress("pr", "posting")
    posted = output_path.with_name(output_path.name + ".posted")
    posted.write_text(output_path.read_text(encoding="utf-8") + agentlib.agent_footer("review"), encoding="utf-8")
    agentlib.gh(["pr", "comment", number, "--repo", repository, "--body-file", str(posted)])
    print("Posted PR conversation comment.")


if __name__ == "__main__":
    main()
