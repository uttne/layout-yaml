#!/usr/bin/env python3
"""Issue @agent progress comments, prompt assembly, and the plan/go run.

Stdlib only. Shared model selection and checkpoint rendering live in agentlib.py.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import agentlib

PLAN_CHECKPOINTS = (
    "リクエスト受付",
    "Issue コンテキストの取得",
    "リポジトリのチェックアウト",
    "エージェント環境の準備（Cursor CLI）",
    "方針の整理",
    "Issue への返信投稿",
    "完了",
)
GO_CHECKPOINTS = (
    "リクエスト受付",
    "Issue コンテキストの取得",
    "リポジトリのチェックアウト",
    "作業ブランチの準備",
    "エージェント環境の準備（Cursor CLI）",
    "実装・テスト",
    "push と PR 作成",
    "完了",
)
PLAN_STAGES = {
    "received": 0,
    "issue_loaded": 1,
    "checked_out": 2,
    "cli_ready": 3,
    "agent_running": 4,
    "posting": 5,
    "completed": 6,
}
GO_STAGES = {
    "received": 0,
    "issue_loaded": 1,
    "checked_out": 2,
    "branch_ready": 3,
    "cli_ready": 4,
    "agent_running": 5,
    "publishing": 6,
    "completed": 7,
}
def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def runner_temp() -> Path:
    raw = os.environ.get("RUNNER_TEMP") or os.environ.get("TEMP") or "/tmp"
    return Path(raw)


def comment_id_path() -> Path:
    return runner_temp() / "issue-agent-progress-comment-id"


def active_index_path() -> Path:
    return runner_temp() / "issue-agent-progress-active-index"


def checkpoints(mode: str) -> tuple[str, ...]:
    if mode == "plan":
        return PLAN_CHECKPOINTS
    return GO_CHECKPOINTS


def stage_index(mode: str, stage: str) -> int:
    table = PLAN_STAGES if mode == "plan" else GO_STAGES
    return table.get(stage, 0)


def read_note(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1][:200].replace("$", "").replace("`", "")


def note_path() -> Path | None:
    raw = os.environ.get("AGENT_NOTE_PATH") or os.environ.get("GO_NOTE_PATH") or ""
    return Path(raw) if raw else None


def load_active_index() -> int:
    path = active_index_path()
    if not path.is_file():
        return 0
    raw = path.read_text(encoding="utf-8").strip()
    try:
        return int(raw)
    except ValueError:
        return 0


def save_active_index(index: int) -> None:
    active_index_path().write_text(f"{index}\n", encoding="utf-8")


def render_body(mode: str, stage: str, active_index: int, note: str) -> str:
    meta = [f"モード: `@agent {mode}`", *agentlib.progress_context_lines()]
    branch = os.environ.get("BRANCH_NAME", "")
    if branch:
        meta.append(f"ブランチ: `{branch}`")
    selected_model = agentlib.model_label()
    if selected_model:
        meta.append(f"モデル: {selected_model}")
    note_section = f"\n### いまの作業\n\n{note}\n" if note else ""
    return agentlib.progress_document(
        "@agent Issue 進捗",
        meta,
        agentlib.checkpoint_rows(checkpoints(mode), stage, active_index),
        agentlib.PROGRESS_CLOSING,
        extra=note_section,
    )


def gh_api(method: str, url: str, body: str, jq: str | None = None) -> str:
    command = [
        "gh",
        "api",
        "--method",
        method,
        "-H",
        "Accept: application/vnd.github+json",
        url,
        "-f",
        f"body={body}",
    ]
    if jq:
        command.extend(["--jq", jq])
    result = subprocess.run(command, check=False, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def update_progress(stage: str) -> None:
    mode = require_env("AGENT_MODE")
    repository = require_env("REPOSITORY")
    issue = require_env("ISSUE_NUMBER")
    require_env("GH_TOKEN")
    id_path = comment_id_path()
    if agentlib.result_already_written(id_path):
        print(f"Result already written; skip progress update (mode={mode}, stage={stage}).")
        return
    if stage == "failed":
        comment_id = agentlib.write_result(
            id_path,
            "ISSUE_NUMBER",
            agentlib.failure_comment(f"@agent {mode}"),
        )
        print(f"Issue progress replaced with failure (mode={mode}, id={comment_id}).")
        return

    if stage == "note":
        active_index = load_active_index()
    else:
        active_index = stage_index(mode, stage)
        save_active_index(active_index)

    body = render_body(mode, stage, active_index, read_note(note_path()))
    if stage == "note" and not id_path.is_file():
        print("No progress comment yet; skip note update.")
        return

    if id_path.is_file():
        comment_id = id_path.read_text(encoding="utf-8").strip()
        gh_api("PATCH", f"repos/{repository}/issues/comments/{comment_id}", body)
    else:
        comment_id = gh_api(
            "POST",
            f"repos/{repository}/issues/{issue}/comments",
            body,
            jq=".id",
        )
        id_path.write_text(f"{comment_id}\n", encoding="utf-8")
    print(f"Issue progress updated (mode={mode}, stage={stage}, id={comment_id}).")


def poll_notes(stop: threading.Event | None = None) -> None:
    interval = int(os.environ.get("NOTE_POLL_SECONDS", "30"))
    path = note_path()
    if path is None:
        return
    last = ""
    while True:
        if stop is None:
            time.sleep(interval)
        elif stop.wait(interval):
            return
        current = read_note(path)
        if not current or current == last:
            continue
        try:
            update_progress("note")
        except SystemExit as exc:
            print(f"Note update failed: {exc}", file=sys.stderr)
        last = current


def run_agent() -> None:
    mode = require_env("AGENT_MODE")
    if mode not in {"plan", "go"}:
        raise SystemExit("AGENT_MODE must be plan or go")
    if not os.environ.get("CURSOR_API_KEY"):
        raise SystemExit("CURSOR_API_KEY is not configured.")
    if shutil.which("cursor-agent") is None:
        raise SystemExit("cursor-agent was not found in PATH.")
    prompt_file = runner_temp() / "issue-agent-prompt.md"
    prompt_file.write_text(build_prompt(), encoding="utf-8")
    reply_path = Path(os.environ.get("ISSUE_REPLY_OUTPUT_PATH") or runner_temp() / "issue-agent-reply.md")
    reply_path.unlink(missing_ok=True)
    update_progress("agent_running")
    print(f"Starting @agent {mode} for issue #{require_env('ISSUE_NUMBER')}...")
    stop = threading.Event()
    thread: threading.Thread | None = None
    if mode == "go" and note_path() is not None:
        thread = threading.Thread(target=poll_notes, args=(stop,), daemon=True)
        thread.start()
    status = agentlib.run_cursor_agent(prompt_file.read_text(encoding="utf-8"), model=agentlib.selected_model_id())
    stop.set()
    if thread is not None:
        thread.join(timeout=1)
    if status != 0:
        print("cursor-agent failed.", file=sys.stderr)
        raise SystemExit(status)
    if mode != "plan":
        return
    if not reply_path.is_file() or reply_path.stat().st_size == 0:
        raise SystemExit(f"Plan reply was not written to {reply_path}.")
    update_progress("posting")
    reply = reply_path.read_text(encoding="utf-8") + agentlib.agent_footer("`@agent plan`")
    comment_id = agentlib.write_result(comment_id_path(), "ISSUE_NUMBER", reply)
    print(f"Replaced progress comment {comment_id} with the plan reply.")


def substitute(text: str) -> str:
    mapping = {
        "REPOSITORY": os.environ.get("REPOSITORY", ""),
        "ISSUE_NUMBER": os.environ.get("ISSUE_NUMBER", ""),
        "TRIGGERED_BY": os.environ.get("TRIGGERED_BY", ""),
        "ISSUE_REPLY_OUTPUT_PATH": os.environ.get("ISSUE_REPLY_OUTPUT_PATH", ""),
        "DEFAULT_BRANCH": os.environ.get("DEFAULT_BRANCH", "main"),
        "WORK_BRANCH": os.environ.get("WORK_BRANCH", ""),
        "GO_RESUMED": os.environ.get("GO_RESUMED", "false"),
        "GO_STATUS_PATH": os.environ.get("GO_STATUS_PATH", ""),
        "GO_NOTE_PATH": os.environ.get("GO_NOTE_PATH", ""),
        "GO_PR_BODY_PATH": os.environ.get("GO_PR_BODY_PATH", ""),
    }
    return agentlib.substitute(text, mapping)


def read_trigger_comment() -> str:
    path = os.environ.get("TRIGGER_COMMENT_PATH", "")
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").replace("\r", "")
    body = os.environ.get("TRIGGER_COMMENT_BODY", "")
    if body:
        return body.replace("\r", "")
    raise SystemExit("Trigger comment body is missing (set TRIGGER_COMMENT_PATH or TRIGGER_COMMENT_BODY).")


def build_prompt() -> str:
    mode = require_env("AGENT_MODE")
    template_path = Path(
        os.environ.get("PROMPT_TEMPLATE_PATH")
        or f".github/workflows/prompts/issue-agent-{mode}.md"
    )
    if not template_path.is_file():
        raise SystemExit(f"Prompt template not found: {template_path}")
    template = template_path.read_text(encoding="utf-8")
    kept = [
        line
        for line in template.splitlines(keepends=True)
        if "<!-- PROJECT_ISSUE_CONTEXT -->" not in line
    ]
    prompt = substitute("".join(kept)).rstrip() + "\n"

    context_path = Path(os.environ.get("PROJECT_CONTEXT_PATH") or ".cursor/issue-agent.md")
    if context_path.is_file():
        print(f"Including project context from {context_path}.", file=sys.stderr)
        context = substitute(context_path.read_text(encoding="utf-8")).rstrip()
        prompt += f"\n## プロジェクト固有の作業指針\n\n{context}\n"

    trigger = read_trigger_comment().rstrip("\n")
    prompt += (
        "\n## 依頼者のコメント（全文・必読）\n\n"
        "次の Markdown ブロックは、今回のワークフローを起動した Issue コメントの**全文**です。\n"
        f"`@agent {mode}` 以外の行も、制約・優先順位・スコープとして**すべて尊重**してください。\n\n"
        "```markdown\n"
        f"{trigger}\n"
        "```\n"
    )
    return prompt


def gh_out(args: list[str]) -> str:
    result = subprocess.run(["gh", *args], check=False, text=True, encoding="utf-8", errors="replace", capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def parse_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"^### (.+)$", text, re.M))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).strip()] = text[start:end].strip()
    return sections


def section_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*[-*]\s+(?:\[[ xX]\]\s+)?(.*)$", line)
        if match and match.group(1).strip():
            items.append(match.group(1).strip())
    return items


def mark_task_section(section: str, phrases: list[str]) -> str:
    if not phrases:
        return section
    cleaned = [phrase.replace("`", "").strip() for phrase in phrases if phrase.strip()]
    lines: list[str] = []
    for line in section.splitlines():
        match = re.match(r"^(\s*)([-*])\s+(?:\[[ xX]\]\s+)?(.*)$", line)
        if not match:
            lines.append(line)
            continue
        content = match.group(3).strip()
        plain = content.replace("`", "")
        already = "[x]" in line.lower() or "[X]" in line
        done = already or any(phrase in plain for phrase in cleaned)
        lines.append(f"{match.group(1)}- [{'x' if done else ' '}] {content}")
    return "\n".join(lines)


def replace_h2(body: str, heading: str, block: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\n.*?(?=^## |\Z)", re.M | re.S)
    replacement = block.rstrip() + "\n\n"
    if pattern.search(body):
        return pattern.sub(replacement, body, count=1)
    marker = "## 参照"
    if marker in body:
        return body.replace(marker, replacement + marker, 1)
    return body.rstrip() + "\n\n" + replacement


def task_section_span(body: str) -> tuple[int, int] | None:
    match = re.search(r"^## タスク\n.*?(?=^## |\Z)", body, re.M | re.S)
    if not match:
        return None
    return match.start(), match.end()


def apply_issue_body(body: str, status: str, progress_block: str) -> str:
    sections = parse_sections(status)
    phrases = section_items(sections.get("完了したタスク", ""))
    span = task_section_span(body)
    if span and phrases:
        start, end = span
        heading, _, rest = body[start:end].partition("\n")
        body = body[:start] + heading + "\n" + mark_task_section(rest, phrases).rstrip() + "\n\n" + body[end:]
    return replace_h2(body, "進捗", progress_block)


def progress_block(branch: str, pr_url: str, head: str, status: str) -> str:
    sections = parse_sections(status)
    remaining = section_items(sections.get("まだ残っていること", "")) or ["（未記録）"]
    blockers = section_items(sections.get("ブロック・エラー", "")) or ["なし"]
    if os.environ.get("OMITTED_WORKFLOWS") == "true":
        blockers.append("`.github/workflows/` の変更は Actions から push していない。workflow ファイルは手元で追加する。")
    remaining_lines = "\n".join(f"- {item}" for item in remaining)
    blocker_lines = "\n".join(f"- {item}" for item in blockers)
    pr_text = pr_url or "未作成"
    selected_model = agentlib.model_label()
    model_line = f"- モデル: {selected_model}\n" if selected_model else ""
    return (
        "## 進捗\n\n"
        f"- ブランチ: `{branch}`\n"
        f"- PR: {pr_text}\n"
        f"- HEAD: `{head}`\n"
        f"{model_line}\n"
        "### 未完了\n\n"
        f"{remaining_lines}\n\n"
        "### ブロック\n\n"
        f"{blocker_lines}\n"
    )


def record_comment(branch: str, pr_url: str, head: str, head_full: str, status: str) -> str:
    sections = parse_sections(status)
    done = sections.get("ここまでできたこと", "（未記録）")
    remaining = sections.get("まだ残っていること", "（未記録）")
    blockers = sections.get("ブロック・エラー", "なし")
    if os.environ.get("OMITTED_WORKFLOWS") == "true":
        blockers = blockers.rstrip() + "\n\n- `.github/workflows/` の変更は Actions から push していない。workflow ファイルは手元で追加する。"
    pr_text = pr_url or "未作成"
    selected_model = agentlib.model_label()
    model_row = f"| モデル | {selected_model} |\n" if selected_model else ""
    model_meta = f"model: {selected_model}\n" if selected_model else ""
    return (
        "## @agent go 実装記録\n\n"
        "| 項目 | 値 |\n"
        "| --- | --- |\n"
        f"| ブランチ | `{branch}` |\n"
        f"| HEAD | `{head}` |\n"
        f"| PR | {pr_text} |\n"
        f"{model_row}"
        "| 再開 | 次の `@agent go` は概要のチェックとこの記録、同じブランチから続ける |\n\n"
        "### ここまでできたこと\n\n"
        f"{done}\n\n"
        "### まだ残っていること\n\n"
        f"{remaining}\n\n"
        "### ブロック・エラー\n\n"
        f"{blockers}\n\n"
        "<!-- layout-yaml-agent-go\n"
        f"branch: {branch}\n"
        f"head_sha: {head_full}\n"
        f"pr_url: {pr_url}\n"
        f"{model_meta}"
        "-->\n"
    )


def japanese_pr_body(issue: str, status: str) -> str:
    path = os.environ.get("GO_PR_BODY_PATH", "")
    if path and Path(path).is_file() and Path(path).stat().st_size > 0:
        return Path(path).read_text(encoding="utf-8")
    sections = parse_sections(status)
    done = section_items(sections.get("ここまでできたこと", ""))
    if not done:
        done = ["（実装記録を参照）"]
    lines = "\n".join(f"- {item}" for item in done)
    return f"## 概要\n\n{lines}\n\n## 確認\n\n- Issue #{issue} の合格基準\n\nCloses #{issue}\n"


def sync_record() -> None:
    repository = require_env("REPOSITORY")
    issue = require_env("ISSUE_NUMBER")
    branch = require_env("WORK_BRANCH")
    status_path = Path(os.environ.get("GO_STATUS_PATH") or runner_temp() / "go-status.md")
    status = status_path.read_text(encoding="utf-8") if status_path.is_file() else ""
    head_full = os.environ.get("HEAD_SHA", "")
    head = head_full[:7] if head_full else ""
    pr_url = os.environ.get("PR_URL", "")
    body = gh_out(["issue", "view", issue, "--repo", repository, "--json", "body", "--jq", ".body"])
    updated = apply_issue_body(body, status, progress_block(branch, pr_url, head, status))
    body_path = runner_temp() / "issue-body.md"
    body_path.write_text(updated, encoding="utf-8")
    gh_out(["issue", "edit", issue, "--repo", repository, "--body-file", str(body_path)])
    comment = record_comment(branch, pr_url, head, head_full, status)
    comment_id = agentlib.write_result(comment_id_path(), "ISSUE_NUMBER", comment)
    print(f"Replaced progress comment {comment_id} with the go record.")
    ids = gh_out(
        [
            "api",
            "--paginate",
            f"repos/{repository}/issues/{issue}/comments",
            "--jq",
            '.[] | select(.body | contains("layout-yaml-agent-go")) | .id',
        ]
    ).split()
    for other in ids:
        if other == comment_id:
            continue
        agentlib.gh(
            [
                "api",
                "--method",
                "DELETE",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{repository}/issues/comments/{other}",
            ]
        )
        print(f"Removed previous go record {other}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    progress = sub.add_parser("progress", help="create or update the checkpoint comment")
    progress.add_argument("stage")
    sub.add_parser("poll", help="watch the note file and refresh the checkpoint comment")
    sub.add_parser("prompt", help="write the agent prompt to stdout")
    sub.add_parser("sync-record", help="update the Issue body and the progress comment")
    sub.add_parser("pr-body", help="write a Japanese pull request body to stdout")
    sub.add_parser("run", help="run the plan or go agent and post a plan reply")
    args = parser.parse_args()
    if args.command == "progress":
        update_progress(args.stage)
    elif args.command == "poll":
        poll_notes()
    elif args.command == "run":
        run_agent()
    elif args.command == "prompt":
        sys.stdout.write(build_prompt())
    elif args.command == "sync-record":
        sync_record()
    elif args.command == "pr-body":
        issue = require_env("ISSUE_NUMBER")
        status_path = Path(os.environ.get("GO_STATUS_PATH") or "")
        status = status_path.read_text(encoding="utf-8") if status_path.is_file() else ""
        sys.stdout.write(japanese_pr_body(issue, status))


if __name__ == "__main__":
    main()
