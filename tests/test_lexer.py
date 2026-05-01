"""Tests for the Relic lexer."""

from relic.lexer import tokenize
from relic.ast_nodes import TokenType


def test_simple_tokens():
    tokens = tokenize('figure "Hello" [width: 10cm]:')
    types = [t.type for t in tokens]
    assert TokenType.IDENT in types
    assert TokenType.STRING in types
    assert TokenType.COLON in types


def test_string():
    tokens = tokenize('"Hello World"')
    assert tokens[0].type == TokenType.STRING
    assert tokens[0].value == "Hello World"


def test_number_with_unit():
    tokens = tokenize("25mm")
    assert tokens[0].type == TokenType.NUMBER
    assert tokens[0].value == "25"
    assert tokens[1].type == TokenType.UNIT
    assert tokens[1].value == "mm"


def test_arrow():
    tokens = tokenize("A -> B")
    assert any(t.type == TokenType.ARROW for t in tokens)


def test_indentation():
    src = "A:\n  B\n  C\nD"
    tokens = tokenize(src)
    types = [t.type for t in tokens]
    assert TokenType.INDENT in types
    assert TokenType.DEDENT in types


def test_brackets():
    tokens = tokenize("[box, label: 'hi']")
    types = [t.type for t in tokens]
    assert TokenType.LBRACKET in types
    assert TokenType.RBRACKET in types


def test_operators():
    tokens = tokenize("x = y + 5mm")
    types = [t.type for t in tokens]
    assert TokenType.EQUALS in types
    assert TokenType.PLUS in types


def test_empty_input():
    tokens = tokenize("")
    assert tokens[-1].type == TokenType.EOF


def test_comment():
    tokens = tokenize("A # this is a comment\nB")
    assert all(t.value != "#" or t.type == TokenType.UNIT for t in tokens)
    # Comments should be skipped


def test_number_cm():
    tokens = tokenize("14cm")
    assert tokens[0].value == "14"
    assert tokens[1].value == "cm"


def test_dot():
    tokens = tokenize("A.left")
    assert tokens[0].type == TokenType.IDENT
    assert tokens[0].value == "A"
    assert tokens[1].type == TokenType.DOT
    assert tokens[2].type == TokenType.IDENT
    assert tokens[2].value == "left"
