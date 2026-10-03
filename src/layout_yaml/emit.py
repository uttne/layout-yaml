"""Emit YAML text from CST."""

from __future__ import annotations

from typing import Any

from layout_yaml.cst import (
    BlockMapping,
    BlockSequence,
    Document,
    MappingEntry,
    ScalarNode,
    SequenceItem,
)


def emit_document(source: str, document: Document) -> str:
    parts: list[str] = []
    if document.preamble_end > document.start:
        parts.append(source[document.start : document.preamble_end])
    parts.append(emit_node(source, document.mapping))
    return "".join(parts)


def emit_node(source: str, node: Any) -> str:
    match node:
        case BlockMapping() as mapping:
            return "".join(emit_node(source, entry) for entry in mapping.entries)
        case MappingEntry() as entry:
            return source[entry.start : entry.end]
        case BlockSequence() as sequence:
            return "".join(emit_node(source, item) for item in sequence.items)
        case SequenceItem() as item:
            return source[item.start : item.end]
        case ScalarNode() as scalar:
            return source[scalar.start : scalar.end]
        case _:
            return source[node.start : node.end]
