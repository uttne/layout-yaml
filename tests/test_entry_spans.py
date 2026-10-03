"""Entry source spans for leading and trailing trivia."""

from __future__ import annotations

from pathlib import Path

from layout_yaml import dumps, loads
from layout_yaml.cst import BlockMapping

GOLDEN = Path(__file__).resolve().parent / "golden"
CASE_06 = GOLDEN / "06_delete_key_with_owning_comments" / "input.yaml"


def _texts(source: str, mapping: BlockMapping) -> list[str]:
    return [source[entry.start : entry.end] for entry in mapping.entries]


def test_delete_comment_golden_entry_spans() -> None:
    source = CASE_06.read_text(encoding="utf-8")
    doc = loads(source)
    assert _texts(source, doc._root.mapping) == [
        "keep: 1\n\n",
        "# belongs to removable\n# also belongs to removable\nremovable: yes\n\n",
        "# belongs to keep_tail\nkeep_tail: 2\n",
    ]
    assert dumps(doc) == source


def test_nested_sibling_indent_is_next_entry_leading() -> None:
    source = "outer:\n  a: 1\n  b: 2\n"
    doc = loads(source)
    outer = doc._root.mapping.entries[0]
    assert isinstance(outer.value, BlockMapping)
    assert _texts(source, outer.value) == ["a: 1\n", "  b: 2\n"]
    assert dumps(doc) == source


def test_nested_comment_above_key_is_that_entry_leading() -> None:
    source = "o:\n  # c\n  a: 1\n"
    doc = loads(source)
    assert doc["o"]["a"] == 1
    outer = doc._root.mapping.entries[0]
    assert isinstance(outer.value, BlockMapping)
    assert _texts(source, outer.value) == ["# c\n  a: 1\n"]
    assert dumps(doc) == source


def test_eof_standalone_comment_stays_on_previous_entry() -> None:
    source = "a: 1\n# tail\n"
    doc = loads(source)
    assert _texts(source, doc._root.mapping) == [source]
    assert dumps(doc) == source


def test_blank_line_breaks_comment_ownership() -> None:
    attached = "a: 1\n\n# c\nb: 2\n"
    doc = loads(attached)
    assert _texts(attached, doc._root.mapping) == ["a: 1\n\n", "# c\nb: 2\n"]
    assert dumps(doc) == attached

    separated = "a: 1\n# c\n\nb: 2\n"
    doc = loads(separated)
    assert _texts(separated, doc._root.mapping) == ["a: 1\n# c\n\n", "b: 2\n"]
    assert dumps(doc) == separated
