"""Tests for the Relic parser."""

import pytest
from relic.lexer import tokenize
from relic.parser import parse
from relic.ast_nodes import (
    ArrowDecl, ContainerDecl, ConstraintExpr, FigureDecl, ObjectDecl,
)


def _parse(src: str) -> FigureDecl:
    return parse(tokenize(src))


def test_parse_minimal():
    fig = _parse('figure "Test" []:')
    assert fig.name == "Test"


def test_parse_object():
    fig = _parse('figure "T" []:\n  A [box, label: "Hello"]')
    assert len(fig.children) == 1
    obj = fig.children[0]
    assert isinstance(obj, ObjectDecl)
    assert obj.name == "A"
    assert obj.obj_type == "box"


def test_parse_container():
    fig = _parse('figure "T" []:\n  container Enc [flow-v, gap: 6mm]:\n    X [box, label: "X"]')
    assert len(fig.children) == 1
    c = fig.children[0]
    assert isinstance(c, ContainerDecl)
    assert c.name == "Enc"
    assert c.layout == "flow-v"


def test_parse_constraint():
    fig = _parse('figure "T" []:\n  A [box]\n  B [box]\n  B.left = A.right + 25mm')
    constraints = [c for c in fig.children if isinstance(c, ConstraintExpr)]
    assert len(constraints) == 1
    c = constraints[0]
    assert c.target.object_name == "B"
    assert c.target.anchor == "left"
    assert c.source.object_name == "A"
    assert c.source.anchor == "right"
    assert c.offset == 25.0


def test_parse_arrow():
    fig = _parse('figure "T" []:\n  A [box]\n  B [box]\n  arrow A -> B [dashed, label: "hi"]')
    arrows = [c for c in fig.children if isinstance(c, ArrowDecl)]
    assert len(arrows) == 1
    assert arrows[0].source == "A"
    assert arrows[0].target == "B"
    assert arrows[0].style == "dashed"


def test_parse_negative_offset():
    fig = _parse('figure "T" []:\n  A [box]\n  B [box]\n  B.top = A.bottom - 10mm')
    constraints = [c for c in fig.children if isinstance(c, ConstraintExpr)]
    assert constraints[0].offset == -10.0
