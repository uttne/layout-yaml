#!/usr/bin/env python3
"""Lint Python in this directory tree.

The tree is the parent of scripts/, and the config is ruff.toml there.
Nothing outside that tree is checked. Copy scripts/check_py.py and ruff.toml
together into another repository.

    python .cursor/scripts/check_py.py

Ruff is resolved from the RUFF environment variable, then PATH, then uvx.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    config = root / "ruff.toml"
    if not config.is_file():
        print(f"Ruff config not found: {config}", file=sys.stderr)
        return 1

    command = [*ruff_command(), "check", "--config", str(config), str(root)]
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=root)
    return completed.returncode


def ruff_command() -> list[str]:
    override = os.environ.get("RUFF", "").strip()
    if override:
        return [override]
    found = shutil.which("ruff")
    if found:
        return [found]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "ruff"]
    uv = shutil.which("uv")
    if uv:
        return [uv, "tool", "run", "ruff"]
    print(
        "ruff was not found. Set RUFF, install ruff on PATH, or install uv.",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    sys.exit(main())
