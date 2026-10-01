"""Decode scalar source spans to Python values (read path only)."""

from __future__ import annotations

import math

from layout_yaml.cst import (
    DoubleQuotedScalar,
    PlainScalar,
    ScalarNode,
    SingleQuotedScalar,
)
from layout_yaml.errors import ParseError


def plain_scalar_text(source: str, node: PlainScalar) -> str:
    return source[node.start : node.end]


def decode_scalar(source: str, node: ScalarNode) -> str | bool | int | float | None:
    if isinstance(node, PlainScalar):
        return _decode_plain(plain_scalar_text(source, node))
    if isinstance(node, DoubleQuotedScalar):
        return _decode_double_quoted(source[node.start : node.end])
    if isinstance(node, SingleQuotedScalar):
        return _decode_single_quoted(source[node.start : node.end])
    raise ParseError(f"unknown scalar node: {type(node)!r}")


def _decode_plain(text: str) -> str | bool | int | float | None:
    stripped = text.strip()
    if not stripped:
        return ""
    if stripped in ("null", "Null", "NULL", "~"):
        return None
    if stripped in ("true", "True", "TRUE"):
        return True
    if stripped in ("false", "False", "FALSE"):
        return False
    if _looks_like_int(stripped):
        try:
            return int(stripped, 0)
        except ValueError:
            pass
    if _looks_like_float(stripped):
        try:
            value = float(stripped)
        except ValueError:
            pass
        else:
            if math.isfinite(value):
                return value
    return text.rstrip()


def _looks_like_int(text: str) -> bool:
    if text[0] in "+-":
        body = text[1:]
    else:
        body = text
    if not body:
        return False
    if text.startswith(("0x", "0X", "+0x", "+0X", "-0x", "-0X")):
        return all(c in "0123456789abcdefABCDEF" for c in body[2:])
    if text.startswith(("0o", "0O", "+0o", "+0O", "-0o", "-0O")):
        return all(c in "01234567" for c in body[2:])
    if text.startswith(("0b", "0B", "+0b", "+0B", "-0b", "-0B")):
        return all(c in "01" for c in body[2:])
    return body.isdigit() or (
        body[0].isdigit() and all(c in "0123456789_" for c in body)
    )


def _looks_like_float(text: str) -> bool:
    return any(ch in text for ch in ".eE")


def _decode_double_quoted(span: str) -> str:
    if len(span) < 2 or span[0] != '"' or span[-1] != '"':
        raise ParseError("malformed double-quoted scalar")
    return _unescape_double(span[1:-1])


def _decode_single_quoted(span: str) -> str:
    if len(span) < 2 or span[0] != "'" or span[-1] != "'":
        raise ParseError("malformed single-quoted scalar")
    inner = span[1:-1]
    return inner.replace("''", "'")


def _unescape_double(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(text):
            raise ParseError("truncated escape in double-quoted scalar")
        esc = text[i]
        i += 1
        if esc == "n":
            out.append("\n")
        elif esc == "t":
            out.append("\t")
        elif esc == "r":
            out.append("\r")
        elif esc == "\\":
            out.append("\\")
        elif esc == '"':
            out.append('"')
        elif esc == "/":
            out.append("/")
        elif esc == " ":
            out.append(" ")
        elif esc == "0":
            out.append("\0")
        elif esc == "x" and i + 1 < len(text):
            hex_pair = text[i : i + 2]
            out.append(chr(int(hex_pair, 16)))
            i += 2
        elif esc == "u" and i + 3 < len(text):
            out.append(chr(int(text[i : i + 4], 16)))
            i += 4
        elif esc == "U" and i + 7 < len(text):
            out.append(chr(int(text[i : i + 8], 16)))
            i += 8
        else:
            out.append(esc)
    return "".join(out)
