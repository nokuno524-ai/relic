"""Flat IR — intermediate representation after resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from .objects import LayoutObject, ArrowObject, ObjType


@dataclass
class CalloutInfo:
    """Resolved callout between two objects."""
    source: str
    target: str
    style: str = "dashed"
    fill: str = "gray!5"


@dataclass
class FlatIR:
    """Resolved, flat intermediate representation."""
    objects: dict[str, LayoutObject] = field(default_factory=dict)
    arrows: list[ArrowObject] = field(default_factory=list)
    theme: str = "academic"
    figure_name: str = ""
    width: float = 140.0  # mm
    height: float = 100.0  # mm
    callouts: list[CalloutInfo] = field(default_factory=list)

    @property
    def containers(self) -> dict[str, list[str]]:
        """Map container name -> list of non-container child names."""
        result = {}
        for name, obj in self.objects.items():
            if obj.obj_type == ObjType.CONTAINER and obj.children:
                kids = []
                for cname in obj.children:
                    child = self.objects.get(cname)
                    if child and child.obj_type != ObjType.CONTAINER:
                        kids.append(cname)
                    elif child and child.obj_type == ObjType.CONTAINER:
                        # recurse to get leaf children
                        kids.extend(self._leaf_children(cname))
                result[name] = kids
        return result

    def _leaf_children(self, container_name: str) -> list[str]:
        obj = self.objects.get(container_name)
        if not obj or not obj.children:
            return []
        leaves = []
        for cname in obj.children:
            child = self.objects.get(cname)
            if child and child.obj_type == ObjType.CONTAINER:
                leaves.extend(self._leaf_children(cname))
            else:
                leaves.append(cname)
        return leaves

    @property
    def container_meta(self) -> dict[str, "tuple[str, str, list[str]]"]:
        """Map container name -> (layout, label, child_names) for non-container children."""
        result = {}
        for name, obj in self.objects.items():
            if obj.obj_type == ObjType.CONTAINER:
                leaves = self._leaf_children(name)
                result[name] = (obj.layout, obj.label, leaves)
        return result

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
