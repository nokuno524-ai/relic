"""TikZ backend — generate compilable LaTeX/TikZ from FlatIR."""

from __future__ import annotations

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


def generate_tikz(ir: FlatIR) -> str:
    """Generate a standalone .tex file from a FlatIR."""
    theme = get_theme(ir.theme)
    lines: list[str] = []

    # Preamble
    lines.append(r"\documentclass[border=2mm]{standalone}")
    lines.append(r"\usepackage{tikz}")
    lines.append(r"\usetikzlibrary{arrows.meta, positioning, calc}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\begin{tikzpicture}")

    # Define theme colors
    for name, color in theme.colors.items():
        lines.append(f"  \\definecolor{{{name}}}{{HTML}}{{{_color_to_hex(color)}}}")

    lines.append("")

    # Compute bounding box offset (shift so min x,y >= some margin)
    min_x = 0.0
    min_y = 0.0
    if ir.objects:
        min_x = min(o.left for o in ir.objects.values())
        min_y = min(o.bottom for o in ir.objects.values())
    # Shift everything so min is at (5, 5) mm
    ox = 5.0 - min_x
    oy = 5.0 - min_y

    # Draw objects
    for name, obj in ir.objects.items():
        if obj.obj_type == ObjType.CONTAINER:
            continue  # containers are implicit
        shape = _OBJ_TYPE_TO_TIKZ.get(obj.obj_type, "rectangle")
        x_mm = obj.x + ox
        y_mm = obj.y + oy

        style_parts = [shape, "draw"]
        if obj.obj_type == ObjType.BOX:
            style_parts.append("rounded corners=2pt")
        style_parts.append(f"minimum width={obj.width:.1f}mm")
        style_parts.append(f"minimum height={obj.height:.1f}mm")
        style_parts.append("align=center")

        fill = obj.fill
        if fill:
            fill = theme.resolve_color(fill)
            style_parts.append(f"fill={fill}")

        style = ", ".join(style_parts)
        label = _escape_latex(obj.label) if obj.label else name

        lines.append(f"  \\node[{style}] ({name}) at ({x_mm:.2f}mm, {y_mm:.2f}mm) {{{label}}};")

    lines.append("")

    # Draw arrows
    for arrow in ir.arrows:
        style_parts = ["-{Stealth[length=3mm]}", "thick"]
        if arrow.style == "dashed":
            style_parts.append("dashed")
        elif arrow.style == "dotted":
            style_parts.append("dotted")

        style = ", ".join(style_parts)
        label_part = ""
        if arrow.label:
            label_part = f" node[midway, above, font=\\small] {{{_escape_latex(arrow.label)}}}"

        lines.append(f"  \\draw[{style}] ({arrow.source}) -- ({arrow.target}){label_part};")

    lines.append("")
    lines.append(r"\end{tikzpicture}")
    lines.append(r"\end{document}")

    return "\n".join(lines) + "\n"


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters."""
    for old, new in [("\\", "\\\\"), ("{", "\\{"), ("}", "\\}"), ("_", "\\_"), ("%", "\\%")]:
        text = text.replace(old, new)
    return text


def _color_to_hex(color: str) -> str:
    """Try to convert color spec to hex. Returns a default if not parseable."""
    # For simple named colors, just return a reasonable hex
    # This is a simplification — full color parsing is complex
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
