"""Entry source spans for leading and trailing trivia."""

from __future__ import annotations

from pathlib import Path

from layout_yaml import dumps, loads
from layout_yaml.cst import BlockMapping, BlockSequence

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


def test_inner_entry_stops_before_outer_key_indent() -> None:
    source = "server:\n  listen:\n    address: 0.0.0.0\n    port: 80\n  name: edge\n"
    doc = loads(source)
    root = doc._root.mapping
    assert _texts(source, root) == [source]
    server = root.entries[0]
    assert isinstance(server.value, BlockMapping)
    assert _texts(source, server.value) == [
        "listen:\n    address: 0.0.0.0\n    port: 80\n",
        "  name: edge\n",
    ]
    listen = server.value.entries[0]
    assert isinstance(listen.value, BlockMapping)
    assert _texts(source, listen.value) == [
        "address: 0.0.0.0\n",
        "    port: 80\n",
    ]
    assert dumps(doc) == source


def test_inner_entry_keeps_blank_line_before_outer_indent() -> None:
    source = "server:\n  listen:\n    port: 80\n\n  name: edge\n"
    doc = loads(source)
    server = doc._root.mapping.entries[0]
    assert isinstance(server.value, BlockMapping)
    assert _texts(source, server.value) == [
        "listen:\n    port: 80\n\n",
        "  name: edge\n",
    ]
    listen = server.value.entries[0]
    assert isinstance(listen.value, BlockMapping)
    assert _texts(source, listen.value) == ["port: 80\n\n"]
    assert dumps(doc) == source


def test_plain_scalar_at_eof() -> None:
    bare = "a: 1"
    doc = loads(bare)
    assert doc["a"] == 1
    assert _texts(bare, doc._root.mapping) == [bare]
    assert dumps(doc) == bare

    pair = "a: 1\nb: 2"
    doc = loads(pair)
    assert doc["a"] == 1
    assert doc["b"] == 2
    assert _texts(pair, doc._root.mapping) == ["a: 1\n", "b: 2"]
    assert dumps(doc) == pair


def test_sequence_item_includes_line_indent() -> None:
    source = "items:\n  - a\n  - b\n"
    doc = loads(source)
    entry = doc._root.mapping.entries[0]
    assert isinstance(entry.value, BlockSequence)
    assert [source[item.start : item.end] for item in entry.value.items] == [
        "  - a\n",
        "  - b\n",
    ]
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
