"""Public exceptions for layout-yaml."""

from __future__ import annotations


class LayoutYamlError(Exception):
    """Base error for layout-yaml."""


class ParseError(LayoutYamlError):
    """Invalid or unexpected YAML structure."""


class UnsupportedError(LayoutYamlError):
    """Valid YAML construct that is not supported yet."""


class EditError(LayoutYamlError):
    """Failed to apply an edit to the document."""
