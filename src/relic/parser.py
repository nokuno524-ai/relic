"""Parser for Relic — builds AST from token stream."""

from __future__ import annotations

from .ast_nodes import (
    ArrowDecl, ContainerDecl, ConstraintExpr, FigureDecl,
    ObjectDecl, PropertyPair, AnchorRef, Token, TokenType,
)
from .errors import ParseError


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else self.tokens[-1]

    def advance(self) -> Token:
        t = self.peek()
        self.pos += 1
        return t

    def expect(self, tt: TokenType) -> Token:
        t = self.advance()
        if t.type != tt:
            raise ParseError(f"Expected {tt.name}, got {t.type.name} ({t.value!r})", t.line)
        return t

    def skip_newlines(self):
        while self.peek().type == TokenType.NEWLINE:
            self.advance()

    def parse(self) -> FigureDecl:
        self.skip_newlines()
        return self._parse_figure()

    def _parse_figure(self) -> FigureDecl:
        tok = self.expect(TokenType.IDENT)
        if tok.value != "figure":
            raise ParseError(f"Expected 'figure', got {tok.value!r}", tok.line)
        name_tok = self.expect(TokenType.STRING)
        props = self._parse_bracket_props() if self.peek().type == TokenType.LBRACKET else []
        self.expect(TokenType.COLON)
        self.expect(TokenType.NEWLINE)
        children = []
        if self.peek().type == TokenType.INDENT:
            self.advance()
            children = self._parse_block()
        return FigureDecl(name=name_tok.value, properties=props, children=children, line=tok.line)

    def _parse_block(self) -> list:
        items: list = []
        while self.peek().type not in (TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.peek().type in (TokenType.DEDENT, TokenType.EOF):
                break
            item = self._parse_statement()
            if item is not None:
                items.append(item)
            # consume trailing newline
            if self.peek().type == TokenType.NEWLINE:
                self.advance()
        # consume DEDENT
        if self.peek().type == TokenType.DEDENT:
            self.advance()
        return items

    def _parse_statement(self):
        tok = self.peek()
        if tok.type == TokenType.IDENT:
            if tok.value in ("container", "panel", "grid"):
                return self._parse_container()
            elif tok.value == "arrow":
                return self._parse_arrow()
            else:
                return self._parse_object_or_constraint()
        return None

    def _parse_container(self) -> ContainerDecl:
        kind_tok = self.advance()
        name_tok = self.expect(TokenType.IDENT)
        props = self._parse_bracket_props() if self.peek().type == TokenType.LBRACKET else []
        layout = "flow-v"
        remaining_props = []
        for p in props:
            if p.key == "layout":
                layout = p.value
            else:
                remaining_props.append(p)
        # Layout can also be the first positional prop or from keywords like flow-v
        # Check if first prop value is a layout type
        if props and props[0].key in ("flow-v", "flow-h", "grid"):
            layout = props[0].key
            remaining_props = props[1:]

        self.expect(TokenType.COLON)
        self.expect(TokenType.NEWLINE)
        children = []
        if self.peek().type == TokenType.INDENT:
            self.advance()
            children = self._parse_block()
        return ContainerDecl(
            name=name_tok.value, layout=layout,
            properties=remaining_props, children=children, line=kind_tok.line,
        )

    def _parse_arrow(self) -> ArrowDecl:
        self.advance()  # consume 'arrow'
        src_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.ARROW)
        tgt_tok = self.expect(TokenType.IDENT)
        props = self._parse_bracket_props() if self.peek().type == TokenType.LBRACKET else []
        style = ""
        label = ""
        route = ""
        label_pos = 0.5
        for p in props:
            if p.key == "style":
                style = str(p.value)
            elif p.key == "label":
                label = str(p.value)
            elif p.key in ("dashed", "dotted", "solid"):
                style = p.key
            elif p.key in ("bezier", "orthogonal"):
                route = p.key
            elif p.key == "label-pos":
                label_pos = float(p.value) if isinstance(p.value, (int, float)) else float(str(p.value))
        return ArrowDecl(source=src_tok.value, target=tgt_tok.value, style=style, label=label, route=route, label_pos=label_pos, properties=props, line=src_tok.line)

    def _parse_object_or_constraint(self) -> ObjectDecl | ConstraintExpr:
        """Parse either an object declaration or a constraint assignment."""
        # Lookahead: Name.prop = ... is a constraint, Name [ is an object
        name_tok = self.advance()
        if self.peek().type == TokenType.DOT:
            # Constraint: Name.anchor = Source.anchor [+ offset]
            return self._parse_constraint(name_tok.value)
        # Object declaration: Name [type, props...]
        return self._parse_object(name_tok.value, name_tok.line)

    def _parse_constraint(self, target_name: str) -> ConstraintExpr:
        self.expect(TokenType.DOT)
        anchor_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.EQUALS)
        src_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.DOT)
        src_anchor_tok = self.expect(TokenType.IDENT)
        offset = 0.0
        offset_unit = "mm"
        if self.peek().type in (TokenType.PLUS, TokenType.MINUS):
            sign = 1.0 if self.advance().type == TokenType.PLUS else -1.0
            num_tok = self.expect(TokenType.NUMBER)
            offset = sign * float(num_tok.value)
            if self.peek().type == TokenType.UNIT:
                offset_unit = self.advance().value
        return ConstraintExpr(
            target=AnchorRef(target_name, anchor_tok.value),
            source=AnchorRef(src_tok.value, src_anchor_tok.value),
            offset=offset,
            offset_unit=offset_unit,
        )

    def _parse_object(self, name: str, line: int) -> ObjectDecl:
        props = self._parse_bracket_props()
        obj_type = "box"
        remaining_props = []
        for p in props:
            if p.key in ("box", "circle", "diamond", "ellipse", "image",
                         "add", "multiply", "concat", "softmax", "dropout"):
                obj_type = p.key
            else:
                remaining_props.append(p)
        # Check for children (colon + indent)
        children = []
        if self.peek().type == TokenType.COLON:
            self.advance()
            self.expect(TokenType.NEWLINE)
            self.expect(TokenType.INDENT)
            children = self._parse_block()
        return ObjectDecl(name=name, obj_type=obj_type, properties=remaining_props, children=children, line=line)

    def _parse_bracket_props(self) -> list[PropertyPair]:
        if self.peek().type != TokenType.LBRACKET:
            return []
        self.advance()  # [
        props: list[PropertyPair] = []
        while self.peek().type != TokenType.RBRACKET:
            if self.peek().type == TokenType.COMMA:
                self.advance()
                continue
            # key or positional value
            tok = self.advance()
            if tok.type == TokenType.IDENT:
                key = tok.value
                if self.peek().type == TokenType.COLON:
                    self.advance()
                    val = self._parse_value()
                    props.append(PropertyPair(key=key, value=val))
                else:
                    # positional: treat as key=value where key=value (e.g., "dashed", "flow-v")
                    props.append(PropertyPair(key=key, value=True))
            elif tok.type == TokenType.STRING:
                props.append(PropertyPair(key=tok.value, value=tok.value))
            elif tok.type == TokenType.NUMBER:
                val = tok.value
                props.append(PropertyPair(key=f"_num_{len(props)}", value=float(val)))
            else:
                break
        self.expect(TokenType.RBRACKET)
        return props

    def _parse_value(self) -> str | float:
        tok = self.peek()
        if tok.type == TokenType.STRING:
            self.advance()
            return tok.value
        if tok.type == TokenType.NUMBER:
            self.advance()
            val = float(tok.value)
            if self.peek().type == TokenType.UNIT:
                unit = self.advance().value
                return f"{tok.value}{unit}"
            return val
        if tok.type == TokenType.IDENT:
            self.advance()
            # Could be something like "accent-blue!20"
            val = tok.value
            while self.peek().type == TokenType.IDENT and self.peek().value.startswith("!"):
                val += self.advance().value
            # Handle IDENT-dashed-ident patterns: look for color!N patterns
            return val
        raise ParseError(f"Expected value, got {tok.type.name}", tok.line)


def parse(tokens: list[Token]) -> FigureDecl:
    return Parser(tokens).parse()
