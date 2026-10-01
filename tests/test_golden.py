"""Golden round-trip and edit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from layout_yaml import dumps, loads

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def _golden_cases() -> list[str]:
    if not GOLDEN_DIR.is_dir():
        return []
    cases: list[str] = []
    for path in sorted(GOLDEN_DIR.iterdir()):
        if not path.is_dir():
            continue
        ops = json.loads((path / "ops.json").read_text(encoding="utf-8"))
        if ops.get("ops"):
            continue
        cases.append(path.name)
    return cases


@pytest.mark.parametrize("case", _golden_cases())
def test_golden_roundtrip(case: str) -> None:
    case_dir = GOLDEN_DIR / case
    input_text = (case_dir / "input.yaml").read_text(encoding="utf-8")
    expected = (case_dir / "expected.yaml").read_text(encoding="utf-8")
    doc = loads(input_text)
    result = dumps(doc)
    assert result == expected
