"""Lexer/tokenizer for Relic source."""

from __future__ import annotations

from .ast_nodes import Token, TokenType
from .errors import LexError

_KEYWORDS = {"figure", "container", "panel", "grid", "arrow", "positioned"}
_UNITS = {"mm", "cm", "pt", "%"}


def _strip_comments(source: str) -> str:
    """Remove // line comments and /* */ block comments from source."""
    result: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        # Block comment
        if i + 1 < n and source[i] == '/' and source[i + 1] == '*':
            i += 2
            while i + 1 < n and not (source[i] == '*' and source[i + 1] == '/'):
                if source[i] == '\n':
                    result.append('\n')  # preserve line breaks for indent tracking
                i += 1
            i += 2  # skip */
            continue
        # Line comment
        if i + 1 < n and source[i] == '/' and source[i + 1] == '/':
            while i < n and source[i] != '\n':
                i += 1
            continue
        result.append(source[i])
        i += 1
    return ''.join(result)


def tokenize(source: str) -> list[Token]:
    """Tokenize Relic source into a list of tokens."""
    tokens: list[Token] = []
    source = _strip_comments(source)
    lines = source.split("\n")
    indent_stack: list[int] = [0]

    for lineno, line_text in enumerate(lines, 1):
        # Skip blank lines and comments
        stripped = line_text.rstrip()
        if not stripped:
            continue

        # Compute indent
        indent = len(stripped) - len(stripped.lstrip())
        if indent > indent_stack[-1]:
            indent_stack.append(indent)
            tokens.append(Token(TokenType.INDENT, "", lineno, 0))
        while indent < indent_stack[-1]:
            indent_stack.pop()
            tokens.append(Token(TokenType.DEDENT, "", lineno, 0))

        col = indent
        i = indent
        s = stripped

        while i < len(s):
            c = s[i]

            # Skip whitespace
            if c in " \t":
                i += 1
                continue

            # Comment
            if c == "#":
                break

            # String literal (double or single quotes)
            if c in '"':
                quote = c
                j = i + 1
                while j < len(s) and s[j] != quote:
                    if s[j] == "\\":
                        j += 1
                    j += 1
                if j >= len(s):
                    raise LexError("Unterminated string", lineno, i)
                tokens.append(Token(TokenType.STRING, s[i + 1 : j], lineno, i))
                i = j + 1
                continue
            if c == "'":
                j = i + 1
                while j < len(s) and s[j] != "'":
                    j += 1
                tokens.append(Token(TokenType.STRING, s[i + 1 : j], lineno, i))
                i = j + 1
                continue

            # Arrow ->
            if c == "-" and i + 1 < len(s) and s[i + 1] == ">":
                tokens.append(Token(TokenType.ARROW, "->", lineno, i))
                i += 2
                continue

            # Number (with optional unit)
            if c.isdigit() or (c == "." and i + 1 < len(s) and s[i + 1].isdigit()):
                j = i
                while j < len(s) and (s[j].isdigit() or s[j] == "."):
                    j += 1
                num_str = s[i:j]
                # Check for unit
                k = j
                while k < len(s) and s[k].isalpha():
                    k += 1
                unit_str = s[j:k]
                if unit_str in _UNITS:
                    tokens.append(Token(TokenType.NUMBER, num_str, lineno, i))
                    tokens.append(Token(TokenType.UNIT, unit_str, lineno, j))
                    i = k
                elif unit_str == "" or unit_str.startswith("e") or unit_str.startswith("E"):
                    # Could be scientific notation or just a number
                    tokens.append(Token(TokenType.NUMBER, num_str, lineno, i))
                    i = j
                else:
                    tokens.append(Token(TokenType.NUMBER, num_str, lineno, i))
                    i = j
                continue

            # Identifier / keyword
            if c.isalpha() or c == "_":
                j = i
                while j < len(s) and (s[j].isalnum() or s[j] == "_" or s[j] == "-"):
                    j += 1
                word = s[i:j]
                tokens.append(Token(TokenType.IDENT, word, lineno, i))
                i = j
                continue

            # Percent as unit
            if c == "%":
                tokens.append(Token(TokenType.UNIT, "%", lineno, i))
                i += 1
                continue

            # Single-char tokens
            simple = {
                ":": TokenType.COLON,
                ".": TokenType.DOT,
                "[": TokenType.LBRACKET,
                "]": TokenType.RBRACKET,
                "(": TokenType.LPAREN,
                ")": TokenType.RPAREN,
                ",": TokenType.COMMA,
                "=": TokenType.EQUALS,
                "+": TokenType.PLUS,
                "-": TokenType.MINUS,
                "*": TokenType.STAR,
            }
            if c in simple:
                tokens.append(Token(simple[c], c, lineno, i))
                i += 1
                continue

            raise LexError(f"Unexpected character: {c!r}", lineno, i)

        tokens.append(Token(TokenType.NEWLINE, "\n", lineno, len(s)))

    # Close remaining indents
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token(TokenType.DEDENT, "", lineno if lines else 0, 0))

    tokens.append(Token(TokenType.EOF, "", len(lines), 0))
    return tokens
