#!/usr/bin/env python3
"""Run an @agent pull request review and post it as a GitHub review."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agentlib

PRIORITY_LABELS = {
    "must": "要修正",
    "optional": "任意",
    "question": "疑問",
}
_PRIORITY_ALIASES = {
    "must": "must",
    "required": "must",
    "要修正": "must",
    "optional": "optional",
    "任意": "optional",
    "question": "question",
    "疑問": "question",
}
_MAX_COMMENTS = 15


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


def parse_review_output(text: str) -> tuple[str, list[dict], list[dict]]:
    """Return the summary, inline comments, and comments kept only in the body."""
    try:
        data = _load_json_object(text)
    except json.JSONDecodeError as exc:
        print(f"Review output is not JSON ({exc}). Posting it as the review body.")
        return text.strip() + "\n", [], []
    if not isinstance(data, dict):
        print("Review JSON was not an object. Posting the raw output.")
        return text.strip() + "\n", [], []
    summary = data.get("summary")
    comments, overflow = normalize_comments(data.get("comments"))
    if not isinstance(summary, str) or not summary.strip():
        summary = summary_from_comments(comments + overflow)
    return summary.strip() + "\n", comments, overflow


def _load_json_object(text: str) -> object:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return json.loads(stripped)


def normalize_comments(value: object) -> tuple[list[dict], list[dict]]:
    if not isinstance(value, list):
        if value not in (None, []):
            print("Ignoring review comments because they were not a list.")
        return [], []
    comments: list[dict] = []
    overflow: list[dict] = []
    for index, item in enumerate(value, start=1):
        comment = _normalize_comment(index, item)
        if comment is None:
            continue
        if len(comments) >= _MAX_COMMENTS:
            overflow.append(comment)
            continue
        comments.append(comment)
    if overflow:
        print(f"Keeping the first {_MAX_COMMENTS} comments on the diff.")
    return comments, overflow


def _normalize_comment(index: int, item: object) -> dict | None:
    if not isinstance(item, dict):
        print(f"Skipping comment {index}: not an object.")
        return None
    priority = _PRIORITY_ALIASES.get(str(item.get("priority", "")).strip())
    path = _clean_path(item.get("path"))
    line = _clean_line(item.get("line"))
    side = str(item.get("side") or "RIGHT").strip().upper()
    body = item.get("body")
    if priority is None or path is None or line is None or side not in {"RIGHT", "LEFT"}:
        print(f"Skipping comment {index}: priority, path, line, or side is unusable.")
        return None
    if not isinstance(body, str) or not body.strip():
        print(f"Skipping comment {index}: body is empty.")
        return None
    comment = {
        "priority": priority,
        "path": path,
        "side": side,
        "line": line,
        "body": body.strip(),
    }
    start_line = _clean_line(item.get("start_line")) if item.get("start_line") not in (None, "") else None
    if start_line is not None and start_line < line:
        comment["start_line"] = start_line
    elif start_line is not None:
        print(f"Comment {index}: ignoring start_line because it is not above line.")
    return comment


def _clean_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/") or ":" in raw:
        return None
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return "/".join(parts)


def _clean_line(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 1:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        if number >= 1:
            return number
    return None


def summary_from_comments(comments: list[dict]) -> str:
    lines = ["## エージェントレビュー", "", "**概要:** 差分上のコメントに指摘を付けた。", ""]
    for priority in ("must", "optional", "question"):
        group = [comment for comment in comments if comment["priority"] == priority]
        if not group:
            continue
        lines.append(f"### {PRIORITY_LABELS[priority]}")
        lines.append("")
        for comment in group:
            lines.append(f"- `{comment['path']}:{comment['line']}`")
        lines.append("")
    if len(lines) == 4:
        lines = ["## エージェントレビュー", "", "**概要:** 指摘はない。", ""]
    return "\n".join(lines).rstrip() + "\n"


def inline_body(comment: dict) -> str:
    label = PRIORITY_LABELS[comment["priority"]]
    return f"**{label}**\n\n{comment['body']}"


def unplaced_section(comments: list[dict]) -> str:
    lines = [
        "### 差分に付けられなかった指摘",
        "",
        "変更行以外には GitHub のレビューコメントを付けられないため、ここに残している。",
        "",
    ]
    for comment in comments:
        label = PRIORITY_LABELS[comment["priority"]]
        lines.append(f"- **{label}** `{comment['path']}:{comment['line']}`（{comment['side']}）")
        lines.append("")
        lines.append(comment["body"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
    summary, comments, overflow = parse_review_output(output_path.read_text(encoding="utf-8"))
    if not summary.strip() and not comments and not overflow:
        raise SystemExit(f"Review output at {output_path} had no summary or comments.")
    agentlib.update_workflow_progress("pr", "posting")
    head_sha = agentlib.require_env("PR_HEAD_SHA")
    post_pull_request_review(repository, number, head_sha, summary, comments, overflow)


def post_pull_request_review(
    repository: str,
    number: str,
    head_sha: str,
    summary: str,
    comments: list[dict],
    overflow: list[dict],
) -> None:
    body = _review_body(summary, overflow)
    review = gh_api(
        "POST",
        f"repos/{repository}/pulls/{number}/reviews",
        {"commit_id": head_sha, "body": body},
    )
    if review is None or not isinstance(review.get("id"), int):
        print("Could not open a pull request review. Replacing the progress comment.", file=sys.stderr)
        post_conversation_fallback(summary, comments + overflow)
        return
    missed = list(overflow)
    for comment in comments:
        if not add_review_comment(repository, number, review["id"], head_sha, comment):
            missed.append(comment)
    if missed != overflow:
        body = _review_body(summary, missed)
    submitted = gh_api(
        "POST",
        f"repos/{repository}/pulls/{number}/reviews/{review['id']}/events",
        {"event": "COMMENT", "body": body},
    )
    if submitted is None:
        print("Could not submit the pull request review. Replacing the progress comment.", file=sys.stderr)
        delete_pending_review(repository, number, review["id"])
        post_conversation_fallback(summary, comments + overflow)
        return
    print(f"Posted pull request review with {len(comments) - (len(missed) - len(overflow))} inline comments.")
    replace_progress_comment(body)


def _review_body(summary: str, unplaced: list[dict]) -> str:
    body = summary.rstrip()
    if unplaced:
        body += "\n\n" + unplaced_section(unplaced).rstrip()
    return body + agentlib.agent_footer("review")


def add_review_comment(
    repository: str,
    number: str,
    review_id: int,
    head_sha: str,
    comment: dict,
) -> bool:
    payload = {
        "body": inline_body(comment),
        "commit_id": head_sha,
        "path": comment["path"],
        "line": comment["line"],
        "side": comment["side"],
        "subject_type": "line",
    }
    if "start_line" in comment:
        payload["start_line"] = comment["start_line"]
        payload["start_side"] = comment["side"]
    endpoint = f"repos/{repository}/pulls/{number}/reviews/{review_id}/comments"
    if gh_api("POST", endpoint, payload) is not None:
        return True
    if "start_line" not in payload:
        return False
    payload.pop("start_line")
    payload.pop("start_side")
    print(f"Retrying {comment['path']}:{comment['line']} as a single line.")
    return gh_api("POST", endpoint, payload) is not None


def delete_pending_review(repository: str, number: str, review_id: int) -> None:
    agentlib.gh(
        ["api", "--method", "DELETE", f"repos/{repository}/pulls/{number}/reviews/{review_id}"],
        check=False,
        capture=True,
    )


def replace_progress_comment(body: str) -> None:
    comment_id = agentlib.write_result(
        agentlib.runner_temp() / "pr-review-progress-comment-id",
        "PR_NUMBER",
        body,
    )
    print(f"Replaced progress comment {comment_id} with the review result.")


def post_conversation_fallback(summary: str, comments: list[dict]) -> None:
    text = summary.rstrip()
    if comments:
        text += "\n\n" + unplaced_section(comments).rstrip()
    text += agentlib.agent_footer("review")
    replace_progress_comment(text)


def gh_api(method: str, endpoint: str, payload: dict) -> dict | None:
    path = agentlib.runner_temp() / "gh-api-payload.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result = agentlib.gh(
        ["api", "--method", method, endpoint, "--input", str(path)],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        print(f"gh api {method} {endpoint} failed: {detail}", file=sys.stderr)
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"gh api {method} {endpoint} returned non-JSON.", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"gh api {method} {endpoint} returned unexpected JSON.", file=sys.stderr)
        return None
    return data


if __name__ == "__main__":
    main()
