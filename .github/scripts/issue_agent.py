#!/usr/bin/env python3
"""Issue @agent progress comments, note polling, and prompt assembly.

Stdlib only. GitHub Actions invokes this via the thin bash wrappers.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

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


def run_url() -> str:
    explicit = os.environ.get("RUN_URL", "")
    if explicit:
        return explicit
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "unknown")
    return f"{server}/{repo}/actions/runs/{run_id}"


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
    rows: list[str] = []
    for index, label in enumerate(checkpoints(mode)):
        if stage == "failed" and index == active_index:
            icon = "❌"
        elif stage == "completed" or index < active_index:
            icon = "✅"
        elif index == active_index and stage != "completed":
            icon = "🔄"
        else:
            icon = "⏳"
        rows.append(f"| {label} | {icon} |")

    meta = [f"モード: `@agent {mode}`"]
    triggered_by = os.environ.get("TRIGGERED_BY", "")
    if triggered_by:
        meta.append(f"依頼: @{triggered_by}")
    branch = os.environ.get("BRANCH_NAME", "")
    if branch:
        meta.append(f"ブランチ: `{branch}`")

    note_section = f"\n### いまの作業\n\n{note}\n" if note else ""
    table = "\n".join(rows)
    meta_block = "\n".join(meta)
    return (
        "## @agent Issue 進捗\n\n"
        f"{meta_block}\n\n"
        "| チェックポイント | 状態 |\n"
        "| --- | --- |\n"
        f"{table}\n"
        f"{note_section}"
        f"[ワークフロー実行]({run_url()})\n\n"
        "_このコメントはチェックポイントごとに自動更新されます。_\n"
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
    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def update_progress(stage: str) -> None:
    mode = require_env("AGENT_MODE")
    repository = require_env("REPOSITORY")
    issue = require_env("ISSUE_NUMBER")
    require_env("GH_TOKEN")

    if stage in {"failed", "note"}:
        active_index = load_active_index()
    else:
        active_index = stage_index(mode, stage)
        save_active_index(active_index)

    body = render_body(mode, stage, active_index, read_note(note_path()))
    id_path = comment_id_path()
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


def poll_notes() -> None:
    interval = int(os.environ.get("NOTE_POLL_SECONDS", "30"))
    path = note_path()
    if path is None:
        return
    last = ""
    while True:
        time.sleep(interval)
        current = read_note(path)
        if not current or current == last:
            continue
        try:
            update_progress("note")
        except SystemExit as exc:
            print(f"Note update failed: {exc}", file=sys.stderr)
        last = current


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
    }
    keys = sorted(mapping, key=len, reverse=True)
    parts: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "$":
            for key in keys:
                token = f"${key}"
                if text.startswith(token, index):
                    parts.append(mapping[key])
                    index += len(token)
                    break
            else:
                parts.append(text[index])
                index += 1
        else:
            parts.append(text[index])
            index += 1
    return "".join(parts)


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    progress = sub.add_parser("progress", help="create or update the checkpoint comment")
    progress.add_argument("stage")
    sub.add_parser("poll", help="watch the note file and refresh the checkpoint comment")
    sub.add_parser("prompt", help="write the agent prompt to stdout")
    args = parser.parse_args()
    if args.command == "progress":
        update_progress(args.stage)
    elif args.command == "poll":
        poll_notes()
    elif args.command == "prompt":
        sys.stdout.write(build_prompt())


if __name__ == "__main__":
    main()
