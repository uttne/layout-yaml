"""Lexer unit tests — kinds, spans, and full source reconstruction."""

from __future__ import annotations

from layout_yaml.lexer import TokenKind, reconstruct, tokenize


def test_empty_source() -> None:
    stream = tokenize("")
    assert stream.tokens == ()


def test_reconstruct_simple_mapping() -> None:
    source = "key: value\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    kinds = [t.kind for t in stream.tokens]
    assert TokenKind.PLAIN_SCALAR in kinds
    assert TokenKind.COLON in kinds
    assert TokenKind.NEWLINE in kinds


def test_comment_only_line() -> None:
    source = "# standalone\nnext: 1\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    comment = next(t for t in stream.tokens if t.kind == TokenKind.COMMENT)
    assert source[comment.start : comment.end] == "# standalone"


def test_end_of_line_comment() -> None:
    source = "name: demo  # trailing\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    comments = [t for t in stream.tokens if t.kind == TokenKind.COMMENT]
    assert len(comments) == 1
    assert source[comments[0].start : comments[0].end] == "# trailing"


def test_tab_indent_and_block_list() -> None:
    source = "root:\n\t- item\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    assert any(t.kind == TokenKind.INDENT for t in stream.tokens)
    assert any(t.kind == TokenKind.LIST_ENTRY for t in stream.tokens)
    ws = next(t for t in stream.tokens if t.kind == TokenKind.WHITESPACE)
    assert "\t" in source[ws.start : ws.end]


def test_flow_sequence_nested() -> None:
    source = "items: [a, [b, c]]\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    kinds = [t.kind for t in stream.tokens]
    assert kinds.count(TokenKind.FLOW_SEQ_START) == 2
    assert kinds.count(TokenKind.FLOW_SEQ_END) == 2
    assert kinds.count(TokenKind.COMMA) == 2


def test_double_quoted_splits() -> None:
    source = 'msg: "hello"\n'
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    quotes = [t for t in stream.tokens if t.kind == TokenKind.DOUBLE_QUOTE]
    assert len(quotes) == 2
    content = next(
        t for t in stream.tokens if t.kind == TokenKind.DOUBLE_QUOTED_CONTENT
    )
    assert source[content.start : content.end] == "hello"


def test_single_quoted_doubled_quote() -> None:
    source = "x: 'it''s fine'\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    content = next(
        t for t in stream.tokens if t.kind == TokenKind.SINGLE_QUOTED_CONTENT
    )
    assert source[content.start : content.end] == "it''s fine"


def test_unclosed_double_quote_no_extra_tokens() -> None:
    source = 'open: "no close\nstill: plain\n'
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    quotes = [t for t in stream.tokens if t.kind == TokenKind.DOUBLE_QUOTE]
    assert len(quotes) == 1
    assert any(t.kind == TokenKind.DOUBLE_QUOTED_CONTENT for t in stream.tokens)


def test_block_scalar_lines() -> None:
    source = "readme: |\n  line one\n  line two\nversion: 1\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    lines = [t for t in stream.tokens if t.kind == TokenKind.BLOCK_SCALAR_LINE]
    assert len(lines) == 2
    assert any(t.kind == TokenKind.BLOCK_SCALAR_HEADER for t in stream.tokens)


def test_document_start() -> None:
    source = "---\nkey: 1\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    doc = next(t for t in stream.tokens if t.kind == TokenKind.DOCUMENT_START)
    assert source[doc.start : doc.end] == "---"


def test_indent_dedent_zero_width() -> None:
    source = "a:\n  b: 1\n"
    stream = tokenize(source)
    assert reconstruct(source, stream) == source
    indents = [t for t in stream.tokens if t.kind == TokenKind.INDENT]
    dedents = [t for t in stream.tokens if t.kind == TokenKind.DEDENT]
    assert indents
    assert dedents
    for t in indents + dedents:
        assert t.start == t.end
