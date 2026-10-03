"""Concrete syntax tree node types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Document:
    """Root document node."""

    start: int
    end: int
    preamble_end: int
    mapping: BlockMapping


@dataclass(frozen=True, slots=True)
class BlockMapping:
    start: int
    end: int
    entries: tuple[MappingEntry, ...]


@dataclass(frozen=True, slots=True)
class MappingEntry:
    start: int
    end: int
    key: PlainScalar
    value: BlockMapping | BlockSequence | ScalarNode | None


@dataclass(frozen=True, slots=True)
class BlockSequence:
    start: int
    end: int
    items: tuple[SequenceItem, ...]


@dataclass(frozen=True, slots=True)
class SequenceItem:
    start: int
    end: int
    value: BlockMapping | BlockSequence | ScalarNode


@dataclass(frozen=True, slots=True)
class PlainScalar:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class DoubleQuotedScalar:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SingleQuotedScalar:
    start: int
    end: int


ScalarNode = PlainScalar | DoubleQuotedScalar | SingleQuotedScalar
