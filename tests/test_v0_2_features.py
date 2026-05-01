"""Tests for Relic v0.2 features: comments, math labels, images, ML components,
bezier/orthogonal arrows, opacity, and Nord theme."""

from relic.lexer import tokenize
from relic.parser import parse
from relic.resolver import resolve
from relic.backends.tikz import generate_tikz, _format_label, _wrap_math
from relic.themes import get_theme


def _compile(src: str) -> str:
    return generate_tikz(resolve(parse(tokenize(src))))


# --- Feature 1: Comments ---

class TestComments:
    def test_line_comment(self):
        tokens = tokenize("A // comment\nB")
        names = [t.value for t in tokens if t.value in ("A", "B")]
        assert names == ["A", "B"]

    def test_block_comment_inline(self):
        tokens = tokenize("A /* removed */ B")
        names = [t.value for t in tokens if t.value in ("A", "B")]
        assert names == ["A", "B"]

    def test_block_comment_multiline(self):
        tokens = tokenize("A /* multi\nline\ncomment */ B")
        names = [t.value for t in tokens if t.value in ("A", "B")]
        assert names == ["A", "B"]

    def test_line_comment_in_figure(self):
        tex = _compile(
            'figure "T" []:\n'
            '  A [box, label: "X"] // side note\n'
            '  B [box, label: "Y"]'
        )
        assert "X" in tex
        assert "Y" in tex


# --- Feature 2: Math Labels ---

class TestMathLabels:
    def test_dollar_passthrough(self):
        result = _format_label(r"$\mathbf{W}_Q$")
        assert "$" in result
        assert r"\mathbf" in result

    def test_double_dollar_passthrough(self):
        result = _format_label(r"$$x^2$$")
        assert "$$" in result

    def test_auto_wrap_still_works(self):
        result = _wrap_math("x_i")
        assert "$x_i$" in result


# --- Feature 3: Image Embedding ---

class TestImageEmbedding:
    def test_image_node(self):
        tex = _compile(
            'figure "T" []:\n'
            '  Img [image, src: "cat.png"]'
        )
        assert r"\includegraphics" in tex
        assert "cat.png" in tex

    def test_image_with_width(self):
        tex = _compile(
            'figure "T" []:\n'
            '  Img [image, src: "photo.jpg", width: 30mm]'
        )
        assert "width=30mm" in tex


# --- Feature 4: ML Components ---

class TestMLComponents:
    def test_add_node(self):
        tex = _compile(
            'figure "T" []:\n'
            '  N [add]'
        )
        assert r"\oplus" in tex
        assert "circle" in tex

    def test_multiply_node(self):
        tex = _compile(
            'figure "T" []:\n'
            '  N [multiply]'
        )
        assert r"\otimes" in tex

    def test_softmax_node(self):
        tex = _compile(
            'figure "T" []:\n'
            '  SM [softmax]'
        )
        assert "Softmax" in tex
        assert "purple!20" in tex

    def test_concat_node(self):
        tex = _compile(
            'figure "T" []:\n'
            '  C [concat]'
        )
        assert "Concat" in tex

    def test_dropout_node(self):
        tex = _compile(
            'figure "T" []:\n'
            '  D [dropout]'
        )
        assert "Dropout" in tex


# --- Feature 5: Bezier & Orthogonal Arrows ---

class TestArrowRouting:
    def test_bezier_arrow(self):
        tex = _compile(
            'figure "T" []:\n'
            '  A [box, label: "A"]\n'
            '  B [box, label: "B"]\n'
            '  B.left = A.right + 25mm\n'
            '  B.center-y = A.center-y\n'
            '  arrow A -> B [bezier]'
        )
        assert "out=" in tex
        assert "in=" in tex

    def test_orthogonal_arrow(self):
        tex = _compile(
            'figure "T" []:\n'
            '  A [box, label: "A"]\n'
            '  B [box, label: "B"]\n'
            '  B.left = A.right + 25mm\n'
            '  B.center-y = A.center-y\n'
            '  arrow A -> B [orthogonal]'
        )
        assert "-|" in tex or "|-" in tex

    def test_label_pos_near_start(self):
        tex = _compile(
            'figure "T" []:\n'
            '  A [box, label: "A"]\n'
            '  B [box, label: "B"]\n'
            '  B.left = A.right + 25mm\n'
            '  B.center-y = A.center-y\n'
            '  arrow A -> B [label: "hi", label-pos: 0.2]'
        )
        assert "near start" in tex

    def test_label_pos_near_end(self):
        tex = _compile(
            'figure "T" []:\n'
            '  A [box, label: "A"]\n'
            '  B [box, label: "B"]\n'
            '  B.left = A.right + 25mm\n'
            '  B.center-y = A.center-y\n'
            '  arrow A -> B [label: "hi", label-pos: 0.8]'
        )
        assert "near end" in tex


# --- Feature 6: Opacity / Ghosting ---

class TestOpacity:
    def test_opacity_attribute(self):
        tex = _compile(
            'figure "T" []:\n'
            '  G [box, label: "Ghost", opacity: 0.2]'
        )
        assert "opacity=0.2" in tex
        assert "fill opacity=0.2" in tex

    def test_ghost_shorthand(self):
        tex = _compile(
            'figure "T" []:\n'
            '  G [box, label: "Ghost", ghost: true]'
        )
        assert "opacity=0.2" in tex


# --- Nord Theme ---

class TestNordTheme:
    def test_nord_theme_exists(self):
        theme = get_theme("nord")
        assert theme.name == "nord"
        assert theme.colors["primary"] == "#5E81AC"

    def test_nord_theme_in_compile(self):
        tex = _compile(
            'figure "T" [theme: nord]:\n'
            '  A [box, label: "X"]'
        )
        assert "5E81AC" in tex
