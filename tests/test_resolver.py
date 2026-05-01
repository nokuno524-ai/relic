"""Tests for the constraint resolver."""

from relic.lexer import tokenize
from relic.parser import parse
from relic.resolver import resolve


def _resolve(src: str):
    return resolve(parse(tokenize(src)))


def test_resolve_two_boxes():
    ir = _resolve(
        'figure "T" [width: 12cm]:\n'
        '  A [box, label: "Box A"]\n'
        '  B [box, label: "Box B"]\n'
        '  B.left = A.right + 25mm\n'
        '  B.center-y = A.center-y'
    )
    assert "A" in ir.objects
    assert "B" in ir.objects
    a = ir.objects["A"]
    b = ir.objects["B"]
    # B.left should equal A.right + 25mm
    assert abs(b.left - (a.right + 25.0)) < 0.01
    # Same center-y
    assert abs(b.center_y - a.center_y) < 0.01


def test_resolve_container_flow_v():
    ir = _resolve(
        'figure "T" []:\n'
        '  container C [flow-v, gap: 6mm]:\n'
        '    X [box, label: "X"]\n'
        '    Y [box, label: "Y"]'
    )
    x = ir.objects["X"]
    y = ir.objects["Y"]
    # Y should be below X with gap
    assert y.top <= x.bottom


def test_resolve_object_defaults():
    ir = _resolve(
        'figure "T" []:\n'
        '  A [box, label: "Test"]'
    )
    a = ir.objects["A"]
    assert a.label == "Test"
    assert a.width > 0
    assert a.height > 0
