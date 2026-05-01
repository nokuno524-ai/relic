"""Theme definitions for Relic figures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Theme:
    name: str = "academic"
    colors: dict[str, str] = field(default_factory=dict)
    fonts: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)

    def resolve_color(self, color: str) -> str:
        """Resolve theme color references like 'accent-blue' to TikZ color spec."""
        # Handle accent-blue!20 style
        parts = color.split("!")
        base = self.colors.get(parts[0], parts[0])
        if len(parts) > 1:
            return f"{base}!{parts[1]}"
        return base


ACADEMIC_THEME = Theme(
    name="academic",
    colors={
        "accent-blue": "blue!60!black",
        "accent-red": "red!70!black",
        "accent-green": "green!50!black",
        "accent-orange": "orange!80!black",
        "accent-purple": "purple!60!black",
        "bg-light": "gray!10",
        "bg-white": "white",
        "text-primary": "black",
        "text-secondary": "gray!70!black",
    },
    fonts={
        "title": r"\large\bfseries",
        "label": r"\small",
        "caption": r"\footnotesize",
    },
    defaults={
        "box-style": "draw, rounded corners=2pt, minimum width=20mm, minimum height=8mm, align=center",
        "circle-style": "draw, circle, minimum size=10mm, align=center",
        "arrow-style": "->, >=stealth, thick",
        "container-gap": "6mm",
    },
)

THEMES: dict[str, Theme] = {
    "academic": ACADEMIC_THEME,
}

NORD_THEME = Theme(
    name="nord",
    colors={
        "primary": "#5E81AC",
        "secondary": "#81A1C1",
        "accent": "#BF616A",
        "neutral": "#4C566A",
        "light": "#ECEFF4",
        "bg": "#2E3440",
    },
)

THEMES["nord"] = NORD_THEME


def get_theme(name: str) -> Theme:
    return THEMES.get(name, ACADEMIC_THEME)
