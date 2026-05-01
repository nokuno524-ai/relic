"""CLI for Relic compiler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .lexer import tokenize
from .parser import parse
from .resolver import resolve
from .backends.tikz import generate_tikz
from .errors import RelicError


def compile_file(input_path: str, output_path: str | None = None) -> str:
    """Compile a .relic file to TikZ."""
    source = Path(input_path).read_text()
    tokens = tokenize(source)
    ast = parse(tokens)
    ir = resolve(ast)
    tex = generate_tikz(ir)

    if output_path:
        Path(output_path).write_text(tex)

    return tex


def main():
    parser = argparse.ArgumentParser(prog="relic", description="Relic layout compiler")
    sub = parser.add_subparsers(dest="command")

    compile_cmd = sub.add_parser("compile", help="Compile a .relic file to TikZ")
    compile_cmd.add_argument("input", help="Input .relic file")
    compile_cmd.add_argument("-o", "--output", help="Output .tex file")

    args = parser.parse_args()

    if args.command == "compile":
        try:
            result = compile_file(args.input, args.output)
            if not args.output:
                print(result)
            else:
                print(f"Compiled {args.input} -> {args.output}")
        except RelicError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
