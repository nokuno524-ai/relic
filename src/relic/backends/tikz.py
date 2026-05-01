"""TikZ backend — generate compilable LaTeX/TikZ from FlatIR."""

from __future__ import annotations

import re

from ..ir import FlatIR
from ..objects import ObjType
from ..themes import get_theme

_OBJ_TYPE_TO_TIKZ = {
    ObjType.BOX: "rectangle",
    ObjType.CIRCLE: "circle",
    ObjType.DIAMOND: "diamond",
    ObjType.ELLIPSE: "ellipse",
    ObjType.CONTAINER: "rectangle",
}

# Regex patterns for math mode detection
_MATH_SYMBOLS = re.compile(
    r"(?<!\$)("  # not already in math mode
    r"\\(?:alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega"
    r"|sum|int|prod|frac|sqrt|infty|partial|nabla)"
    r"|(?<![A-Za-z])\w+[_^]\w+"  # x_i, x^2, etc. (word_subscript/superscript)
    r")(?!\$)"
)

# Simpler approach: find individual math tokens
_MATH_TOKEN = re.compile(
    r"\\(?:alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega"
    r"|sum|int|prod|frac|sqrt|infty|partial|nabla)"
    r"|(?<![A-Za-z\\])\b[a-zA-Z]\w*[_^][a-zA-Z0-9{}\w]*"
)


def _wrap_math(label: str) -> str:
    """Detect math symbols in a label and wrap them in $...$."""
    if not label:
        return label

    # Find all math tokens and their positions
    matches = list(_MATH_TOKEN.finditer(label))
    if not matches:
        return label

    # Work backwards to preserve positions
    result = label
    for m in reversed(matches):
        token = m.group()
        start, end = m.start(), m.end()
        # Check if already inside $...$
        before = result[:start]
        # Count unescaped $ signs before this position
        dollar_count = before.count("$") - before.count("\\$")
        if dollar_count % 2 == 0:
            # Not in math mode, wrap it
            result = result[:start] + "$" + token + "$" + result[end:]

    return result


def generate_tikz(ir: FlatIR) -> str:
    """Generate a standalone .tex file from a FlatIR."""
    theme = get_theme(ir.theme)
    lines: list[str] = []

    # Preamble
    lines.append(r"\documentclass[border=2mm]{standalone}")
    lines.append(r"\usepackage{tikz}")
    lines.append(r"\usetikzlibrary{arrows.meta, positioning, calc, fit, backgrounds}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\begin{tikzpicture}[")

    # Style definitions (Fix 2 + Fix 6)
    lines.append("    font=\\small,")
    lines.append("    >=Stealth,")
    lines.append("    relicbox/.style={rectangle, draw, fill=white, rounded corners=2pt, minimum width=25mm, minimum height=8mm, align=center},")
    lines.append("    reliccircle/.style={draw, circle, minimum size=10mm, align=center, fill=white},")
    lines.append("    relicarrow/.style={->, thick, >=Stealth},")
    lines.append("    container/.style={draw=gray, dashed, fill=gray!5, rounded corners=4pt, inner sep=4mm}")
    lines.append("  ]")

    # Define theme colors
    for name, color in theme.colors.items():
        lines.append(f"  \\definecolor{{{name}}}{{HTML}}{{{_color_to_hex(color)}}}")

    lines.append("")

    # Separate containers and non-container objects
    non_containers = [(name, obj) for name, obj in ir.objects.items()
                      if obj.obj_type != ObjType.CONTAINER]

    # Find the anchor node (first non-container with no positioning metadata)
    anchor_name = None
    positioned_names = set()
    for name, obj in non_containers:
        if not obj.pos_direction and not obj.pos_reference:
            anchor_name = name
            break

    # Draw objects with relative positioning
    for name, obj in non_containers:
        shape = _OBJ_TYPE_TO_TIKZ.get(obj.obj_type, "rectangle")

        # Determine style
        if obj.obj_type == ObjType.BOX:
            style = "relicbox"
        elif obj.obj_type == ObjType.CIRCLE:
            style = "reliccircle"
        else:
            style_parts = [shape, "draw", "align=center"]
            style = ", ".join(style_parts)

        # Handle fill override
        if obj.fill:
            fill = theme.resolve_color(obj.fill)
            style += f", fill={fill}"

        label = _format_label(obj.label if obj.label else name)

        # Positioning: use relative positioning everywhere except anchor
        if obj.pos_direction and obj.pos_reference:
            # Relative positioning
            dist = f"{obj.pos_distance:.0f}mm" if obj.pos_distance > 0 else ""
            lines.append(f"  \\node[{style}, {obj.pos_direction}={dist} of {obj.pos_reference}] ({name}) {{{label}}};")
        else:
            # Anchor node at origin
            lines.append(f"  \\node[{style}] ({name}) {{{label}}};")

    lines.append("")

    # Fix 3: Visual container grouping
    container_meta = ir.container_meta
    if container_meta:
        lines.append("  % Container grouping")
        lines.append(r"  \begin{scope}[on background layer]")
        for cname, (layout, label, children) in container_meta.items():
            if not children:
                continue
            fit_nodes = " ".join(f"({c})" for c in children)
            label_part = ""
            if label:
                label_part = f", label={{[anchor=south]above:{_format_label(label)}}}"
            lines.append(f"    \\node[container, fit={fit_nodes}{label_part}] ({cname}) {{}};")
        lines.append(r"  \end{scope}")
        lines.append("")

    # Fix 4: Flow arrows (auto-generate for flow-v and flow-h containers)
    flow_arrows: list[tuple[str, str]] = []
    for cname, (layout, label, children) in container_meta.items():
        if layout in ("flow-v", "flow-h"):
            for i in range(len(children) - 1):
                flow_arrows.append((children[i], children[i + 1]))

    if flow_arrows:
        lines.append("  % Flow arrows")
        for src, tgt in flow_arrows:
            lines.append(f"  \\draw[relicarrow] ({src}) -- ({tgt});")
        lines.append("")

    # Draw explicit arrows
    for arrow in ir.arrows:
        style_parts = ["relicarrow"]
        if arrow.style == "dashed":
            style_parts.append("dashed")
        elif arrow.style == "dotted":
            style_parts.append("dotted")

        style = ", ".join(style_parts)
        label_part = ""
        if arrow.label:
            label_part = f" node[midway, above, font=\\small] {{{_format_label(arrow.label)}}}"

        lines.append(f"  \\draw[{style}] ({arrow.source}) -- ({arrow.target}){label_part};")

    lines.append("")
    lines.append(r"\end{tikzpicture}")
    lines.append(r"\end{document}")

    return "\n".join(lines) + "\n"


def _format_label(label: str) -> str:
    """Format a label: wrap math, escape LaTeX."""
    label = _wrap_math(label)
    return _escape_latex(label)


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters, but preserve backslash commands for math."""
    # Don't escape backslashes that are part of LaTeX commands
    # We need to be careful: only escape bare special chars
    # Strategy: protect \command sequences, then escape remaining specials
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text) and text[i + 1].isalpha():
            # LaTeX command like \alpha — keep as-is
            j = i + 1
            while j < len(text) and text[j].isalpha():
                j += 1
            result.append(text[i:j])
            i = j
        elif text[i] == '_':
            # Check if we're inside $...$ — if so, keep as-is
            # Count $ before this position
            before = text[:i]
            dollar_count = before.count('$')
            if dollar_count % 2 == 1:
                result.append('_')
            else:
                result.append('\\_')
            i += 1
        elif text[i] == '%':
            result.append('\\%')
            i += 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def _color_to_hex(color: str) -> str:
    """Try to convert color spec to hex."""
    color_map = {
        "blue!60!black": "0000CC",
        "red!70!black": "CC0000",
        "green!50!black": "009900",
        "orange!80!black": "E68A00",
        "purple!60!black": "7A0099",
        "gray!10": "E6E6E6",
        "white": "FFFFFF",
        "black": "000000",
        "gray!70!black": "4D4D4D",
    }
    return color_map.get(color, "333333")
