"""YAML 1.2 lexical analysis — flat tokens with source spans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TokenKind(StrEnum):
    """Flat token kinds for block / flow YAML (v0.1 subset)."""

    NEWLINE = "NEWLINE"
    WHITESPACE = "WHITESPACE"
    COMMENT = "COMMENT"

    INDENT = "INDENT"
    DEDENT = "DEDENT"

    DOCUMENT_START = "DOCUMENT_START"

    LIST_ENTRY = "LIST_ENTRY"
    COLON = "COLON"
    QUESTION = "QUESTION"

    FLOW_SEQ_START = "FLOW_SEQ_START"
    FLOW_SEQ_END = "FLOW_SEQ_END"
    FLOW_MAP_START = "FLOW_MAP_START"
    FLOW_MAP_END = "FLOW_MAP_END"
    COMMA = "COMMA"

    BLOCK_SCALAR_HEADER = "BLOCK_SCALAR_HEADER"

    PLAIN_SCALAR = "PLAIN_SCALAR"

    DOUBLE_QUOTE = "DOUBLE_QUOTE"
    DOUBLE_QUOTED_CONTENT = "DOUBLE_QUOTED_CONTENT"

    SINGLE_QUOTE = "SINGLE_QUOTE"
    SINGLE_QUOTED_CONTENT = "SINGLE_QUOTED_CONTENT"

    BLOCK_SCALAR_LINE = "BLOCK_SCALAR_LINE"


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class TokenStream:
    source: str
    tokens: tuple[Token, ...]


def tokenize(source: str) -> TokenStream:
    """Tokenize a single YAML document source without raising."""
    lexer = _Lexer(source)
    lexer.run()
    return TokenStream(source=source, tokens=tuple(lexer.tokens))


def reconstruct(source: str, stream: TokenStream) -> str:
    """Concatenate token spans; equals *source* when lexing is consistent."""
    return "".join(source[t.start : t.end] for t in stream.tokens)


class _Lexer:
    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.pos = 0
        self.tokens: list[Token] = []
        self.indent_stack: list[int] = [0]
        self.flow_depth = 0
        self.in_block_scalar = False
        self.block_scalar_min_column: int | None = None

    def _emit(self, kind: TokenKind, start: int, end: int) -> None:
        self.tokens.append(Token(kind, start, end))

    def _emit_zero(self, kind: TokenKind, at: int) -> None:
        self._emit(kind, at, at)

    def _peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        if i >= self.length:
            return ""
        return self.source[i]

    def _advance(self, n: int = 1) -> None:
        self.pos += n

    def run(self) -> None:
        if self.length == 0:
            return
        while self.pos < self.length:
            if self._at_line_begin():
                self._line_begin()
            else:
                self._token_at_cursor()

        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self._emit_zero(TokenKind.DEDENT, self.length)

    def _at_line_begin(self) -> bool:
        if self.pos == 0:
            return True
        prev = self.source[self.pos - 1]
        return prev in "\r\n"

    def _consume_newline(self) -> None:
        start = self.pos
        if self.source[self.pos : self.pos + 2] == "\r\n":
            self._advance(2)
        elif self._peek() in "\r\n":
            self._advance(1)
        else:
            return
        self._emit(TokenKind.NEWLINE, start, self.pos)

    def _column_width(self, start: int, end: int) -> int:
        col = 0
        for i in range(start, end):
            if self.source[i] == "\t":
                col += 8 - (col % 8)
            else:
                col += 1
        return col

    def _read_horizontal_whitespace(self) -> tuple[int, int] | None:
        start = self.pos
        while self.pos < self.length and self.source[self.pos] in " \t":
            self.pos += 1
        if self.pos == start:
            return None
        return start, self.pos

    def _line_begin(self) -> None:
        if self.in_block_scalar:
            self._block_scalar_line()
            return

        if self._peek() in "\r\n":
            self._consume_newline()
            return

        indent_span = self._read_horizontal_whitespace()
        line_start = self.pos

        if self._peek() in "\r\n" or self._peek() == "":
            if indent_span:
                self._emit(TokenKind.WHITESPACE, indent_span[0], indent_span[1])
            self._consume_newline()
            return

        if self.flow_depth == 0:
            indent_end = indent_span[1] if indent_span else line_start
            column = (
                self._column_width(indent_span[0], indent_span[1])
                if indent_span
                else self._column_width(0, 0)
            )
            if indent_span:
                self._emit(TokenKind.WHITESPACE, indent_span[0], indent_span[1])
            self._adjust_indent(column, indent_end)
        elif indent_span:
            self._emit(TokenKind.WHITESPACE, indent_span[0], indent_span[1])

        self._token_at_cursor()

    def _adjust_indent(self, column: int, at: int) -> None:
        if column > self.indent_stack[-1]:
            self.indent_stack.append(column)
            self._emit_zero(TokenKind.INDENT, at)
            return
        while column < self.indent_stack[-1]:
            self.indent_stack.pop()
            self._emit_zero(TokenKind.DEDENT, at)
        if column > self.indent_stack[-1]:
            self.indent_stack.append(column)
            self._emit_zero(TokenKind.INDENT, at)

    def _line_content_column(self, start: int, end: int) -> tuple[int, int]:
        """Return (indent column, index after indent) for a line slice."""
        i = start
        col = 0
        while i < end and self.source[i] in " \t":
            if self.source[i] == "\t":
                col += 8 - (col % 8)
            else:
                col += 1
            i += 1
        return col, i

    def _block_scalar_line(self) -> None:
        line_start = self.pos
        line_end = line_start
        while line_end < self.length and self.source[line_end] not in "\r\n":
            line_end += 1

        column, content_at = self._line_content_column(line_start, line_end)
        has_content = content_at < line_end

        if (
            self.block_scalar_min_column is not None
            and has_content
            and column < self.block_scalar_min_column
        ):
            self.in_block_scalar = False
            self.block_scalar_min_column = None
            self.pos = line_start
            self._line_begin()
            return

        if self.block_scalar_min_column is None and has_content:
            self.block_scalar_min_column = column

        self._emit(TokenKind.BLOCK_SCALAR_LINE, line_start, line_end)
        self.pos = line_end
        if self._peek() in "\r\n":
            self._consume_newline()

    def _token_at_cursor(self) -> None:
        if self.pos >= self.length:
            return

        ch = self._peek()
        if ch in "\r\n":
            self._consume_newline()
            return

        if ch == "#":
            self._read_comment()
            return

        ws = self._read_horizontal_whitespace()
        if ws:
            self._emit(TokenKind.WHITESPACE, ws[0], ws[1])
            return

        if ch == "-":
            if self._is_document_start():
                self._read_document_start()
            elif self._is_list_entry():
                self._emit(TokenKind.LIST_ENTRY, self.pos, self.pos + 1)
                self._advance(1)
            else:
                self._read_plain_scalar()
            return

        if ch == ":":
            self._emit(TokenKind.COLON, self.pos, self.pos + 1)
            self._advance(1)
            return

        if ch == "?":
            self._emit(TokenKind.QUESTION, self.pos, self.pos + 1)
            self._advance(1)
            return

        if ch == "[":
            self.flow_depth += 1
            self._emit(TokenKind.FLOW_SEQ_START, self.pos, self.pos + 1)
            self._advance(1)
            return

        if ch == "]":
            self.flow_depth = max(0, self.flow_depth - 1)
            self._emit(TokenKind.FLOW_SEQ_END, self.pos, self.pos + 1)
            self._advance(1)
            return

        if ch == "{":
            self.flow_depth += 1
            self._emit(TokenKind.FLOW_MAP_START, self.pos, self.pos + 1)
            self._advance(1)
            return

        if ch == "}":
            self.flow_depth = max(0, self.flow_depth - 1)
            self._emit(TokenKind.FLOW_MAP_END, self.pos, self.pos + 1)
            self._advance(1)
            return

        if ch == ",":
            self._emit(TokenKind.COMMA, self.pos, self.pos + 1)
            self._advance(1)
            return

        if ch in "|>":
            self._read_block_scalar_header()
            return

        if ch == '"':
            self._read_double_quoted()
            return

        if ch == "'":
            self._read_single_quoted()
            return

        self._read_plain_scalar()

    def _is_document_start(self) -> bool:
        return self.source[self.pos : self.pos + 3] == "---" and (
            self.pos + 3 >= self.length or self.source[self.pos + 3] in " \t\r\n#"
        )

    def _read_document_start(self) -> None:
        start = self.pos
        self._advance(3)
        self._emit(TokenKind.DOCUMENT_START, start, self.pos)

    def _is_list_entry(self) -> bool:
        if self.flow_depth > 0:
            return False
        if self.source[self.pos : self.pos + 1] != "-":
            return False
        nxt = self._peek(1)
        return nxt in " \t\r\n#" or nxt == ""

    def _read_comment(self) -> None:
        start = self.pos
        while self.pos < self.length and self.source[self.pos] not in "\r\n":
            self.pos += 1
        self._emit(TokenKind.COMMENT, start, self.pos)

    def _read_block_scalar_header(self) -> None:
        start = self.pos
        self._advance(1)
        while self.pos < self.length and self.source[self.pos] in "+-0123456789":
            self.pos += 1
        while self.pos < self.length and self.source[self.pos] in " \t":
            self.pos += 1
        self._emit(TokenKind.BLOCK_SCALAR_HEADER, start, self.pos)
        if self._peek() in "\r\n":
            self._consume_newline()
            self.in_block_scalar = True
            self.block_scalar_min_column = None

    def _read_double_quoted(self) -> None:
        open_start = self.pos
        self._advance(1)
        self._emit(TokenKind.DOUBLE_QUOTE, open_start, self.pos)
        content_start = self.pos
        while self.pos < self.length:
            ch = self._peek()
            if ch == "\\":
                self._advance(2)
                continue
            if ch == '"':
                if content_start < self.pos:
                    self._emit(TokenKind.DOUBLE_QUOTED_CONTENT, content_start, self.pos)
                close_start = self.pos
                self._advance(1)
                self._emit(TokenKind.DOUBLE_QUOTE, close_start, self.pos)
                return
            self._advance(1)
        if content_start < self.pos:
            self._emit(TokenKind.DOUBLE_QUOTED_CONTENT, content_start, self.pos)

    def _read_single_quoted(self) -> None:
        open_start = self.pos
        self._advance(1)
        self._emit(TokenKind.SINGLE_QUOTE, open_start, self.pos)
        content_start = self.pos
        while self.pos < self.length:
            if self._peek() == "'":
                if self._peek(1) == "'":
                    self._advance(2)
                    continue
                if content_start < self.pos:
                    self._emit(TokenKind.SINGLE_QUOTED_CONTENT, content_start, self.pos)
                close_start = self.pos
                self._advance(1)
                self._emit(TokenKind.SINGLE_QUOTE, close_start, self.pos)
                return
            self._advance(1)
        if content_start < self.pos:
            self._emit(TokenKind.SINGLE_QUOTED_CONTENT, content_start, self.pos)

    def _read_plain_scalar(self) -> None:
        start = self.pos
        in_flow = self.flow_depth > 0
        while self.pos < self.length:
            ch = self.source[self.pos]
            if ch in "\r\n":
                break
            if ch == "#" and (self.pos == start or self.source[self.pos - 1] in " \t"):
                break
            if not in_flow:
                if ch == ":":
                    nxt = self._peek(1)
                    if nxt in " \t\r\n#" or nxt == "":
                        break
                if ch == "-" and self.pos == start and self._is_list_entry():
                    break
            else:
                if ch in ",]}:":
                    break
            if ch in "[]{}," and in_flow:
                break
            if ch in " \t":
                if in_flow:
                    break
                nxt = self._peek(1)
                if nxt in "\r\n#":
                    break
            self._advance(1)
        if self.pos > start:
            self._emit(TokenKind.PLAIN_SCALAR, start, self.pos)
