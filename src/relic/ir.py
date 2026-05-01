"""Flat IR — intermediate representation after resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from .objects import LayoutObject, ArrowObject, ObjType


@dataclass
class FlatIR:
    """Resolved, flat intermediate representation."""
    objects: dict[str, LayoutObject] = field(default_factory=dict)
    arrows: list[ArrowObject] = field(default_factory=list)
    theme: str = "academic"
    figure_name: str = ""
    width: float = 140.0  # mm
    height: float = 100.0  # mm

    def to_dict(self) -> dict:
        """Serialize to a JSON-like dict."""
        objs = {}
        for name, obj in self.objects.items():
            objs[name] = {
                "type": obj.obj_type.name.lower(),
                "x": obj.x,
                "y": obj.y,
                "width": obj.width,
                "height": obj.height,
                "label": obj.label,
                "fill": obj.fill,
                "draw": obj.draw_color,
                "style": obj.line_style,
            }
        arrows = []
        for a in self.arrows:
            arrows.append({
                "source": a.source,
                "target": a.target,
                "style": a.style,
                "label": a.label,
            })
        return {
            "figure": self.figure_name,
            "theme": self.theme,
            "width": self.width,
            "height": self.height,
            "objects": objs,
            "arrows": arrows,
        }
