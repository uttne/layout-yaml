"""Tests for the GitHub Pages test-results builder."""

import importlib.util
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "test_results_page.py"


@pytest.fixture(scope="module")
def page():
    spec = importlib.util.spec_from_file_location("test_results_page", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_junit(path: Path, cases: list[tuple[str, str, str]]) -> None:
    parts = ["<testsuites><testsuite>"]
    for fullname, result, duration in cases:
        file_name, _, name = fullname.partition("::")
        if not name:
            name = file_name
            file_name = ""
        if result == "failed":
            body = "<failure message='no'>trace</failure>"
        elif result == "skipped":
            body = "<skipped/>"
        else:
            body = ""
        parts.append(
            f"<testcase file='{file_name}' classname='{file_name}' "
            f"name='{name}' time='{duration}'>{body}</testcase>"
        )
    parts.append("</testsuite></testsuites>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts), encoding="utf-8")


def meta(page, run_id: str, created_at: str):
    return page.RunMeta(
        run_id=run_id,
        run_attempt="1",
        run_number=int(run_id),
        sha="abc123def456",
        ref="refs/heads/main",
        event="push",
        actor="tester",
        url=f"https://example.test/runs/{run_id}",
        created_at=created_at,
        repository="example/layout-yaml",
    )


def build(
    page,
    incoming: Path,
    previous: Path,
    out: Path,
    run_id: str,
    created_at: str,
    chunk_size: int | None = None,
):
    size = page.XML_CHUNK_SIZE if chunk_size is None else chunk_size
    return page.build_site(
        incoming=incoming,
        previous=previous,
        out=out,
        pattern=r"\.xml$",
        app_dir=page.default_app_dir(),
        meta=meta(page, run_id, created_at),
        chunk_size=size,
    )


def test_parse_counts_and_ignores_skipped_in_rate(page, tmp_path: Path) -> None:
    path = tmp_path / "sample.xml"
    write_junit(
        path,
        [
            ("tests/test_a.py::test_ok", "passed", "0.1"),
            ("tests/test_a.py::test_bad", "failed", "0.2"),
            ("tests/test_a.py::test_skip", "skipped", "0"),
        ],
    )
    parsed = page.parse_report(path)
    assert parsed.fmt == "junit"
    assert [case.result for case in parsed.cases] == ["passed", "failed", "skipped"]
    totals = page.Totals()
    for case in parsed.cases:
        totals.add_case(case)
    assert totals.as_dict()["success_rate"] == 0.5
    assert totals.as_dict()["total"] == 3


def test_non_junit_root_is_rejected(page, tmp_path: Path) -> None:
    path = tmp_path / "other.xml"
    path.write_text("<test-run/>", encoding="utf-8")
    with pytest.raises(page.ReportError, match="Unsupported"):
        page.parse_report(path)


def test_merge_keeps_history_and_groups_tools(page, tmp_path: Path) -> None:
    first_in = tmp_path / "in1"
    second_in = tmp_path / "in2"
    previous = tmp_path / "previous"
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    previous.mkdir()
    write_junit(
        first_in / "pytest-20261003T000000Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.xml",
        [("tests/test_a.py::test_ok", "passed", "0.2")],
    )
    write_junit(
        first_in
        / "playwright"
        / "playwright-20261003T000000Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.xml",
        [("spec::loads", "passed", "0.4"), ("spec::skips", "skipped", "0.1")],
    )
    assert build(page, first_in, previous, out1, "100", "2026-10-03T00:00:00Z")
    summary = json.loads((out1 / "summary.json").read_text(encoding="utf-8"))
    assert summary["schema_version"] == 1
    assert summary["runs"][0]["totals"]["files"] == 2
    tools = {item["tool"]: item for item in summary["runs"][0]["tools"]}
    assert tools["pytest"]["passed"] == 1
    assert tools["playwright"]["skipped"] == 1
    assert (out1 / "index.html").is_file()
    assert (out1 / ".nojekyll").is_file()

    write_junit(
        second_in / "pytest-20261003T010000Z-cccccccccccccccccccccccccccccccc.xml",
        [("tests/test_a.py::test_ok", "failed", "0.3")],
    )
    assert build(page, second_in, out1, out2, "101", "2026-10-03T01:00:00Z")
    merged = json.loads((out2 / "summary.json").read_text(encoding="utf-8"))
    assert [run["id"] for run in merged["runs"]] == ["101-1", "100-1"]
    case = next(item for item in merged["cases"] if item["id"].endswith("test_ok"))
    assert [point["result"] for point in case["points"]] == ["passed", "failed"]
    assert case["latest_result"] == "failed"
    index = json.loads((out2 / "xml-index.json").read_text(encoding="utf-8"))
    published = [item for run in merged["runs"] for item in run["files"]]
    assert len(published) == len(index["files"])
    for item in published:
        assert "path" not in item
        assert "zip" not in item
        assert item["id"] in index["files"]
    assert not list(out2.rglob("*.xml"))


def test_same_run_replaces_previous_files(page, tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    previous = tmp_path / "previous"
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    previous.mkdir()
    write_junit(
        incoming / "pytest-20261003T000000Z-dddddddddddddddddddddddddddddddd.xml",
        [("tests/test_a.py::test_ok", "passed", "0.1")],
    )
    assert build(page, incoming, previous, out1, "100", "2026-10-03T00:00:00Z")
    write_junit(
        incoming / "pytest-20261003T000000Z-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee.xml",
        [("tests/test_a.py::test_ok", "failed", "0.4")],
    )
    assert build(page, incoming, out1, out2, "100", "2026-10-03T00:05:00Z")
    summary = json.loads((out2 / "summary.json").read_text(encoding="utf-8"))
    assert [run["id"] for run in summary["runs"]] == ["100-1"]
    assert summary["runs"][0]["totals"]["failed"] == 1
    assert summary["cases"][0]["latest_result"] == "failed"


def test_pattern_skips_non_xml(page, tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    previous = tmp_path / "previous"
    out = tmp_path / "out"
    previous.mkdir()
    (incoming).mkdir()
    (incoming / "notes.txt").write_text("nope", encoding="utf-8")
    write_junit(
        incoming / "pytest-20261003T000000Z-ffffffffffffffffffffffffffffffff.xml",
        [("tests/test_a.py::test_ok", "passed", "0.1")],
    )
    assert build(page, incoming, previous, out, "7", "2026-10-03T00:00:00Z")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["runs"][0]["totals"]["files"] == 1


def test_missing_history_refuses_to_publish(page, tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    (tmp_path / "previous").mkdir()
    write_junit(
        incoming / "pytest-20261003T000000Z-11111111111111111111111111111111.xml",
        [("tests/test_a.py::test_ok", "passed", "0.1")],
    )
    assert build(
        page, incoming, tmp_path / "previous", out1, "8", "2026-10-03T00:00:00Z"
    )
    next((out1 / "xml").glob("*.zip")).unlink()
    write_junit(
        incoming / "pytest-20261003T010000Z-22222222222222222222222222222222.xml",
        [("tests/test_a.py::test_ok", "passed", "0.1")],
    )
    with pytest.raises(page.ReportError, match="missing"):
        build(page, incoming, out1, out2, "9", "2026-10-03T01:00:00Z")
    assert not out2.exists()


def test_unsafe_zip_path_is_rejected(page, tmp_path: Path) -> None:
    previous = tmp_path / "previous"
    previous.mkdir()
    summary = {
        "schema_version": 1,
        "generator": page.GENERATOR,
        "runs": [{"id": "1-1", "files": [{"id": "deadbeef", "name": "a.xml"}]}],
    }
    index = {
        "schema_version": 1,
        "generator": page.GENERATOR,
        "chunk_size": 50,
        "files": {
            "deadbeef": {"zip": "xml/../secret.zip", "name": "results/1-1/a.xml"}
        },
    }
    (previous / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (previous / "xml-index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(page.ReportError, match="Unsafe"):
        page.load_previous(previous)


def test_xml_is_split_into_fixed_chunks(page, tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    previous = tmp_path / "previous"
    out = tmp_path / "out"
    previous.mkdir()
    for name, title in (
        ("pytest-20261003T000000Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.xml", "a"),
        ("pytest-20261003T000000Z-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.xml", "b"),
        ("pytest-20261003T000000Z-cccccccccccccccccccccccccccccccc.xml", "c"),
    ):
        write_junit(
            incoming / name,
            [(f"tests/test_a.py::test_{title}", "passed", "0.1")],
        )
    assert build(page, incoming, previous, out, "3", "2026-10-03T00:00:00Z", 2)
    index = json.loads((out / "xml-index.json").read_text(encoding="utf-8"))
    assert index["chunk_size"] == 2
    zips = {item["zip"] for item in index["files"].values()}
    assert zips == {"xml/00000.zip", "xml/00001.zip"}
    counts = {"xml/00000.zip": 0, "xml/00001.zip": 0}
    for item in index["files"].values():
        counts[item["zip"]] += 1
    assert counts == {"xml/00000.zip": 2, "xml/00001.zip": 1}
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert "xml" not in summary


def test_extract_pages_zip(page, tmp_path: Path) -> None:
    site = tmp_path / "site"
    xml_dir = site / "results" / "1-1"
    xml_dir.mkdir(parents=True)
    (site / "summary.json").write_text("{}\n", encoding="utf-8")
    (xml_dir / "pytest.xml").write_text("<test-run/>", encoding="utf-8")
    tar_path = tmp_path / "artifact.tar"
    with tarfile.open(tar_path, "w") as tar:
        tar.add(site / "summary.json", arcname="./summary.json")
        tar.add(xml_dir / "pytest.xml", arcname="./results/1-1/pytest.xml")
    zip_path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(tar_path, arcname="artifact.tar")
    dest = tmp_path / "dest"
    page.extract_pages_zip(zip_path, dest)
    assert (dest / "summary.json").is_file()
    assert (dest / "results" / "1-1" / "pytest.xml").is_file()


def test_tool_name_from_prefix_or_directory(page) -> None:
    filename = "pytest-20261003T000000Z-abc.xml"
    assert page.tool_name(filename) == "pytest"
    assert page.tool_name(f"nested/{filename}") == "pytest"
    assert page.tool_name("nested/results.xml") == "nested"


def test_live_404_on_unpublished_site_starts_empty(
    page, tmp_path: Path, monkeypatch
) -> None:
    def http_get(url: str) -> bytes:
        raise page.urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(
        page, "_pages_html_url", lambda: "https://example.test/layout-yaml"
    )
    monkeypatch.setattr(page, "_http_get", http_get)
    assert page._try_live(tmp_path / "previous") is False


def test_live_404_on_other_site_is_refused(page, tmp_path: Path, monkeypatch) -> None:
    def http_get(url: str) -> bytes:
        if url.split("?", 1)[0].endswith("summary.json"):
            raise page.urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return b"<html>docs</html>"

    monkeypatch.setattr(
        page, "_pages_html_url", lambda: "https://example.test/layout-yaml"
    )
    monkeypatch.setattr(page, "_http_get", http_get)
    with pytest.raises(page.ReportError, match="unrelated"):
        page._try_live(tmp_path / "previous")


def test_empty_incoming_does_not_write(page, tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    previous = tmp_path / "previous"
    out = tmp_path / "out"
    incoming.mkdir()
    previous.mkdir()
    assert build(page, incoming, previous, out, "10", "2026-10-03T00:00:00Z") is False
    assert not out.exists()
