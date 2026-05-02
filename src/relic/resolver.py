"""Constraint resolver — dispatches to RankResolver with fallback."""

from __future__ import annotations

import sys

from .ast_nodes import (
    ArrowDecl, ContainerDecl, ConstraintExpr, FigureDecl, ObjectDecl,
)
from .constraints import Constraint
from .dag import DAG, build_dag
from .errors import ResolveError
from .ir import FlatIR
from .objects import ArrowObject, LayoutObject, ObjType
from .rank_resolver import RankResolver


def resolve(figure: FigureDecl) -> FlatIR:
    """Resolve a figure AST into a FlatIR.

    Uses the rank-based resolver by default. Falls back to the legacy
    constraint-based resolver for complex cases.
    """
    try:
        resolver = RankResolver()
        return resolver.resolve(figure)
    except ResolveError:
        raise  # Don't fall back for resolve errors (bad references)
    except Exception as e:
        print(f"[resolver] Rank resolver failed ({e}), falling back to legacy resolver", file=sys.stderr)
        return _legacy_resolve(figure)


# ─── Legacy Constraint Resolver (fallback) ───

_ML_TYPE_MAP = {
    "add": ObjType.ML_ADD,
    "multiply": ObjType.ML_MULTIPLY,
    "concat": ObjType.ML_CONCAT,
    "softmax": ObjType.ML_SOFTMAX,
    "dropout": ObjType.ML_DROPOUT,
}

_TYPE_MAP = {
    "tensor3d": ObjType.TENSOR3D,
}

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


class _LegacyResolver:
    """Legacy constraint-based resolver (kept as fallback)."""

    def __init__(self):
        self.objects: dict[str, LayoutObject] = {}
        self.arrows: list[ArrowObject] = []
        self.constraints: list[Constraint] = []
        self.theme: str = "academic"
        self.figure_name: str = ""
        self.figure_width: float = 140.0
        self._container_anchors: set[str] = set()

    def resolve(self, figure: FigureDecl) -> FlatIR:
        self.figure_name = figure.name
        for p in figure.properties:
            if p.key == "theme":
                self.theme = str(p.value)
            elif p.key == "width":
                val = str(p.value)
                self.figure_width = _parse_dimension(val)

        self._register_children(figure.children)
        self._collect_constraints(figure.children)
        self._apply_flow_layouts(figure.children)

        dag = build_dag(self.constraints, set(self.objects.keys()))
        order = dag.topological_sort()

        for name in order:
            constraints = dag.get_constraints_for(name)
            for c in constraints:
                self._apply_constraint(c)

        self._compute_container_bounds()

        for name in order:
            constraints = dag.get_constraints_for(name)
            for c in constraints:
                source_obj = self.objects.get(c.source_name)
                if source_obj and source_obj.obj_type == ObjType.CONTAINER:
                    self._apply_constraint(c)
                elif c.source_name in self._container_anchors:
                    self._apply_constraint(c)

        self._resolve_overlaps()

        from .router import ArrowRouter
        router = ArrowRouter()
        router.route_all(self.objects, self.arrows)

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
                    style=child.style, label=child.label,
                    route=child.route, label_pos=child.label_pos,
                    line=child.line,
                ))

    def _register_object(self, decl: ObjectDecl, parent: str = ""):
        props = _resolve_props(decl)
        obj_type = _ML_TYPE_MAP.get(decl.obj_type) or _TYPE_MAP.get(decl.obj_type) or ObjType[decl.obj_type.upper()]
        obj = LayoutObject(
            name=decl.name, obj_type=obj_type,
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
        if obj_type == ObjType.IMAGE:
            obj.src = str(props.get("src", ""))
            w = props.get("width", "")
            if isinstance(w, str) and any(w.endswith(u) for u in ('mm', 'cm', 'pt')):
                obj.image_width = w
        if "ghost" in props and props["ghost"]:
            obj.opacity = 0.2
        elif "opacity" in props:
            obj.opacity = float(props["opacity"])
        if "shadow" in props and props["shadow"]:
            obj.shadow = True
        if "depth" in props and isinstance(props["depth"], (int, float)):
            obj.depth = float(props["depth"])
        for key in ("annotate-top", "annotate-right", "annotate-bottom", "annotate-left"):
            if key in props:
                direction = key.replace("annotate-", "")
                obj.annotations[direction] = str(props[key])
        self.objects[decl.name] = obj
        self._register_children(decl.children)

    def _register_container(self, decl: ContainerDecl, parent: str = ""):
        props = _resolve_props(decl)
        gap = 6.0
        if "gap" in props:
            val = str(props["gap"])
            gap = _parse_dimension(val)
        obj = LayoutObject(
            name=decl.name, obj_type=ObjType.CONTAINER,
            layout=decl.layout, gap=gap, parent=parent,
            label=str(props.get("label", "")),
        )
        if "ghost" in props and props["ghost"]:
            obj.opacity = 0.2
        elif "opacity" in props:
            obj.opacity = float(props["opacity"])
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
                c = Constraint(
                    target_name=child.target.object_name,
                    target_anchor=child.target.anchor,
                    source_name=child.source.object_name,
                    source_anchor=child.source.anchor,
                    offset=child.offset,
                    offset_unit=child.offset_unit,
                )
                self.constraints.append(c)
                if child.source.object_name in self.objects:
                    src_obj = self.objects[child.source.object_name]
                    if src_obj.obj_type == ObjType.CONTAINER:
                        self._container_anchors.add(child.source.object_name)
            elif isinstance(child, ContainerDecl):
                self._collect_constraints(child.children)
            elif isinstance(child, ObjectDecl):
                self._collect_constraints(child.children)

    def _apply_flow_layouts(self, children: list):
        for child in children:
            if isinstance(child, ContainerDecl):
                obj = self.objects.get(child.name)
                if obj and obj.children:
                    self._layout_flow_container(obj, child)
                self._apply_flow_layouts(child.children)

    def _layout_flow_container(self, container: LayoutObject, decl: ContainerDecl):
        child_names = container.children
        if len(child_names) < 2:
            if child_names:
                cname = child_names[0]
                self.constraints.append(Constraint(cname, "center-x", container.name, "center-x"))
                self.constraints.append(Constraint(cname, "center-y", container.name, "center-y"))
            return
        gap = container.gap
        is_vertical = container.layout in ("flow-v", "")
        is_horizontal = container.layout == "flow-h"
        for i, cname in enumerate(child_names):
            if i == 0:
                if is_vertical:
                    self.constraints.append(Constraint(cname, "center-x", container.name, "center-x"))
                    self.constraints.append(Constraint(cname, "top", container.name, "top"))
                elif is_horizontal:
                    self.constraints.append(Constraint(cname, "center-y", container.name, "center-y"))
                    self.constraints.append(Constraint(cname, "left", container.name, "left"))
            else:
                prev = child_names[i - 1]
                if is_vertical:
                    self.constraints.append(Constraint(cname, "center-x", container.name, "center-x"))
                    self.constraints.append(Constraint(cname, "top", prev, "bottom", offset=-gap, offset_unit="mm"))
                elif is_horizontal:
                    self.constraints.append(Constraint(cname, "center-y", container.name, "center-y"))
                    self.constraints.append(Constraint(cname, "left", prev, "right", offset=gap, offset_unit="mm"))

    def _apply_constraint(self, c: Constraint):
        target = self.objects.get(c.target_name)
        source = self.objects.get(c.source_name)
        if target is None or source is None:
            return
        offset_mm = _offset_to_mm(c.offset, c.offset_unit)
        value = source.get_anchor(c.source_anchor) + offset_mm
        target.set_anchor(c.target_anchor, value)

    def _compute_container_bounds(self):
        for name, obj in self.objects.items():
            if obj.obj_type == ObjType.CONTAINER and obj.children:
                child_objs = [self.objects[c] for c in obj.children if c in self.objects]
                if child_objs:
                    bounds_left = min(c.left for c in child_objs)
                    bounds_right = max(c.right for c in child_objs)
                    bounds_top = max(c.top for c in child_objs)
                    bounds_bottom = min(c.bottom for c in child_objs)
                    obj.x = (bounds_left + bounds_right) / 2
                    obj.y = (bounds_top + bounds_bottom) / 2
                    obj.width = bounds_right - bounds_left
                    obj.height = bounds_top - bounds_bottom

    def _resolve_overlaps(self, max_iterations: int = 50):
        for iteration in range(max_iterations):
            moved = False
            leaf_objects = [
                (name, obj) for name, obj in self.objects.items()
                if obj.obj_type != ObjType.CONTAINER
                and not (0 < obj.opacity < 0.5)
            ]
            for i, (name_a, a) in enumerate(leaf_objects):
                for j, (name_b, b) in enumerate(leaf_objects):
                    if i >= j:
                        continue
                    if a.parent and a.parent == b.parent:
                        parent_obj = self.objects.get(a.parent)
                        if parent_obj and parent_obj.layout in ("flow-v", "flow-h", ""):
                            continue
                    overlap_x = min(a.right, b.right) - max(a.left, b.left)
                    overlap_y = min(a.top, b.top) - max(a.bottom, b.bottom)
                    if overlap_x > 0 and overlap_y > 0:
                        moved = True
                        print(f"[resolver] Overlap: '{name_a}' and '{name_b}'", file=sys.stderr)
                        if overlap_x < overlap_y:
                            push = overlap_x / 2 + 2.0
                            if a.x <= b.x:
                                a.x -= push
                                b.x += push
                            else:
                                a.x += push
                                b.x -= push
                        else:
                            push = overlap_y / 2 + 2.0
                            if a.y <= b.y:
                                a.y -= push
                                b.y += push
                            else:
                                a.y += push
                                b.y -= push
            if not moved:
                break

    def _compute_positioning_metadata(self, dag: DAG):
        cross_positioned = set()
        for c in self.constraints:
            direction = _constraint_to_direction(c)
            if not direction:
                continue
            target_obj = self.objects.get(c.target_name)
            source_obj = self.objects.get(c.source_name)
            if target_obj is None or source_obj is None:
                continue
            target_is_container = target_obj.obj_type == ObjType.CONTAINER
            source_is_container = source_obj.obj_type == ObjType.CONTAINER
            if target_is_container:
                target_leaf = self._first_leaf(c.target_name)
                if target_leaf is None:
                    continue
                if source_is_container:
                    ref = self._first_leaf(c.source_name)
                else:
                    ref = c.source_name
                if ref is None:
                    ref = c.source_name
                dist = abs(_offset_to_mm(c.offset, c.offset_unit))
                leaf_obj = self.objects.get(target_leaf)
                if leaf_obj:
                    leaf_obj.pos_direction = direction
                    leaf_obj.pos_reference = ref
                    leaf_obj.pos_distance = dist
                    cross_positioned.add(target_leaf)
        for name in self.objects:
            if name in cross_positioned:
                continue
            obj = self.objects[name]
            if obj.obj_type == ObjType.CONTAINER:
                continue
            constraints = dag.get_constraints_for(name)
            primary = None
            align = None
            for c in constraints:
                source_obj = self.objects.get(c.source_name)
                direction = _constraint_to_direction(c)
                if direction:
                    if source_obj and source_obj.obj_type == ObjType.CONTAINER:
                        ref = self._last_leaf(c.source_name)
                        if ref is None:
                            ref = c.source_name
                    else:
                        ref = c.source_name
                    dist = abs(_offset_to_mm(c.offset, c.offset_unit))
                    primary = (direction, ref, dist)
                elif c.target_anchor in ("center-x",) and c.source_anchor in ("center-x",):
                    if source_obj and source_obj.obj_type == ObjType.CONTAINER:
                        align_ref = c.source_name
                    else:
                        align_ref = c.source_name
                    align = ("center-x", align_ref)
                elif c.target_anchor in ("center-y",) and c.source_anchor in ("center-y",):
                    if source_obj and source_obj.obj_type == ObjType.CONTAINER:
                        align_ref = c.source_name
                    else:
                        align_ref = c.source_name
                    align = ("center-y", align_ref)
            if primary:
                obj.pos_direction, obj.pos_reference, obj.pos_distance = primary
            if align:
                obj.pos_align_direction, obj.pos_align_reference = align

    def _first_leaf(self, container_name: str) -> str | None:
        obj = self.objects.get(container_name)
        if not obj or not obj.children:
            return None
        for cname in obj.children:
            child = self.objects.get(cname)
            if child and child.obj_type == ObjType.CONTAINER:
                leaf = self._first_leaf(cname)
                if leaf:
                    return leaf
            elif child:
                return cname
        return None

    def _last_leaf(self, container_name: str) -> str | None:
        obj = self.objects.get(container_name)
        if not obj or not obj.children:
            return None
        for cname in reversed(obj.children):
            child = self.objects.get(cname)
            if child and child.obj_type == ObjType.CONTAINER:
                leaf = self._last_leaf(cname)
                if leaf:
                    return leaf
            elif child:
                return cname
        return None


def _constraint_to_direction(c: Constraint) -> str | None:
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


def _legacy_resolve(figure: FigureDecl) -> FlatIR:
    return _LegacyResolver().resolve(figure)
