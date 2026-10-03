#!/usr/bin/env python3
"""Publish pytest JUnit results to the job summary and the pull request."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

MARKER = "<!-- layout-yaml-ci-pytest -->"
MAX_DETAIL_CHARS = 1500
MAX_BODY_CHARS = 60000

_OUTCOME_RANK = {"failed": 0, "error": 1, "skipped": 2, "passed": 3}
_OUTCOME_LABEL = {
    "failed": "失敗",
    "error": "エラー",
    "skipped": "スキップ",
    "passed": "成功",
}


@dataclass(frozen=True)
class Case:
    file: str
    name: str
    outcome: str
    detail: str


def parse_junit(path: Path) -> list[Case]:
    root = ET.parse(path).getroot()
    cases: list[Case] = []
    for node in root.iter("testcase"):
        file_name, test_name = _test_name(node)
        outcome, detail = _outcome(node)
        cases.append(Case(file=file_name, name=test_name, outcome=outcome, detail=detail))
    cases.sort(key=lambda case: (_OUTCOME_RANK.get(case.outcome, 9), case.file, case.name))
    return cases


def _test_name(node: ET.Element) -> tuple[str, str]:
    """Return the file and the test name from a JUnit testcase.

    pytest stores the function (and parameters) in ``name``. Classes sit in
    ``classname`` after the module path, so ``tests.test_lexer.TestBlock`` and
    ``tests/test_lexer.py`` become ``TestBlock::test_lines``.
    """
    file_name = node.attrib.get("file", "").replace("\\", "/").strip()
    classname = node.attrib.get("classname", "").strip()
    name = node.attrib.get("name", "").strip() or "(unknown)"
    if not file_name:
        return classname or "(unknown)", name
    module = file_name[:-3] if file_name.endswith(".py") else file_name
    module = module.replace("/", ".")
    prefix = module + "."
    if classname.startswith(prefix):
        qual = classname[len(prefix) :]
        name = "::".join((*qual.split("."), name))
    return file_name, name


def _outcome(node: ET.Element) -> tuple[str, str]:
    for kind in ("failure", "error", "skipped"):
        child = node.find(kind)
        if child is None:
            continue
        message = (child.attrib.get("message") or "").strip()
        body = (child.text or "").strip()
        detail = message if message else body
        if message and body and body not in message:
            detail = f"{message}\n{body}"
        return ("failed" if kind == "failure" else kind, detail[:MAX_DETAIL_CHARS])
    return "passed", ""


def render(cases: list[Case], *, truncate: bool = True) -> str:
    text = _compose(cases)
    if not truncate or len(text) <= MAX_BODY_CHARS:
        return text
    without_passed = [case for case in cases if case.outcome != "passed"]
    text = _compose(
        without_passed,
        notice="結果が多いため、成功の一覧は掲載していません。",
        counted=cases,
    )
    if len(text) <= MAX_BODY_CHARS:
        return text
    without_details = [Case(case.file, case.name, case.outcome, "") for case in without_passed]
    text = _compose(
        without_details,
        notice="結果が多いため、成功の一覧と各テストのメッセージは掲載していません。",
        counted=cases,
    )
    if len(text) <= MAX_BODY_CHARS:
        return text
    failures = [case for case in without_details if case.outcome in {"failed", "error"}]
    text = _compose(
        failures,
        notice="結果が多いため、失敗とエラーのテスト名だけを掲載しています。",
        counted=cases,
    )
    if len(text) <= MAX_BODY_CHARS:
        return text
    return _compose(
        [],
        notice="結果が多いため、テスト一覧は掲載していません。",
        counted=cases,
    )


def _compose(
    shown: list[Case],
    *,
    notice: str = "",
    counted: list[Case] | None = None,
) -> str:
    source = shown if counted is None else counted
    counts = {label: 0 for label in _OUTCOME_LABEL}
    for case in source:
        counts[case.outcome] = counts.get(case.outcome, 0) + 1
    lines = [
        MARKER,
        "## pytest",
        "",
        (
            f"{counts.get('passed', 0)} 成功、"
            f"{counts.get('failed', 0)} 失敗、"
            f"{counts.get('error', 0)} エラー、"
            f"{counts.get('skipped', 0)} スキップ"
        ),
        "",
    ]
    if notice:
        lines.append(notice)
        lines.append("")
    run_url = _run_url()
    if run_url:
        lines.append(f"[ログ]({run_url})")
        lines.append("")
    if not shown:
        if counted is None:
            lines.append("テストは 0 件でした。")
        return "\n".join(lines).rstrip() + "\n"

    for outcome in ("failed", "error", "skipped", "passed"):
        group = [case for case in shown if case.outcome == outcome]
        if not group:
            continue
        label = _OUTCOME_LABEL.get(outcome, outcome)
        open_attr = " open" if outcome in {"failed", "error"} else ""
        lines.append(f"<details{open_attr}>")
        lines.append(f"<summary>{label} {len(group)}</summary>")
        lines.append("")
        lines.extend(_render_files(group))
        lines.append("")
        lines.append("</details>")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_files(cases: list[Case]) -> list[str]:
    grouped: dict[str, list[Case]] = {}
    order: list[str] = []
    for case in cases:
        bucket = grouped.setdefault(case.file, [])
        if not bucket:
            order.append(case.file)
        bucket.append(case)
    lines = ["<ul>"]
    for file_name in order:
        lines.append(f"<li><code>{_html_text(file_name)}</code>")
        lines.append("<ul>")
        for case in grouped[file_name]:
            lines.append(f"<li><code>{_html_text(case.name)}</code>")
            if case.detail:
                lines.append("<pre>")
                lines.append(_pre_text(case.detail))
                lines.append("</pre>")
            lines.append("</li>")
        lines.append("</ul>")
        lines.append("</li>")
    lines.append("</ul>")
    return lines


def _pre_text(detail: str) -> str:
    """Escape a traceback for ``<pre>`` without emitting a blank source line.

    The surrounding list is one HTML block, and that block ends at a blank
    line. A whitespace-only line counts as blank, so those lines become a
    non-breaking space and still look empty inside the traceback.
    """
    normalized = detail.replace("\r\n", "\n").replace("\r", "\n")
    kept: list[str] = []
    for line in _html_text(normalized).split("\n"):
        kept.append(line if line.strip(" \t") else "\u00a0")
    return "\n".join(kept)


def _html_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def write_summary(body: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not path:
        print(body)
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(body)
        if not body.endswith("\n"):
            handle.write("\n")


def upsert_comment(pr: str, body: str) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("GITHUB_REPOSITORY is unset; skipped the pull request comment.", file=sys.stderr)
        return
    comment_id = _find_comment(repo, pr)
    if comment_id is None:
        _gh_api("POST", f"repos/{repo}/issues/{pr}/comments", {"body": body})
        print(f"Posted pytest results to PR #{pr}.")
        return
    _gh_api("PATCH", f"repos/{repo}/issues/comments/{comment_id}", {"body": body})
    print(f"Updated pytest results comment on PR #{pr}.")


def _find_comment(repo: str, pr: str) -> int | None:
    result = _gh(
        ["api", "--paginate", "--slurp", f"repos/{repo}/issues/{pr}/comments"],
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"Could not list pull request comments: {detail}")
    try:
        pages = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Pull request comments were not JSON: {exc}") from exc
    comments: list[dict] = []
    if isinstance(pages, list) and pages and isinstance(pages[0], list):
        for page in pages:
            comments.extend(item for item in page if isinstance(item, dict))
    elif isinstance(pages, list):
        comments.extend(item for item in pages if isinstance(item, dict))
    for comment in comments:
        body = comment.get("body") or ""
        if MARKER in body:
            comment_id = comment.get("id")
            if isinstance(comment_id, int):
                return comment_id
    return None


def _gh_api(method: str, endpoint: str, payload: dict) -> None:
    path = Path(os.environ.get("RUNNER_TEMP") or os.environ.get("TEMP") or ".") / "pytest-report-payload.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    result = _gh(["api", "--method", method, endpoint, "--input", str(path)])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"gh api {method} {endpoint} failed: {detail}")


def _gh(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"gh {' '.join(args)} failed: {detail}")
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: pytest_report.py RESULTS.xml", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"JUnit file not found: {path}", file=sys.stderr)
        return 2
    cases = parse_junit(path)
    body = render(cases)
    write_summary(body)
    pr = os.environ.get("PR_NUMBER", "").strip()
    if not pr:
        print("PR_NUMBER is unset; skipped the pull request comment.")
        return 0
    try:
        upsert_comment(pr, body)
    except SystemExit as exc:
        detail = exc.code if isinstance(exc.code, str) else "pull request comment failed"
        print(detail, file=sys.stderr)
        print(
            "Pull request comment was not updated. The pytest result still stands.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
