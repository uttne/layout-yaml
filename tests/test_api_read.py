"""Read-only MappingView / SequenceView on identity golden."""

from __future__ import annotations

from pathlib import Path

from layout_yaml import loads

GOLDEN = Path(__file__).resolve().parent / "golden" / "00_identity_roundtrip"
CASE = GOLDEN / "input.yaml"


def test_mapping_view_reads_identity_golden() -> None:
    doc = loads(CASE.read_text(encoding="utf-8"))
    assert doc["name"] == "demo"
    assert list(doc["items"]) == ["a", "b"]
    assert doc["items"][0] == "a"
    assert doc["items"][1] == "b"
    assert doc["empty"] is None
    assert doc["nested"]["ok"] is True
