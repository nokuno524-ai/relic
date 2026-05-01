"""Constraint resolver — forward propagation through DAG."""

from __future__ import annotations

from .ast_nodes import (
    ArrowDecl, ContainerDecl, ConstraintExpr, FigureDecl, ObjectDecl,
)
from .constraints import Constraint
from .dag import DAG, build_dag
from .errors import ResolveError
from .ir import FlatIR
from .objects import ArrowObject, LayoutObject, ObjType


_UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "pt": 0.3528, "%": 1.0}


def _resolve_props(decl: ObjectDecl | ContainerDecl) -> dict[str, str | float]:
    """Extract named properties from declaration."""
    props = {}
    for p in decl.properties:
        if isinstance(p.value, bool):
            props[p.key] = p.value
        else:
            props[p.key] = p.value
    return props


def _offset_to_mm(offset: float, unit: str) -> float:
    return offset * _UNIT_TO_MM.get(unit, 1.0)


class Resolver:
    """Resolves constraints to compute absolute positions."""

    def __init__(self):
        self.objects: dict[str, LayoutObject] = {}
        self.arrows: list[ArrowObject] = []
        self.constraints: list[Constraint] = []
        self.theme: str = "academic"
        self.figure_name: str = ""
        self.figure_width: float = 140.0

    def resolve(self, figure: FigureDecl) -> FlatIR:
        """Resolve a figure AST into a FlatIR."""
        self.figure_name = figure.name
        for p in figure.properties:
            if p.key == "theme":
                self.theme = str(p.value)
            elif p.key == "width":
                val = str(p.value)
                self.figure_width = _parse_dimension(val)

        # First pass: register all objects
        self._register_children(figure.children)

        # Second pass: collect constraints
        self._collect_constraints(figure.children)

        # Third pass: auto-layout for flow containers
        self._apply_flow_layouts(figure.children)

        # Fourth pass: resolve DAG
        dag = build_dag(self.constraints, set(self.objects.keys()))
        order = dag.topological_sort()

        for name in order:
            constraints = dag.get_constraints_for(name)
            for c in constraints:
                self._apply_constraint(c)

        # Fifth pass: compute relative positioning metadata
        self._compute_positioning_metadata(dag)

        return FlatIR(
            objects=self.objects,
            arrows=self.arrows,
            theme=self.theme,
            figure_name=self.figure_name,
            width=self.figure_width,
        )

    def _register_children(self, children: list):
        for child in children:
            if isinstance(child, ObjectDecl):
                self._register_object(child)
            elif isinstance(child, ContainerDecl):
                self._register_container(child)
            elif isinstance(child, ArrowDecl):
                self.arrows.append(ArrowObject(
                    source=child.source, target=child.target,
                    style=child.style, label=child.label, line=child.line,
                ))

    def _register_object(self, decl: ObjectDecl, parent: str = ""):
        props = _resolve_props(decl)
        obj = LayoutObject(
            name=decl.name,
            obj_type=ObjType[decl.obj_type.upper()],
            label=str(props.get("label", decl.name)),
            fill=str(props.get("fill", "")),
            parent=parent,
            width=float(props.get("min-width", props.get("width", 20.0)))
                if isinstance(props.get("min-width", props.get("width", 20.0)), (int, float)) else 20.0,
            height=float(props.get("min-height", props.get("height", 8.0)))
                if isinstance(props.get("min-height", props.get("height", 8.0)), (int, float)) else 8.0,
        )
        if "width" in props and isinstance(props["width"], (int, float)):
            obj.width = float(props["width"])
        if "height" in props and isinstance(props["height"], (int, float)):
            obj.height = float(props["height"])
        self.objects[decl.name] = obj
        self._register_children(decl.children)

    def _register_container(self, decl: ContainerDecl, parent: str = ""):
        props = _resolve_props(decl)
        gap = 6.0
        if "gap" in props:
            val = str(props["gap"])
            gap = _parse_dimension(val)

        obj = LayoutObject(
            name=decl.name,
            obj_type=ObjType.CONTAINER,
            layout=decl.layout,
            gap=gap,
            parent=parent,
            label=str(props.get("label", "")),
        )
        self.objects[decl.name] = obj

        for child in decl.children:
            if isinstance(child, ObjectDecl):
                self._register_object(child, parent=decl.name)
                obj.children.append(child.name)
            elif isinstance(child, ContainerDecl):
                self._register_container(child, parent=decl.name)
                obj.children.append(child.name)

    def _collect_constraints(self, children: list):
        for child in children:
            if isinstance(child, ConstraintExpr):
                self.constraints.append(Constraint(
                    target_name=child.target.object_name,
                    target_anchor=child.target.anchor,
                    source_name=child.source.object_name,
                    source_anchor=child.source.anchor,
                    offset=child.offset,
                    offset_unit=child.offset_unit,
                ))
            elif isinstance(child, ContainerDecl):
                self._collect_constraints(child.children)
            elif isinstance(child, ObjectDecl):
                self._collect_constraints(child.children)

    def _apply_flow_layouts(self, children: list):
        """Auto-inject position constraints for flow containers."""
        for child in children:
            if isinstance(child, ContainerDecl):
                obj = self.objects.get(child.name)
                if obj and obj.children:
                    self._layout_flow_container(obj, child)
                self._apply_flow_layouts(child.children)

    def _layout_flow_container(self, container: LayoutObject, decl: ContainerDecl):
        """Create sequential constraints for children in a flow container."""
        child_names = container.children
        if len(child_names) < 2:
            # Single child: just center it in container
            if child_names:
                cname = child_names[0]
                self.constraints.append(Constraint(cname, "center-x", container.name, "center-x"))
                self.constraints.append(Constraint(cname, "center-y", container.name, "center-y"))
            return

        gap = container.gap
        is_vertical = container.layout in ("flow-v", "")
        is_horizontal = container.layout == "flow-h"

        for i, cname in enumerate(child_names):
            # First child aligns to container
            if i == 0:
                if is_vertical:
                    self.constraints.append(Constraint(cname, "center-x", container.name, "center-x"))
                    # Align first child's top to container top
                    self.constraints.append(Constraint(cname, "top", container.name, "top"))
                elif is_horizontal:
                    self.constraints.append(Constraint(cname, "center-y", container.name, "center-y"))
                    self.constraints.append(Constraint(cname, "left", container.name, "left"))
            else:
                prev = child_names[i - 1]
                if is_vertical:
                    self.constraints.append(Constraint(cname, "center-x", container.name, "center-x"))
                    self.constraints.append(Constraint(
                        cname, "top", prev, "bottom",
                        offset=-gap, offset_unit="mm",
                    ))
                elif is_horizontal:
                    self.constraints.append(Constraint(cname, "center-y", container.name, "center-y"))
                    self.constraints.append(Constraint(
                        cname, "left", prev, "right",
                        offset=gap, offset_unit="mm",
                    ))

    def _apply_constraint(self, c: Constraint):
        target = self.objects.get(c.target_name)
        source = self.objects.get(c.source_name)
        if target is None or source is None:
            return
        offset_mm = _offset_to_mm(c.offset, c.offset_unit)
        value = source.get_anchor(c.source_anchor) + offset_mm
        target.set_anchor(c.target_anchor, value)

    def _compute_positioning_metadata(self, dag: DAG):
        """Analyze constraints to determine relative positioning for TikZ."""
        for name in self.objects:
            obj = self.objects[name]
            if obj.obj_type == ObjType.CONTAINER:
                continue
            constraints = dag.get_constraints_for(name)
            primary = None
            align = None
            for c in constraints:
                # Directional constraints
                direction = _constraint_to_direction(c)
                if direction:
                    dist = abs(_offset_to_mm(c.offset, c.offset_unit))
                    primary = (direction, c.source_name, dist)
                elif c.target_anchor in ("center-x",) and c.source_anchor in ("center-x",):
                    align = ("center-x", c.source_name)
                elif c.target_anchor in ("center-y",) and c.source_anchor in ("center-y",):
                    align = ("center-y", c.source_name)
            if primary:
                obj.pos_direction, obj.pos_reference, obj.pos_distance = primary
            if align:
                obj.pos_align_direction, obj.pos_align_reference = align


def _constraint_to_direction(c: Constraint) -> str | None:
    """Map a constraint to a TikZ positioning direction."""
    # target.top = source.bottom ± offset → "below"
    if c.target_anchor == "top" and c.source_anchor == "bottom":
        return "below"
    if c.target_anchor == "bottom" and c.source_anchor == "top":
        return "above"
    if c.target_anchor == "left" and c.source_anchor == "right":
        return "right"
    if c.target_anchor == "right" and c.source_anchor == "left":
        return "left"
    return None


def _parse_dimension(val: str) -> float:
    """Parse a dimension string like '14cm' or '6mm' to mm."""
    val = str(val).strip()
    if val.endswith("mm"):
        return float(val[:-2])
    if val.endswith("cm"):
        return float(val[:-2]) * 10.0
    if val.endswith("pt"):
        return float(val[:-2]) * 0.3528
    try:
        return float(val)
    except ValueError:
        return 0.0


def resolve(figure: FigureDecl) -> FlatIR:
    return Resolver().resolve(figure)
