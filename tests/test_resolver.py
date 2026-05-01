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


def test_overlap_pushed_apart():
    """Two overlapping free objects should be pushed apart."""
    ir = _resolve(
        'figure "T" []:\n'
        '  A [box, label: "A", width: 20, height: 8]\n'
        '  B [box, label: "B", width: 20, height: 8]\n'
        '  B.left = A.left + 5mm\n'
        '  B.center-y = A.center-y'
    )
    a = ir.objects["A"]
    b = ir.objects["B"]
    # They should no longer overlap
    overlap_x = min(a.right, b.right) - max(a.left, b.left)
    overlap_y = min(a.top, b.top) - max(a.bottom, b.bottom)
    assert not (overlap_x > 0 and overlap_y > 0), f"Objects still overlap ({overlap_x:.1f}x{overlap_y:.1f}mm)"


def test_non_overlapping_unchanged():
    """Non-overlapping objects should not be moved by overlap resolution."""
    ir = _resolve(
        'figure "T" []:\n'
        '  A [box, label: "A"]\n'
        '  B [box, label: "B"]\n'
        '  B.left = A.right + 25mm\n'
        '  B.center-y = A.center-y'
    )
    a = ir.objects["A"]
    b = ir.objects["B"]
    # B.left should still equal A.right + 25mm
    assert abs(b.left - (a.right + 25.0)) < 0.1


def test_flow_container_siblings_not_separated():
    """Siblings in a flow container should not be pushed apart by overlap resolution."""
    ir = _resolve(
        'figure "T" []:\n'
        '  container C [flow-v, gap: 2mm]:\n'
        '    X [box, label: "X", width: 20, height: 8]\n'
        '    Y [box, label: "Y", width: 20, height: 8]'
    )
    x = ir.objects["X"]
    y = ir.objects["Y"]
    # Y should be directly below X with 2mm gap — overlap resolver shouldn't change this
    assert abs(y.top - x.bottom) < 5.0  # roughly where flow layout put it


def test_ghosted_objects_not_separated():
    """Ghosted objects should not trigger overlap resolution."""
    ir = _resolve(
        'figure "T" []:\n'
        '  A [box, label: "A", width: 20, height: 8]\n'
        '  G [box, label: "G", width: 20, height: 8, ghost: true]\n'
        '  G.left = A.left + 5mm\n'
        '  G.center-y = A.center-y'
    )
    a = ir.objects["A"]
    g = ir.objects["G"]
    # A should not have been moved (G is ghosted)
    assert abs(a.x) < 0.01  # A stays at default position
    assert abs(g.x - (a.left + 5.0 + g.width / 2)) < 0.1
