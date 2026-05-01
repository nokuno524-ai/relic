"""Object model for layout computation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class ObjType(Enum):
    BOX = auto()
    CIRCLE = auto()
    DIAMOND = auto()
    ELLIPSE = auto()
    CONTAINER = auto()


@dataclass
class LayoutObject:
    """A layout object with computed position and size."""
    name: str
    obj_type: ObjType
    # Absolute position (center)
    x: float = 0.0
    y: float = 0.0
    # Size
    width: float = 20.0  # mm
    height: float = 8.0  # mm
    # Visual properties
    label: str = ""
    fill: str = ""
    draw_color: str = "black"
    line_style: str = ""
    line_width: str = ""
    # Container
    layout: str = ""  # flow-v, flow-h, grid
    gap: float = 6.0  # mm
    children: list[str] = field(default_factory=list)  # child names
    parent: str = ""
    # Anchors (computed)
    resolved: bool = False

    # --- Anchor properties ---
    @property
    def left(self) -> float:
        return self.x - self.width / 2

    @property
    def right(self) -> float:
        return self.x + self.width / 2

    @property
    def top(self) -> float:
        return self.y + self.height / 2

    @property
    def bottom(self) -> float:
        return self.y - self.height / 2

    @property
    def center_x(self) -> float:
        return self.x

    @property
    def center_y(self) -> float:
        return self.y

    def get_anchor(self, anchor: str) -> float:
        """Get the value of a named anchor."""
        anchors = {
            "left": self.left,
            "right": self.right,
            "top": self.top,
            "bottom": self.bottom,
            "center": self.x,  # alias for center-x
            "center-x": self.center_x,
            "center-y": self.center_y,
            "width": self.width,
            "height": self.height,
            "x": self.x,
            "y": self.y,
        }
        if anchor not in anchors:
            raise ValueError(f"Unknown anchor: {anchor}")
        return anchors[anchor]

    def set_anchor(self, anchor: str, value: float):
        """Set position via an anchor name."""
        match anchor:
            case "left":
                self.x = value + self.width / 2
            case "right":
                self.x = value - self.width / 2
            case "top":
                self.y = value - self.height / 2
            case "bottom":
                self.y = value + self.height / 2
            case "center" | "center-x":
                self.x = value
            case "center-y":
                self.y = value
            case "x":
                self.x = value
            case "y":
                self.y = value
            case "width":
                self.width = value
            case "height":
                self.height = value
            case _:
                raise ValueError(f"Cannot set anchor: {anchor}")


@dataclass
class ArrowObject:
    """An arrow between two objects."""
    source: str
    target: str
    style: str = ""
    label: str = ""
    line: int = 0
