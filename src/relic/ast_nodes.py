"""AST node definitions for Relic."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class TokenType(Enum):
    IDENT = auto()
    STRING = auto()
    NUMBER = auto()
    UNIT = auto()  # mm, cm, pt, %
    COLON = auto()
    DOT = auto()
    ARROW = auto()  # ->
    LBRACKET = auto()
    RBRACKET = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    EQUALS = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int = 0
    col: int = 0


# --- AST Nodes ---


@dataclass
class AnchorRef:
    """Reference to an object's anchor: ObjectName.anchor"""
    object_name: str
    anchor: str  # left, right, top, bottom, center, center-x, center-y, width, height


@dataclass
class ConstraintExpr:
    """A constraint expression: target.anchor = source.anchor [+ offset]"""
    target: AnchorRef
    source: AnchorRef
    offset: float = 0.0
    offset_unit: str = "mm"  # mm, cm, pt


@dataclass
class PropertyPair:
    """Key: value pair in brackets."""
    key: str
    value: str | float


@dataclass
class ObjectDecl:
    """Object declaration: Name [type, key: val, ...]"""
    name: str
    obj_type: str = "box"  # box, circle, diamond, etc.
    properties: list[PropertyPair] = field(default_factory=list)
    children: list[ObjectDecl | ContainerDecl | ArrowDecl | ConstraintExpr] = field(default_factory=list)
    line: int = 0


@dataclass
class ContainerDecl:
    """Container: container Name [layout, key: val, ...]: children"""
    name: str
    layout: str = "flow-v"  # flow-v, flow-h, grid
    properties: list[PropertyPair] = field(default_factory=list)
    children: list[ObjectDecl | ContainerDecl | ArrowDecl | ConstraintExpr] = field(default_factory=list)
    line: int = 0


@dataclass
class ArrowDecl:
    """Arrow: arrow Src -> Tgt [style, label: '...']"""
    source: str
    target: str
    style: str = ""  # solid, dashed, dotted
    label: str = ""
    route: str = ""  # bezier, orthogonal, or "" (default straight)
    label_pos: float = 0.5  # 0.0=near source, 0.5=midpoint, 1.0=near target
    properties: list[PropertyPair] = field(default_factory=list)
    line: int = 0


@dataclass
class CalloutStmt:
    """Callout: callout Source -> Target [style: dashed, fill: gray!5]"""
    source: str
    target: str
    style: str = "dashed"
    fill: str = "gray!5"
    line: int = 0


@dataclass
class FigureDecl:
    """Top-level figure declaration."""
    name: str
    properties: list[PropertyPair] = field(default_factory=list)
    children: list[ObjectDecl | ContainerDecl | ArrowDecl | ConstraintExpr] = field(default_factory=list)
    line: int = 0
