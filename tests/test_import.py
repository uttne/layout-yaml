"""Smoke tests for package import."""

import layout_yaml


def test_import_layout_yaml() -> None:
    assert layout_yaml.__version__ == "0.0.0"
