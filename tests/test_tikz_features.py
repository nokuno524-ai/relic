"""Tests for new TikZ backend features."""

from relic.lexer import tokenize
from relic.parser import parse
from relic.resolver import resolve
from relic.backends.tikz import generate_tikz, _wrap_math, _escape_latex


def _compile(src: str) -> str:
    return generate_tikz(resolve(parse(tokenize(src))))


class TestStyleDefinitions:
    def test_relicbox_style_defined(self):
        tex = _compile('figure "T" []:\n  A [box, label: "X"]')
        assert "relicbox/.style=" in tex
        assert "relicarrow/.style=" in tex
        assert "container/.style=" in tex

    def test_node_uses_relicbox_style(self):
        tex = _compile('figure "T" []:\n  A [box, label: "X"]')
        assert "\\node[relicbox]" in tex

    def test_circle_uses_reliccircle_style(self):
        tex = _compile('figure "T" []:\n  A [circle, label: "X"]')
        assert "reliccircle" in tex


class TestRelativePositioning:
    def test_right_of_positioning(self):
        tex = _compile(
            'figure "T" []:\n'
            '  A [box, label: "A"]\n'
            '  B [box, label: "B"]\n'
            '  B.left = A.right + 25mm\n'
            '  B.center-y = A.center-y'
        )
        assert "right=25mm of A" in tex

    def test_below_positioning_from_flow(self):
        tex = _compile(
            'figure "T" []:\n'
            '  container C [flow-v, gap: 8mm]:\n'
            '    X [box, label: "X"]\n'
            '    Y [box, label: "Y"]'
        )
        assert "below=8mm of X" in tex

    def test_anchor_node_has_absolute_position(self):
        tex = _compile('figure "T" []:\n  A [box, label: "A"]')
        assert "at (" in tex


class TestContainerGrouping:
    def test_fit_node_generated(self):
        tex = _compile(
            'figure "T" []:\n'
            '  container C [flow-v, gap: 6mm]:\n'
            '    X [box, label: "X"]\n'
            '    Y [box, label: "Y"]'
        )
        assert "fit=(X) (Y)" in tex
        assert "on background layer" in tex

    def test_container_with_label(self):
        tex = _compile(
            'figure "T" []:\n'
            '  container Enc [flow-v, label: "Encoder"]:\n'
            '    X [box, label: "X"]\n'
            '    Y [box, label: "Y"]'
        )
        assert "above:Encoder" in tex


class TestFlowArrows:
    def test_flow_v_arrows(self):
        tex = _compile(
            'figure "T" []:\n'
            '  container C [flow-v, gap: 6mm]:\n'
            '    X [box, label: "X"]\n'
            '    Y [box, label: "Y"]'
        )
        assert "\\draw[relicarrow] (X) -- (Y);" in tex

    def test_flow_h_arrows(self):
        tex = _compile(
            'figure "T" []:\n'
            '  container C [flow-h, gap: 10mm]:\n'
            '    X [box, label: "X"]\n'
            '    Y [box, label: "Y"]'
        )
        assert "\\draw[relicarrow] (X) -- (Y);" in tex

    def test_no_flow_arrows_for_explicit(self):
        """Explicit arrows use relicarrow style too."""
        tex = _compile(
            'figure "T" []:\n'
            '  A [box, label: "A"]\n'
            '  B [box, label: "B"]\n'
            '  B.left = A.right + 25mm\n'
            '  B.center-y = A.center-y\n'
            '  arrow A -> B'
        )
        assert "\\draw[relicarrow]" in tex


class TestMathMode:
    def test_subscript_wrapped(self):
        result = _wrap_math("x_i")
        assert "$x_i$" in result

    def test_greek_letter_wrapped(self):
        result = _wrap_math("\\alpha")
        assert "$\\alpha$" in result

    def test_mixed_label(self):
        result = _wrap_math("Loss (L_2)")
        assert "$L_2$" in result

    def test_plain_text_unchanged(self):
        result = _wrap_math("Hello World")
        assert result == "Hello World"


class TestArrowTips:
    def test_stealth_global(self):
        tex = _compile('figure "T" []:\n  A [box, label: "A"]')
        assert ">=Stealth" in tex

    def test_arrows_meta_library(self):
        tex = _compile('figure "T" []:\n  A [box, label: "A"]')
        assert "arrows.meta" in tex


class TestLibraries:
    def test_fit_and_backgrounds_libraries(self):
        tex = _compile('figure "T" []:\n  A [box, label: "A"]')
        assert "fit" in tex
        assert "backgrounds" in tex
