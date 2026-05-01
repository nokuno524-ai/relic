"""Constraint system — 7 relational primitives."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Constraint:
    """A single constraint: target_anchor = source_anchor + offset."""
    target_name: str
    target_anchor: str
    source_name: str
    source_anchor: str
    offset: float = 0.0
    offset_unit: str = "mm"

    def depends_on(self) -> str:
        """Return the name of the object this constraint depends on."""
        return self.source_name

    def sets(self) -> str:
        """Return the name of the object this constraint sets."""
        return self.target_name
