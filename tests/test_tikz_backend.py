"""Tests for TikZ backend."""

from relic.lexer import tokenize
from relic.parser import parse
from relic.resolver import resolve
from relic.backends.tikz import generate_tikz


def _compile(src: str) -> str:
    return generate_tikz(resolve(parse(tokenize(src))))


def test_basic_output():
    tex = _compile(
        'figure "Test" []:\n'
        '  A [box, label: "Hello"]'
    )
    assert r"\documentclass" in tex
    assert r"\begin{tikzpicture}" in tex
    assert r"\end{tikzpicture}" in tex
    assert r"\node" in tex
    assert "Hello" in tex


def test_arrow_output():
    tex = _compile(
        'figure "T" []:\n'
        '  A [box, label: "A"]\n'
        '  B [box, label: "B"]\n'
        '  B.left = A.right + 25mm\n'
        '  B.center-y = A.center-y\n'
        '  arrow A -> B [dashed, label: "link"]'
    )
    assert r"\draw" in tex
    assert "dashed" in tex
    assert "link" in tex


def test_standalone_compilable():
    tex = _compile(
        'figure "Min" []:\n'
        '  X [box, label: "Box"]'
    )
    assert r"\documentclass[border=2mm]{standalone}" in tex
    assert r"\usepackage{tikz}" in tex
    assert r"\end{document}" in tex
