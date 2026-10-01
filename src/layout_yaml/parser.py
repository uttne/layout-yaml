"""Build CST from lexer tokens."""

from __future__ import annotations

from layout_yaml.cst import (
    BlockMapping,
    BlockSequence,
    Document,
    DoubleQuotedScalar,
    MappingEntry,
    PlainScalar,
    ScalarNode,
    SequenceItem,
    SingleQuotedScalar,
)
from layout_yaml.errors import ParseError, UnsupportedError
from layout_yaml.lexer import Token, TokenKind, TokenStream


def parse_document(stream: TokenStream) -> Document:
    return _Parser(stream).parse_document()


class _Parser:
    def __init__(self, stream: TokenStream) -> None:
        self.stream = stream
        self.source = stream.source
        self.tokens = stream.tokens
        self.pos = 0
        self.indent_depth = 0

    def parse_document(self) -> Document:
        doc_start = 0
        if self._peek_kind() == TokenKind.DOCUMENT_START:
            raise UnsupportedError("multiple documents are not supported")
        preamble_end = self._skip_preamble()
        if self._at_end():
            mapping = BlockMapping(preamble_end, preamble_end, ())
        else:
            mapping = self._parse_block_mapping(preamble_end)
        while not self._at_end() and self._peek_kind() == TokenKind.DEDENT:
            self._advance()
        doc_end = mapping.end if mapping.entries else preamble_end
        if not mapping.entries and not self._at_end():
            doc_end = self.tokens[-1].end
        elif mapping.entries:
            doc_end = max(doc_end, self._prev_end())
        if not self._at_end():
            self._error("unexpected tokens after document")
        return Document(doc_start, doc_end, preamble_end, mapping)

    def _skip_preamble(self) -> int:
        while not self._at_end():
            kind = self._peek_kind()
            if kind in (TokenKind.COMMENT, TokenKind.NEWLINE):
                self._advance()
                continue
            if kind == TokenKind.PLAIN_SCALAR and self._peek_ahead_colon():
                break
            if kind in (TokenKind.INDENT, TokenKind.DEDENT):
                self._error("unexpected indent in document preamble")
            self._error(f"unexpected token in preamble: {kind}")
        if self._at_end():
            return len(self.source)
        return self.tokens[self.pos].start

    def _peek_ahead_colon(self) -> bool:
        i = self.pos + 1
        while i < len(self.tokens):
            kind = self.tokens[i].kind
            if kind == TokenKind.COLON:
                return True
            if kind in (TokenKind.NEWLINE, TokenKind.COMMENT, TokenKind.WHITESPACE):
                i += 1
                continue
            return False
        return False

    def _parse_block_mapping(self, span_start: int) -> BlockMapping:
        entries: list[MappingEntry] = []
        while self._mapping_entry_ahead():
            entries.append(self._parse_mapping_entry())
        end = entries[-1].end if entries else span_start
        return BlockMapping(span_start, end, tuple(entries))

    def _mapping_entry_ahead(self) -> bool:
        if self._at_end():
            return False
        kind = self._peek_kind()
        if kind == TokenKind.DEDENT:
            return False
        if kind == TokenKind.COMMENT:
            return True
        if kind == TokenKind.PLAIN_SCALAR:
            return True
        return False

    def _parse_mapping_entry(self) -> MappingEntry:
        entry_start = self._current_start()
        self._consume_entry_leading()
        entry_start = min(entry_start, self._current_start())
        key = self._parse_key_scalar()
        self._expect(TokenKind.COLON)
        value = self._parse_value_after_colon()
        entry_end = self._consume_entry_trailing()
        return MappingEntry(entry_start, entry_end, key, value)

    def _consume_entry_leading(self) -> None:
        while self._peek_kind() == TokenKind.COMMENT:
            self._advance()
            if self._peek_kind() == TokenKind.NEWLINE:
                self._advance()

    def _parse_key_scalar(self) -> PlainScalar:
        token = self._expect(TokenKind.PLAIN_SCALAR)
        return PlainScalar(token.start, token.end)

    def _parse_value_after_colon(
        self,
    ) -> BlockMapping | BlockSequence | ScalarNode | None:
        if self._at_end():
            return None
        kind = self._peek_kind()
        if kind in (TokenKind.WHITESPACE, TokenKind.PLAIN_SCALAR, TokenKind.COMMENT):
            return self._parse_inline_scalar_value()
        if kind in (
            TokenKind.DOUBLE_QUOTE,
            TokenKind.SINGLE_QUOTE,
        ):
            return self._parse_quoted_scalar()
        if kind == TokenKind.NEWLINE:
            self._advance()
            return self._parse_block_value()
        if kind == TokenKind.INDENT:
            return self._parse_block_value()
        self._unsupported(f"value after colon: {kind}")

    def _parse_inline_scalar_value(self) -> ScalarNode:
        if self._peek_kind() == TokenKind.WHITESPACE:
            self._advance()
        if self._peek_kind() == TokenKind.PLAIN_SCALAR:
            token = self._expect(TokenKind.PLAIN_SCALAR)
            while self._peek_kind() == TokenKind.WHITESPACE:
                self._advance()
            if self._peek_kind() == TokenKind.NEWLINE:
                self._advance()
            return PlainScalar(token.start, token.end)
        if self._peek_kind() in (TokenKind.DOUBLE_QUOTE, TokenKind.SINGLE_QUOTE):
            return self._parse_quoted_scalar()
        self._error("expected inline scalar value")

    def _parse_quoted_scalar(self) -> ScalarNode:
        kind = self._peek_kind()
        if kind == TokenKind.DOUBLE_QUOTE:
            return self._parse_double_quoted()
        if kind == TokenKind.SINGLE_QUOTE:
            return self._parse_single_quoted()
        self._error("expected quoted scalar")

    def _parse_double_quoted(self) -> DoubleQuotedScalar:
        start = self._current_start()
        self._expect(TokenKind.DOUBLE_QUOTE)
        while (
            not self._at_end() and self._peek_kind() == TokenKind.DOUBLE_QUOTED_CONTENT
        ):
            self._advance()
        self._expect(TokenKind.DOUBLE_QUOTE)
        return DoubleQuotedScalar(start, self._prev_end())

    def _parse_single_quoted(self) -> SingleQuotedScalar:
        start = self._current_start()
        self._expect(TokenKind.SINGLE_QUOTE)
        while (
            not self._at_end() and self._peek_kind() == TokenKind.SINGLE_QUOTED_CONTENT
        ):
            self._advance()
        self._expect(TokenKind.SINGLE_QUOTE)
        return SingleQuotedScalar(start, self._prev_end())

    def _parse_block_value(
        self,
    ) -> BlockMapping | BlockSequence | ScalarNode | None:
        self._consume_blank_lines()
        if self._at_end() or self._peek_kind() == TokenKind.DEDENT:
            return None
        self._skip_indent_padding()
        if self._at_end() or self._peek_kind() == TokenKind.DEDENT:
            return None
        if self._peek_kind() == TokenKind.INDENT:
            self._advance()
            self.indent_depth += 1
            try:
                if self._peek_kind() == TokenKind.LIST_ENTRY:
                    return self._parse_block_sequence()
                return self._parse_block_mapping(self._current_start())
            finally:
                self._finish_indented_block()
        if self._peek_kind() == TokenKind.LIST_ENTRY:
            return self._parse_block_sequence()
        return None

    def _parse_block_sequence(self) -> BlockSequence:
        seq_start = self._current_start()
        items: list[SequenceItem] = []
        while True:
            self._skip_indent_padding()
            if self._at_end() or self._peek_kind() != TokenKind.LIST_ENTRY:
                break
            items.append(self._parse_sequence_item())
        seq_end = items[-1].end if items else seq_start
        return BlockSequence(seq_start, seq_end, tuple(items))

    def _parse_sequence_item(self) -> SequenceItem:
        item_start = self._current_start()
        self._expect(TokenKind.LIST_ENTRY)
        if self._peek_kind() == TokenKind.WHITESPACE:
            self._advance()
        if self._peek_kind() == TokenKind.PLAIN_SCALAR and not self._peek_ahead_colon():
            scalar = self._parse_plain_scalar_line()
            item_end = self._consume_sequence_item_trailing(scalar.end)
            return SequenceItem(item_start, item_end, scalar)
        if self._peek_kind() == TokenKind.INDENT:
            self._advance()
            self.indent_depth += 1
            try:
                if self._peek_kind() == TokenKind.LIST_ENTRY:
                    value: BlockMapping | BlockSequence | ScalarNode = (
                        self._parse_block_sequence()
                    )
                elif (
                    self._peek_kind() == TokenKind.PLAIN_SCALAR
                    and self._peek_ahead_colon()
                ):
                    value = self._parse_block_mapping(self._current_start())
                else:
                    self._error("expected nested block content after list entry")
            finally:
                self._finish_indented_block()
            item_end = value.end
            if self._peek_kind() == TokenKind.NEWLINE:
                self._advance()
                item_end = self._prev_end()
            return SequenceItem(item_start, item_end, value)
        self._error("expected value after list entry marker")

    def _parse_plain_scalar_line(self) -> PlainScalar:
        token = self._expect(TokenKind.PLAIN_SCALAR)
        return PlainScalar(token.start, token.end)

    def _consume_sequence_item_trailing(self, end: int) -> int:
        while not self._at_end():
            kind = self._peek_kind()
            if kind in (TokenKind.WHITESPACE, TokenKind.COMMENT, TokenKind.NEWLINE):
                self._advance()
                end = self._prev_end()
                if kind == TokenKind.NEWLINE:
                    break
                continue
            break
        return end

    def _consume_entry_trailing(self) -> int:
        end = self._prev_end()
        while not self._at_end():
            kind = self._peek_kind()
            if kind == TokenKind.DEDENT:
                break
            if kind == TokenKind.PLAIN_SCALAR and self._peek_ahead_colon():
                break
            if kind in (TokenKind.WHITESPACE, TokenKind.COMMENT, TokenKind.NEWLINE):
                self._advance()
                end = self._prev_end()
                continue
            break
        return end

    def _block_content_follows_after(self, index: int) -> bool:
        j = index
        while j < len(self.tokens) and self.tokens[j].kind == TokenKind.NEWLINE:
            j += 1
        while j < len(self.tokens) and self.tokens[j].kind == TokenKind.DEDENT:
            j += 1
        if j >= len(self.tokens):
            return False
        kind = self.tokens[j].kind
        if kind in (TokenKind.INDENT, TokenKind.LIST_ENTRY):
            return True
        if kind == TokenKind.WHITESPACE:
            k = j + 1
            while k < len(self.tokens) and self.tokens[k].kind == TokenKind.WHITESPACE:
                k += 1
            if k < len(self.tokens) and self.tokens[k].kind in (
                TokenKind.INDENT,
                TokenKind.LIST_ENTRY,
                TokenKind.PLAIN_SCALAR,
            ):
                return True
        return False

    def _colon_after(self, index: int) -> bool:
        j = index + 1
        while j < len(self.tokens):
            kind = self.tokens[j].kind
            if kind == TokenKind.COLON:
                return True
            if kind in (TokenKind.NEWLINE, TokenKind.COMMENT, TokenKind.WHITESPACE):
                j += 1
                continue
            return False
        return False

    def _consume_blank_lines(self) -> None:
        while self._peek_kind() == TokenKind.NEWLINE:
            if not self._block_content_follows_after(self.pos + 1):
                break
            self._advance()

    def _skip_indent_padding(self) -> None:
        while not self._at_end() and self._peek_kind() == TokenKind.WHITESPACE:
            self._advance()

    def _finish_indented_block(self) -> None:
        while not self._at_end():
            kind = self._peek_kind()
            if kind == TokenKind.NEWLINE:
                self._advance()
                continue
            if kind == TokenKind.DEDENT:
                self._advance()
                self.indent_depth = max(0, self.indent_depth - 1)
                break
            break

    def _peek_kind(self) -> TokenKind:
        if self._at_end():
            raise ParseError("unexpected end of input")
        return self.tokens[self.pos].kind

    def _current_start(self) -> int:
        if self._at_end():
            return len(self.source)
        return self.tokens[self.pos].start

    def _prev_end(self) -> int:
        if self.pos == 0:
            return 0
        return self.tokens[self.pos - 1].end

    def _at_end(self) -> bool:
        return self.pos >= len(self.tokens)

    def _advance(self) -> Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def _expect(self, kind: TokenKind) -> Token:
        if self._at_end():
            self._error(f"expected {kind}, got end of input")
        token = self.tokens[self.pos]
        if token.kind != kind:
            self._error(f"expected {kind}, got {token.kind}")
        self.pos += 1
        return token

    def _error(self, message: str) -> None:
        raise ParseError(message)

    def _unsupported(self, message: str) -> None:
        raise UnsupportedError(message)
