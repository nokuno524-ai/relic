"""Tests for new features: shadows, tensor3d, annotations, positioned, smart routing, error messages."""

import pytest
from relic.lexer import tokenize
from relic.parser import parse
from relic.resolver import resolve
from relic.backends.tikz import generate_tikz


def _compile(source: str) -> str:
    """Compile a relic source to tikz."""
    tokens = tokenize(source)
    ast = parse(tokens)
    ir = resolve(ast)
    return generate_tikz(ir)


# ─── Feature 1: Drop Shadows ───

class TestShadows:
    def test_shadow_property(self):
        src = '''figure "test":
    A [box, label: "hello", shadow: true]
'''
        tikz = _compile(src)
        assert "shadows.blur" in tikz
        assert "blur shadow" in tikz

    def test_no_shadow_by_default(self):
        src = '''figure "test":
    A [box, label: "hello"]
'''
        tikz = _compile(src)
        assert "shadows.blur" not in tikz
        assert "blur shadow" not in tikz

    def test_shadow_on_container_child(self):
        src = '''figure "test":
    container MyGroup [flow-v]:
        A [box, label: "Important", shadow: true]
        B [box, label: "Normal"]
'''
        tikz = _compile(src)
        assert "blur shadow" in tikz


# ─── Feature 2: Smart Route Defaults ───

class TestSmartRouting:
    def test_same_rank_arrow(self):
        src = '''figure "test":
    A [box, label: "A"]
    B [box, label: "B"]
    A.right = B.left + 20mm
    arrow A -> B
'''
        tikz = _compile(src)
        assert "relicarrow" in tikz

    def test_vertical_arrow(self):
        src = '''figure "test":
    A [box, label: "A"]
    B [box, label: "B"]
    B.top = A.bottom - 15mm
    B.center-x = A.center-x
    arrow A -> B
'''
        tikz = _compile(src)
        assert "relicarrow" in tikz


# ─── Feature 3: Tensor3D ───

class TestTensor3D:
    def test_tensor3d_type(self):
        src = '''figure "test":
    X [tensor3d, width: 20, height: 8, depth: 5, label: "$X$"]
'''
        tikz = _compile(src)
        assert "Tensor3D" in tikz
        assert "5.0mm" in tikz

    def test_tensor3d_default_depth(self):
        src = '''figure "test":
    X [tensor3d, label: "$X$"]
'''
        tikz = _compile(src)
        assert "Tensor3D" in tikz


# ─── Feature 4: Annotation Labels ───

class TestAnnotations:
    def test_annotate_top(self):
        src = '''figure "test":
    X [box, label: "X", annotate-top: "$N$"]
'''
        tikz = _compile(src)
        assert "above=1mm" in tikz
        assert "$N$" in tikz

    def test_annotate_right(self):
        src = '''figure "test":
    X [box, label: "X", annotate-right: "$d$"]
'''
        tikz = _compile(src)
        assert "right=1mm" in tikz

    def test_multiple_annotations(self):
        src = '''figure "test":
    X [tensor3d, label: "$X$", annotate-top: "$N$", annotate-right: "$d$"]
'''
        tikz = _compile(src)
        assert "above=1mm" in tikz
        assert "right=1mm" in tikz


# ─── Feature 5: Semantic Positioning ───

class TestPositioned:
    def test_right_of(self):
        src = '''figure "test":
    A [box, label: "A"]
    B [box, label: "B"]
    B positioned right-of A
'''
        tikz = _compile(src)
        assert "B" in tikz
        assert "A" in tikz

    def test_below(self):
        src = '''figure "test":
    A [box, label: "A"]
    B [box, label: "B"]
    B positioned below A
'''
        tikz = _compile(src)
        assert "B" in tikz

    def test_left_of(self):
        src = '''figure "test":
    A [box, label: "A"]
    B [box, label: "B"]
    B positioned left-of A
'''
        tikz = _compile(src)

    def test_above(self):
        src = '''figure "test":
    A [box, label: "A"]
    B [box, label: "B"]
    B positioned above A
'''
        tikz = _compile(src)

    def test_with_gap(self):
        src = '''figure "test":
    A [box, label: "A"]
    B [box, label: "B"]
    B positioned right-of A [gap: 25]
'''
        tikz = _compile(src)


# ─── Feature 6: LLM-Friendly Error Messages ───

class TestErrorMessages:
    def test_suggestions_on_bad_arrow(self):
        from relic.errors import suggest_names
        names = ["PosEncEnc", "PosEncDec", "Encoder", "Decoder"]
        result = suggest_names("PosEnc", names)
        assert len(result) > 0
        assert "PosEncEnc" in result or "PosEncDec" in result

    def test_arrow_to_nonexistent_node(self):
        src = '''figure "test":
    A [box, label: "A"]
    B [box, label: "B"]
    arrow A -> C
'''
        with pytest.raises(Exception) as exc_info:
            _compile(src)
        assert "C" in str(exc_info.value)

    def test_resolve_error_with_suggestions(self):
        from relic.errors import ResolveError
        err = ResolveError("Node 'Foo' not found", suggestions=["FooBar", "FooBaz"])
        assert "FooBar" in str(err)
        assert "Did you mean" in str(err)
