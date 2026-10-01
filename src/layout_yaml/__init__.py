"""Layout-preserving YAML editor."""

from __future__ import annotations

from layout_yaml.api import Document
from layout_yaml.emit import emit_document
from layout_yaml.lexer import tokenize
from layout_yaml.parser import parse_document

__version__ = "0.0.0"


def loads(text: str) -> Document:
    """Parse YAML text into a layout-preserving document."""
    stream = tokenize(text)
    root = parse_document(stream)
    return Document(text, root)


def dumps(doc: Document) -> str:
    """Serialize a document back to YAML text."""
    return emit_document(doc._source, doc._root)
