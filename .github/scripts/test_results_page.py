#!/usr/bin/env python3
"""Build a GitHub Pages site from JUnit XML.

One CI run is one result. Every XML file found under the incoming directory
is part of that run. The previous site is a fetched Pages artifact (or the
published site, when that artifact has expired). This script keeps every
historical XML, rewrites summary.json, and copies the static app.

    python3 .github/scripts/test_results_page.py fetch-previous --dest previous
    python3 .github/scripts/test_results_page.py build \
        --incoming incoming --previous previous --out _site
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

GENERATOR = "layout-yaml-test-results"
SCHEMA_VERSION = 1
APP_FILES = ("index.html", "app.js", "style.css")
INDEX_NAME = "xml-index.json"
XML_CHUNK_SIZE = 50
_ZIP_PATH = re.compile(r"^xml/\d{5}\.zip$")
_RANK = {"failed": 0, "inconclusive": 1, "skipped": 2, "passed": 3}
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_TOOL_PREFIX = re.compile(r"^([A-Za-z][A-Za-z0-9_.]*)-\d{8}T\d{6}Z-")


class ReportError(Exception):
    """The site must not be published."""


class GhNotFound(ReportError):
    """GitHub API returned 404."""


@dataclass(frozen=True)
class ParsedCase:
    id: str
    name: str
    classname: str
    result: str
    duration_seconds: float


@dataclass(frozen=True)
class ParsedReport:
    fmt: str
    cases: list[ParsedCase]


@dataclass
class Totals:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    inconclusive: int = 0
    duration_seconds: float = 0.0

    def add_case(self, case: ParsedCase) -> None:
        self.total += 1
        self.duration_seconds += case.duration_seconds
        if case.result == "passed":
            self.passed += 1
        elif case.result == "failed":
            self.failed += 1
        elif case.result == "skipped":
            self.skipped += 1
        else:
            self.inconclusive += 1

    def add_record(self, record: dict) -> None:
        self.total += int(record["total"])
        self.passed += int(record["passed"])
        self.failed += int(record["failed"])
        self.skipped += int(record["skipped"])
        self.inconclusive += int(record["inconclusive"])
        self.duration_seconds += float(record["duration_seconds"])

    def as_dict(self) -> dict:
        decisive = self.passed + self.failed + self.inconclusive
        rate = None if decisive == 0 else round(self.passed / decisive, 4)
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "inconclusive": self.inconclusive,
            "duration_seconds": round(self.duration_seconds, 6),
            "success_rate": rate,
            "result": overall_result(self),
        }


@dataclass(frozen=True)
class StoredXml:
    file_id: str
    run_id: str
    created_at: str
    name: str
    data: bytes


@dataclass(frozen=True)
class RunMeta:
    run_id: str
    run_attempt: str
    run_number: int | None
    sha: str
    ref: str
    event: str
    actor: str
    url: str
    created_at: str
    repository: str

    @property
    def id(self) -> str:
        return safe_token(f"{self.run_id}-{self.run_attempt}")


def overall_result(totals: Totals) -> str:
    if totals.failed:
        return "failed"
    if totals.inconclusive:
        return "inconclusive"
    if totals.passed:
        return "passed"
    if totals.skipped:
        return "skipped"
    return "inconclusive"


def default_app_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "pages" / "test-results"


def build_site(
    *,
    incoming: Path,
    previous: Path,
    out: Path,
    pattern: str,
    app_dir: Path,
    meta: RunMeta,
    chunk_size: int = XML_CHUNK_SIZE,
) -> bool:
    """Write the site. Return False when this run produced no XML."""

    _distinct_dirs(incoming, previous, out)
    found = find_reports(incoming, pattern)
    if not found:
        print("No incoming test XML. The site was not changed.")
        return False
    if chunk_size < 1:
        raise ReportError("chunk_size must be at least 1.")
    history, entries = load_previous(previous)
    created_at = normalize_time(meta.created_at)
    run_key = meta.id
    new_files = [
        (path, safe_filename(path.name), tool_name(path.relative_to(incoming).as_posix()), parse_report(path))
        for path in found
    ]
    new_files = _unique_names(new_files)
    kept = [run for run in history if run["id"] != run_key]
    old_files: list[tuple[dict, list[tuple[dict, ParsedReport, bytes]]]] = []
    for run in kept:
        parsed_files = []
        for item in run["files"]:
            data = entries.get(str(item.get("id", "")))
            if data is None:
                raise ReportError(f"Historical result is missing: {item.get('id')}")
            parsed_files.append((item, parse_bytes(data, str(item.get("name", ""))), data))
        old_files.append((run, parsed_files))

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    try:
        _write_site(
            out,
            app_dir,
            meta,
            created_at,
            run_key,
            new_files,
            old_files,
            chunk_size,
        )
    except Exception:
        shutil.rmtree(out, ignore_errors=True)
        raise
    print(f"Wrote {out} (run {run_key}, incoming files {len(new_files)}).")
    return True


def find_reports(root: Path, pattern: str) -> list[Path]:
    if not root.is_dir():
        raise ReportError(f"Incoming directory not found: {root}")
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ReportError(f"Invalid pattern: {pattern}") from exc
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if regex.search(relative):
            found.append(path)
    return sorted(found, key=lambda item: item.relative_to(root).as_posix())


def load_previous(previous: Path) -> tuple[list[dict], dict[str, bytes]]:
    if not previous.exists():
        return [], {}
    summary_path = previous / "summary.json"
    if not summary_path.is_file():
        extras = [path for path in previous.rglob("*") if path.is_file()]
        if extras:
            raise ReportError(f"{previous} has files but no summary.json.")
        return [], {}
    summary = _read_json(summary_path, "summary.json")
    if summary.get("generator") != GENERATOR or summary.get("schema_version") != SCHEMA_VERSION:
        raise ReportError("Previous summary.json is not a test results site.")
    runs = summary.get("runs")
    if not isinstance(runs, list):
        raise ReportError("summary.json has no runs array.")
    index = _read_index(previous)
    listed = index["files"]
    opened: dict[Path, dict[str, bytes]] = {}
    entries: dict[str, bytes] = {}
    for run in runs:
        files = run.get("files")
        if not isinstance(files, list):
            raise ReportError(f"Run {run.get('id')} has no files array.")
        for item in files:
            file_id = str(item.get("id", ""))
            located = listed.get(file_id)
            if not isinstance(located, dict):
                raise ReportError(f"Historical result is missing from xml-index.json: {file_id}")
            rel = safe_zip_path(str(located.get("zip", "")))
            entry = safe_entry_name(str(located.get("name", "")))
            zip_path = _contained(previous, previous / rel)
            if zip_path not in opened:
                if not zip_path.is_file():
                    raise ReportError(f"Historical result is missing: {rel.as_posix()}")
                with zipfile.ZipFile(zip_path) as archive:
                    opened[zip_path] = {name: archive.read(name) for name in archive.namelist()}
            data = opened[zip_path].get(entry)
            if data is None:
                raise ReportError(f"Historical result is missing: {entry}")
            entries[file_id] = data
    return runs, entries


def parse_report(path: Path) -> ParsedReport:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ReportError(f"Could not read XML: {path}: {exc}") from exc
    return parse_bytes(data, str(path))


def parse_bytes(data: bytes, label: str) -> ParsedReport:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ReportError(f"Invalid XML: {label}: {exc}") from exc
    kind = local_tag(root.tag)
    if kind in {"testsuites", "testsuite"}:
        return ParsedReport("junit", _cases(root, "testcase", _junit_case))
    raise ReportError(f"Unsupported test XML root <{kind}>: {label}")


def extract_pages_zip(zip_path: Path, dest: Path) -> None:
    """Unpack a github-pages artifact zip (a tar inside a zip)."""

    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "artifact.tar"
        with zipfile.ZipFile(zip_path) as archive:
            tar_name = _tar_member(archive)
            with archive.open(tar_name) as source, tar_path.open("wb") as target:
                shutil.copyfileobj(source, target)
        _extract_tar(tar_path, dest)


def fetch_previous(dest: Path) -> str:
    """Fill dest from the latest Pages artifact, else the live site.

    Return ``artifact``, ``pages``, or ``empty``.
    """

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    try:
        if _try_artifact(dest):
            return "artifact"
        if _try_live(dest):
            return "pages"
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    print("No previous test results site.")
    return "empty"


def _distinct_dirs(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) < len(resolved):
        raise ReportError("incoming, previous, and out must be different directories.")
    for left in resolved:
        for right in resolved:
            if left != right and left in right.parents:
                raise ReportError("incoming, previous, and out must not contain each other.")


def tool_name(relative: str) -> str:
    parts = PurePosixPath(relative).parts
    filename = parts[-1] if parts else ""
    match = _TOOL_PREFIX.match(filename)
    if match:
        return match.group(1)
    if len(parts) >= 2 and parts[0] not in {"", ".", ".."}:
        return parts[0]
    return "unknown"


def safe_token(value: str) -> str:
    if not _SAFE_ID.fullmatch(value) or ".." in value or value.startswith("."):
        raise ReportError(f"Unsafe id: {value}")
    return value


def safe_filename(name: str) -> str:
    base = PurePosixPath(name.replace("\\", "/")).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    if not cleaned:
        cleaned = "result"
    cleaned = cleaned.replace("..", ".")
    if not cleaned.lower().endswith(".xml"):
        cleaned += ".xml"
    return cleaned


def safe_zip_path(value: str) -> Path:
    if not _ZIP_PATH.fullmatch(value):
        raise ReportError(f"Unsafe zip path: {value}")
    return Path(*PurePosixPath(value).parts)


def safe_entry_name(value: str) -> str:
    return safe_result_path(value).as_posix()


def safe_result_path(value: str) -> Path:
    rel = PurePosixPath(value)
    if (
        not value
        or rel.is_absolute()
        or ".." in rel.parts
        or not value.startswith("results/")
        or rel.suffix.lower() != ".xml"
    ):
        raise ReportError(f"Unsafe result path: {value}")
    return Path(*rel.parts)


def normalize_time(value: str) -> str:
    text = value.strip()
    if not text:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReportError(f"Invalid timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _write_site(
    out: Path,
    app_dir: Path,
    meta: RunMeta,
    created_at: str,
    run_key: str,
    new_files: list[tuple[Path, str, str, ParsedReport]],
    old_files: list[tuple[dict, list[tuple[dict, ParsedReport, bytes]]]],
    chunk_size: int,
) -> None:
    runs: list[dict] = []
    stored: list[tuple[dict, ParsedReport]] = []
    packed: list[StoredXml] = []
    for run, files in old_files:
        records = []
        for item, parsed, data in files:
            record = _file_record(
                str(run["id"]),
                str(item["name"]),
                str(item.get("tool") or tool_name(str(item["name"]))),
                parsed,
            )
            records.append(record)
            stored.append((record, parsed))
            packed.append(
                StoredXml(
                    file_id=record["id"],
                    run_id=str(run["id"]),
                    created_at=str(run.get("created_at", "")),
                    name=record["name"],
                    data=data,
                )
            )
        runs.append(_assemble_run(run, records))

    fresh_records = []
    for source, name, tool, parsed in new_files:
        record = _file_record(run_key, name, tool, parsed)
        fresh_records.append(record)
        stored.append((record, parsed))
        packed.append(
            StoredXml(
                file_id=record["id"],
                run_id=run_key,
                created_at=created_at,
                name=name,
                data=source.read_bytes(),
            )
        )
    runs.append(
        _assemble_run(
            {
                "id": run_key,
                "run_id": meta.run_id,
                "run_attempt": _maybe_int(meta.run_attempt),
                "run_number": meta.run_number,
                "sha": meta.sha,
                "ref": meta.ref,
                "event": meta.event,
                "actor": meta.actor,
                "url": meta.url,
                "created_at": created_at,
            },
            fresh_records,
        )
    )
    runs.sort(key=lambda run: (str(run["created_at"]), str(run["id"])), reverse=True)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "generated_at": utc_now(),
        "repository": meta.repository,
        "runs": runs,
        "cases": _collect_cases(runs, stored),
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    (out / "summary.json").write_text(text, encoding="utf-8", newline="\n")
    _write_chunks(out, packed, chunk_size)
    _copy_app(app_dir, out)


def _collect_cases(runs: list[dict], stored: list[tuple[dict, ParsedReport]]) -> list[dict]:
    by_file = {record["id"]: parsed for record, parsed in stored}
    order = sorted(runs, key=lambda run: (str(run["created_at"]), str(run["id"])))
    cases: dict[str, dict] = {}
    for run in order:
        for item in run["files"]:
            parsed = by_file[item["id"]]
            for case in parsed.cases:
                entry = cases.setdefault(
                    case.id,
                    {"id": case.id, "name": case.name, "classname": case.classname, "points": {}},
                )
                if case.name:
                    entry["name"] = case.name
                if case.classname:
                    entry["classname"] = case.classname
                point = entry["points"].get(run["id"])
                if point is None:
                    entry["points"][run["id"]] = {
                        "run_id": run["id"],
                        "file_id": item["id"],
                        "created_at": run["created_at"],
                        "result": case.result,
                        "duration_seconds": round(case.duration_seconds, 6),
                    }
                    continue
                point["duration_seconds"] = round(
                    point["duration_seconds"] + case.duration_seconds,
                    6,
                )
                if _RANK.get(case.result, 9) < _RANK.get(point["result"], 9):
                    point["result"] = case.result
                    point["file_id"] = item["id"]
    listed = []
    for entry in cases.values():
        points = sorted(entry["points"].values(), key=lambda point: (point["created_at"], point["run_id"]))
        latest = points[-1]
        listed.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "classname": entry["classname"],
                "latest_result": latest["result"],
                "latest_at": latest["created_at"],
                "points": points,
            }
        )
    listed.sort(key=lambda item: item["id"])
    return listed


def _assemble_run(meta: dict, files: list[dict]) -> dict:
    files = sorted(files, key=lambda item: item["name"])
    totals = Totals()
    for item in files:
        totals.add_record(item)
    data = totals.as_dict()
    data["files"] = len(files)
    return {
        "id": meta["id"],
        "run_id": meta.get("run_id", ""),
        "run_attempt": meta.get("run_attempt"),
        "run_number": meta.get("run_number"),
        "sha": meta.get("sha", ""),
        "ref": meta.get("ref", ""),
        "event": meta.get("event", ""),
        "actor": meta.get("actor", ""),
        "url": meta.get("url", ""),
        "created_at": meta.get("created_at", ""),
        "files": files,
        "tools": _tool_totals(files),
        "totals": data,
    }


def _tool_totals(files: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in files:
        grouped.setdefault(str(item["tool"]), []).append(item)
    tools = []
    for name in sorted(grouped):
        totals = Totals()
        for item in grouped[name]:
            totals.add_record(item)
        data = totals.as_dict()
        data["tool"] = name
        data["files"] = len(grouped[name])
        tools.append(data)
    return tools


def _file_record(run_id: str, name: str, tool: str, parsed: ParsedReport) -> dict:
    totals = Totals()
    for case in parsed.cases:
        totals.add_case(case)
    data = totals.as_dict()
    return {
        "id": hashlib.sha256(f"{run_id}/{name}".encode()).hexdigest()[:16],
        "name": name,
        "format": parsed.fmt,
        "tool": tool,
        **data,
    }


def _write_chunks(out: Path, packed: list[StoredXml], chunk_size: int) -> None:
    ordered = sorted(packed, key=lambda item: (item.created_at, item.run_id, item.name, item.file_id))
    mapping: dict[str, dict[str, str]] = {}
    for chunk_index, start in enumerate(range(0, len(ordered), chunk_size)):
        chunk = ordered[start : start + chunk_size]
        rel = f"xml/{chunk_index:05d}.zip"
        target = _contained(out, out / safe_zip_path(rel))
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w") as archive:
            for item in chunk:
                entry = safe_entry_name(f"results/{item.run_id}/{item.name}")
                info = zipfile.ZipInfo(filename=entry, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.flag_bits |= 0x800
                archive.writestr(info, item.data)
                mapping[item.file_id] = {"zip": rel, "name": entry}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR,
        "chunk_size": chunk_size,
        "files": mapping,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (out / INDEX_NAME).write_text(text, encoding="utf-8", newline="\n")


def _read_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"Invalid {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReportError(f"{label} is not an object.")
    return data


def _read_index(previous: Path) -> dict:
    path = previous / INDEX_NAME
    if not path.is_file():
        raise ReportError("xml-index.json is missing.")
    index = _read_json(path, INDEX_NAME)
    if index.get("generator") != GENERATOR or index.get("schema_version") != SCHEMA_VERSION:
        raise ReportError("xml-index.json is not a test results index.")
    files = index.get("files")
    if not isinstance(files, dict):
        raise ReportError("xml-index.json has no files object.")
    return index


def _unique_names(
    files: list[tuple[Path, str, str, ParsedReport]],
) -> list[tuple[Path, str, str, ParsedReport]]:
    used: set[str] = set()
    unique: list[tuple[Path, str, str, ParsedReport]] = []
    for source, name, tool, parsed in files:
        candidate = name
        number = 2
        while candidate in used:
            candidate = f"{name[:-4]}-{number}.xml"
            number += 1
        used.add(candidate)
        unique.append((source, candidate, tool, parsed))
    return unique


def _cases(root: ET.Element, tag: str, reader) -> list[ParsedCase]:
    seen: dict[str, int] = {}
    cases: list[ParsedCase] = []
    for node in root.iter():
        if local_tag(node.tag) != tag:
            continue
        raw_id, name, classname, result, duration = reader(node)
        count = seen.get(raw_id, 0) + 1
        seen[raw_id] = count
        case_id = raw_id if count == 1 else f"{raw_id}#{count}"
        cases.append(
            ParsedCase(
                id=case_id,
                name=name,
                classname=classname,
                result=result,
                duration_seconds=duration,
            )
        )
    return cases


def _junit_case(node: ET.Element) -> tuple[str, str, str, str, float]:
    name = node.attrib.get("name") or "(unknown)"
    classname = node.attrib.get("classname") or ""
    file_name = (node.attrib.get("file") or "").replace("\\", "/")
    if file_name and name:
        raw_id = f"{file_name}::{name}"
    elif classname and name:
        raw_id = f"{classname}::{name}"
    else:
        raw_id = name
    return raw_id, name, classname, _result_from_children(node), _seconds(node.attrib.get("time"))


def _result_from_children(node: ET.Element) -> str:
    tags = {local_tag(child.tag) for child in list(node)}
    if "failure" in tags or "error" in tags:
        return "failed"
    if "skipped" in tags:
        return "skipped"
    return "passed"


def _seconds(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return round(float(value), 6)
    except ValueError:
        return 0.0


def _maybe_int(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _copy_app(app_dir: Path, out: Path) -> None:
    for name in APP_FILES:
        source = app_dir / name
        if not source.is_file():
            raise ReportError(f"Missing page asset: {source}")
        shutil.copyfile(source, out / name)
    (out / ".nojekyll").write_text("", encoding="utf-8", newline="\n")


def _contained(root: Path, path: Path) -> Path:
    root_resolved = root.resolve()
    resolved = path.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ReportError(f"Path escapes the site directory: {path}")
    return path


def _try_artifact(dest: Path) -> bool:
    artifacts = _list_pages_artifacts()
    if not artifacts:
        print("No unexpired github-pages artifact.")
        return False
    errors: list[str] = []
    for item in artifacts[:5]:
        artifact_id = item.get("id")
        try:
            _download_artifact(int(artifact_id), dest)
            _require_our_summary(dest)
        except (ReportError, ValueError, TypeError) as exc:
            errors.append(str(exc))
            _empty_dir(dest)
            continue
        print(f"Fetched previous site from artifact {artifact_id}.")
        return True
    raise ReportError("Could not download a previous Pages artifact: " + "; ".join(errors))


def _try_live(dest: Path) -> bool:
    base = _pages_html_url()
    if not base:
        return False
    token = utc_now().replace(":", "").replace("-", "")
    url = base.rstrip("/") + "/summary.json?t=" + token
    try:
        body = _http_get(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and not _site_is_published(base):
            print("No previous test results site.")
            return False
        if exc.code == 404:
            raise ReportError(
                "GitHub Pages exists but summary.json was not found. "
                "Refusing to replace an unrelated site."
            ) from exc
        raise ReportError(f"Could not download summary.json ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise ReportError(f"Could not download summary.json: {exc.reason}") from exc
    try:
        summary = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ReportError(f"Published summary.json is not JSON: {exc}") from exc
    if summary.get("generator") != GENERATOR or summary.get("schema_version") != SCHEMA_VERSION:
        raise ReportError("Published site is not a test results site.")
    (dest / "summary.json").write_bytes(body)
    index_url = base.rstrip("/") + "/" + INDEX_NAME + "?t=" + token
    try:
        index_body = _http_get(index_url)
    except urllib.error.URLError as exc:
        raise ReportError(f"Could not download {INDEX_NAME}: {exc}") from exc
    (dest / INDEX_NAME).write_bytes(index_body)
    index = _read_index(dest)
    zips = sorted({str(item.get("zip", "")) for item in index["files"].values() if isinstance(item, dict)})
    for rel_text in zips:
        rel = safe_zip_path(rel_text)
        target = _contained(dest, dest / rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_url = base.rstrip("/") + "/" + rel.as_posix() + "?t=" + token
        try:
            target.write_bytes(_http_get(file_url))
        except urllib.error.URLError as exc:
            raise ReportError(f"Could not download {rel.as_posix()}: {exc}") from exc
    print("Fetched previous site from the published Pages URL.")
    return True


def _site_is_published(base: str) -> bool:
    """True when the Pages URL already serves a site."""

    try:
        _http_get(base.rstrip("/") + "/")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise ReportError(f"Could not check the Pages site ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise ReportError(f"Could not check the Pages site: {exc.reason}") from exc
    return True


def _require_our_summary(dest: Path) -> None:
    path = dest / "summary.json"
    if not path.is_file():
        raise ReportError("github-pages artifact has no summary.json.")
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"Artifact summary.json is not JSON: {exc}") from exc
    if summary.get("generator") != GENERATOR or summary.get("schema_version") != SCHEMA_VERSION:
        raise ReportError("github-pages artifact is not a test results site.")
    _read_index(dest)


def _list_pages_artifacts() -> list[dict]:
    repo = _require_repo()
    current = os.environ.get("GITHUB_RUN_ID", "").strip()
    payload = _gh_json(
        [
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repo}/actions/artifacts?name=github-pages&per_page=100",
        ]
    )
    artifacts: list[dict] = []
    pages = payload if isinstance(payload, list) else [payload]
    for page in pages:
        if isinstance(page, dict):
            artifacts.extend(item for item in page.get("artifacts") or [] if isinstance(item, dict))
    chosen = []
    for item in artifacts:
        if item.get("name") != "github-pages" or item.get("expired"):
            continue
        run = item.get("workflow_run") or {}
        if current and str(run.get("id") or "") == current:
            continue
        chosen.append(item)
    chosen.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return chosen


def _pages_html_url() -> str | None:
    repo = _require_repo()
    try:
        payload = _gh_json(["api", f"repos/{repo}/pages"])
    except GhNotFound:
        return None
    if not isinstance(payload, dict):
        return None
    url = payload.get("html_url")
    return str(url) if url else None


def _download_artifact(artifact_id: int, dest: Path) -> None:
    repo = _require_repo()
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "artifact.zip"
        _gh_bytes(f"repos/{repo}/actions/artifacts/{artifact_id}/zip", zip_path)
        if zip_path.stat().st_size < 4 or zip_path.read_bytes()[:2] != b"PK":
            raise ReportError(f"Artifact {artifact_id} was not a zip.")
        extract_pages_zip(zip_path, dest)


def _http_get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": GENERATOR})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _require_repo() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if repo.count("/") != 1:
        raise ReportError("GITHUB_REPOSITORY is unset.")
    return repo


def _gh_json(args: list[str]) -> object:
    result = _gh(args, binary=False)
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError as exc:
        raise ReportError(f"gh {' '.join(args)} returned invalid JSON.") from exc


def _gh_bytes(endpoint: str, dest: Path) -> None:
    result = _gh(["api", endpoint], binary=True)
    dest.write_bytes(result.stdout or b"")


def _gh(args: list[str], *, binary: bool) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["gh", *args],
            check=False,
            capture_output=True,
            text=not binary,
            encoding=None if binary else "utf-8",
        )
    except FileNotFoundError as exc:
        raise ReportError("gh is not installed.") from exc
    if result.returncode != 0:
        detail = result.stderr or ""
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        text = detail.strip()
        if "Not Found" in text or "HTTP 404" in text:
            raise GhNotFound(text)
        raise ReportError(f"gh {' '.join(args)} failed: {text}")
    return result


def _tar_member(archive: zipfile.ZipFile) -> str:
    names = [name for name in archive.namelist() if not name.endswith("/")]
    preferred = [name for name in names if PurePosixPath(name).name in {"artifact.tar", "artifact.tar.gz"}]
    matches = preferred or [name for name in names if name.endswith((".tar", ".tar.gz"))]
    if not matches:
        preview = ", ".join(names[:8]) or "(empty)"
        raise ReportError(f"Pages artifact zip did not contain a tar file: {preview}")
    return matches[0]


def _extract_tar(tar_path: Path, dest: Path) -> None:
    last_error: Exception | None = None
    for mode in ("r:", "r:gz"):
        try:
            with tarfile.open(tar_path, mode) as tar:
                tar.extractall(dest, filter="data")
            return
        except tarfile.TarError as exc:
            last_error = exc
    raise ReportError(f"Could not read the Pages artifact tar: {last_error}")


def _empty_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _meta_from_env(args: argparse.Namespace) -> RunMeta:
    def pick(flag: str, *names: str) -> str:
        value = getattr(args, flag, "") or ""
        if str(value).strip():
            return str(value).strip()
        for name in names:
            env = os.environ.get(name, "").strip()
            if env:
                return env
        return ""

    run_id = pick("run_id", "SOURCE_RUN_ID", "GITHUB_RUN_ID") or f"local-{uuid_text()}"
    attempt = pick("run_attempt", "SOURCE_RUN_ATTEMPT", "GITHUB_RUN_ATTEMPT") or "1"
    number = pick("run_number", "SOURCE_RUN_NUMBER", "GITHUB_RUN_NUMBER")
    ref = pick("ref", "SOURCE_REF", "GITHUB_REF")
    server = os.environ.get("GITHUB_SERVER_URL", "").rstrip("/")
    repo = pick("repository", "SOURCE_REPOSITORY", "GITHUB_REPOSITORY")
    run_url = pick("url", "SOURCE_URL")
    if not run_url and server and repo and run_id.isdigit():
        run_url = f"{server}/{repo}/actions/runs/{run_id}"
    return RunMeta(
        run_id=safe_token(run_id),
        run_attempt=safe_token(attempt),
        run_number=int(number) if number.isdigit() else None,
        sha=pick("sha", "SOURCE_SHA", "GITHUB_SHA"),
        ref=ref,
        event=pick("event", "SOURCE_EVENT", "GITHUB_EVENT_NAME"),
        actor=pick("actor", "SOURCE_ACTOR", "GITHUB_ACTOR"),
        url=run_url,
        created_at=pick("created_at", "SOURCE_CREATED_AT"),
        repository=repo,
    )


def uuid_text() -> str:
    return str(uuid.uuid4())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build the test results GitHub Pages site.")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch-previous", help="Download the latest Pages site.")
    fetch.add_argument("--dest", type=Path, required=True)

    build = sub.add_parser("build", help="Merge incoming XML into a new site.")
    build.add_argument("--incoming", type=Path, required=True)
    build.add_argument("--previous", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--pattern", default=r"\.xml$")
    build.add_argument("--app", type=Path)
    build.add_argument("--run-id", default="")
    build.add_argument("--run-attempt", default="")
    build.add_argument("--run-number", default="")
    build.add_argument("--sha", default="")
    build.add_argument("--ref", default="")
    build.add_argument("--event", default="")
    build.add_argument("--actor", default="")
    build.add_argument("--url", default="")
    build.add_argument("--created-at", default="")
    build.add_argument("--repository", default="")
    build.add_argument("--chunk-size", type=int, default=XML_CHUNK_SIZE)

    args = parser.parse_args(argv[1:])
    try:
        if args.command == "fetch-previous":
            print(fetch_previous(args.dest))
            return 0
        wrote = build_site(
            incoming=args.incoming,
            previous=args.previous,
            out=args.out,
            pattern=args.pattern,
            app_dir=args.app or default_app_dir(),
            meta=_meta_from_env(args),
            chunk_size=args.chunk_size,
        )
    except ReportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0 if wrote or args.command == "build" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
