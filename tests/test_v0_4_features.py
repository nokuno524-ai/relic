"""Tests for v0.4 features: bus routing, container stacks, callouts, uniform sizing."""
import pytest
from relic.lexer import tokenize
from relic.parser import Parser
from relic.rank_resolver import RankResolver
from relic.backends.tikz import generate_tikz


def parse(source: str):
    tokens = tokenize(source)
    return Parser(tokens).parse()


def compile_to_ir(source: str):
    ast = parse(source)
    return RankResolver().resolve(ast)


def compile_to_tikz(source: str) -> str:
    ir = compile_to_ir(source)
    return generate_tikz(ir)


class TestBusRouting:
    def test_bus_arrow_parsing(self):
        src = '''figure "Test":
    A [box, label: "A"]
    B [box, label: "B"]
    C [box, label: "C"]
    T [box, label: "Target"]
    arrow A, B, C -> T [route: bus]'''
        ast = parse(src)
        arrows = [c for c in ast.children if hasattr(c, 'source') and hasattr(c, 'target')]
        assert len(arrows) == 3
        assert all(a.target == "T" for a in arrows)
        assert all(a.route == "bus" for a in arrows)

    def test_bus_arrow_compiles(self):
        src = '''figure "Test":
    A [box, label: "A"]
    B [box, label: "B"]
    C [box, label: "C"]
    T [box, label: "Target"]
    A positioned left-of B [gap: 20]
    C positioned right-of B [gap: 20]
    T positioned below B [gap: 20]
    arrow A, B, C -> T [route: bus]'''
        tikz = compile_to_tikz(src)
        assert "Bus routing" in tikz


class TestContainerStack:
    def test_stack_parsing(self):
        src = '''figure "Test":
    container Enc [flow-v, stack: 3, stack-label: "$\\times N$"]:
        SA [box, label: "Self-Attention"]
        FFN [box, label: "FFN"]'''
        ir = compile_to_ir(src)
        enc = ir.objects["Enc"]
        assert enc.stack_count == 3
        assert enc.stack_label == "$\\times N$"

    def test_stack_renders_shadows(self):
        src = '''figure "Test":
    container Enc [flow-v, stack: 3, stack-label: "$\\times N$"]:
        SA [box, label: "Self-Attention"]
        FFN [box, label: "FFN"]'''
        tikz = compile_to_tikz(src)
        assert "Stack visualization" in tikz
        assert "opacity" in tikz
        assert "shift" in tikz


class TestCallout:
    def test_callout_parsing(self):
        src = '''figure "Test":
    Block [box, label: "Block"]
    container Detail [flow-v, gap: 5]:
        A [box, label: "A"]
        B [box, label: "B"]
    callout Block -> Detail [style: dashed, fill: "gray!5"]'''
        ir = compile_to_ir(src)
        assert len(ir.callouts) == 1
        assert ir.callouts[0].source == "Block"
        assert ir.callouts[0].target == "Detail"

    def test_callout_renders_trapezoid(self):
        src = '''figure "Test":
    Block [box, label: "Block"]
    container Detail [flow-v, gap: 5]:
        A [box, label: "A"]
        B [box, label: "B"]
    callout Block -> Detail [style: dashed]'''
        tikz = compile_to_tikz(src)
        assert "Callout" in tikz
        assert "cycle" in tikz


class TestUniformRankSizing:
    def test_uniform_width(self):
        src = '''figure "Test":
    A [box, label: "Short"]
    B [box, label: "A much longer label"]
    C [box, label: "Mid"]
    A positioned left-of B [gap: 15]
    C positioned right-of B [gap: 15]'''
        ir = compile_to_ir(src)
        widths = [ir.objects[n].width for n in ["A", "B", "C"]]
        assert widths[0] == widths[1] == widths[2]


class TestAcademicTheme:
    def test_default_theme(self):
        src = '''figure "Test":
    A [box, label: "Box"]'''
        ir = compile_to_ir(src)
        assert ir.theme == "academic"

    def test_explicit_theme(self):
        src = '''figure "Test" [theme: academic]:
    A [box, label: "Box"]'''
        ir = compile_to_ir(src)
        assert ir.theme == "academic"
