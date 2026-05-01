"""Integration tests — end-to-end .relic -> .tex."""

import tempfile
from pathlib import Path

from relic.cli import compile_file


def test_compile_minimal():
    base = Path(__file__).resolve().parent.parent / "examples"
    tex = compile_file(str(base / "minimal.relic"))
    assert r"\begin{tikzpicture}" in tex
    assert "Hello World" in tex


def test_compile_two_boxes():
    base = Path(__file__).resolve().parent.parent / "examples"
    tex = compile_file(str(base / "two_boxes.relic"))
    assert r"\node" in tex
    assert "Box A" in tex
    assert "Box B" in tex


def test_compile_encoder_decoder():
    base = Path(__file__).resolve().parent.parent / "examples"
    tex = compile_file(str(base / "encoder_decoder.relic"))
    assert "Source Tokens" in tex
    assert "Embedding" in tex
    assert "Target Tokens" in tex


def test_compile_multi_panel():
    base = Path(__file__).resolve().parent.parent / "examples"
    tex = compile_file(str(base / "multi_panel.relic"))
    assert r"\begin{tikzpicture}" in tex


def test_output_to_file():
    with tempfile.NamedTemporaryFile(suffix=".tex", delete=False, mode="w") as f:
        out = f.name
    try:
        base = Path(__file__).resolve().parent.parent / "examples"
        compile_file(str(base / "minimal.relic"), out)
        content = Path(out).read_text()
        assert r"\begin{tikzpicture}" in content
    finally:
        Path(out).unlink(missing_ok=True)
