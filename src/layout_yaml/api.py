"""Document and dict-like views over CST."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from layout_yaml.cst import (
    BlockMapping,
    BlockSequence,
    MappingEntry,
    ScalarNode,
    SequenceItem,
)
from layout_yaml.cst import (
    Document as CstDocument,
)
from layout_yaml.scalar import decode_scalar, plain_scalar_text


class Document(Mapping[str, Any]):
    """Root document — mapping view over the CST."""

    __slots__ = ("_source", "_root")

    def __init__(self, source: str, root: CstDocument) -> None:
        self._source = source
        self._root = root

    @property
    def _mapping(self) -> BlockMapping:
        return self._root.mapping

    def __getitem__(self, key: str) -> Any:
        entry = self._find_entry(key)
        if entry is None:
            raise KeyError(key)
        return view_for_value(self._source, entry.value)

    def __iter__(self) -> Iterator[str]:
        for entry in self._mapping.entries:
            yield plain_scalar_text(self._source, entry.key).strip()

    def __len__(self) -> int:
        return len(self._mapping.entries)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self._find_entry(key) is not None

    def _find_entry(self, key: str) -> MappingEntry | None:
        for entry in self._mapping.entries:
            if plain_scalar_text(self._source, entry.key).strip() == key:
                return entry
        return None


class MappingView(Mapping[str, Any]):
    __slots__ = ("_source", "_mapping")

    def __init__(self, source: str, mapping: BlockMapping) -> None:
        self._source = source
        self._mapping = mapping

    def __getitem__(self, key: str) -> Any:
        for entry in self._mapping.entries:
            if plain_scalar_text(self._source, entry.key).strip() == key:
                return view_for_value(self._source, entry.value)
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        for entry in self._mapping.entries:
            yield plain_scalar_text(self._source, entry.key).strip()

    def __len__(self) -> int:
        return len(self._mapping.entries)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return any(
            plain_scalar_text(self._source, entry.key).strip() == key
            for entry in self._mapping.entries
        )


class SequenceView(Mapping[int, Any]):
    """List-like read access by index (Mapping protocol for minimal surface)."""

    __slots__ = ("_source", "_sequence")

    def __init__(self, source: str, sequence: BlockSequence) -> None:
        self._source = source
        self._sequence = sequence

    def __getitem__(self, index: int) -> Any:
        if not isinstance(index, int):
            raise TypeError("sequence indices must be integers")
        try:
            item = self._sequence.items[index]
        except IndexError:
            raise KeyError(index) from None
        return view_for_value(self._source, item.value)

    def __len__(self) -> int:
        return len(self._sequence.items)

    def __iter__(self) -> Iterator[int]:
        yield from range(len(self._sequence.items))

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, int):
            return False
        return 0 <= key < len(self._sequence.items)


def view_for_value(
    source: str,
    value: BlockMapping | BlockSequence | ScalarNode | SequenceItem | None,
) -> Any:
    if value is None:
        return None
    if isinstance(value, BlockMapping):
        return MappingView(source, value)
    if isinstance(value, BlockSequence):
        return SequenceView(source, value)
    if isinstance(value, ScalarNode):
        return decode_scalar(source, value)
    if isinstance(value, SequenceItem):
        return view_for_value(source, value.value)
    raise TypeError(f"unexpected CST value node: {type(value)!r}")
