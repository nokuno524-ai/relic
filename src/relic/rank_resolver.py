"""Rank-based resolver — three-pass layout system.

Pass 1: Rank Assignment (topology)
Pass 2: Geometry Solver (flexbox centering)
Pass 3: Arrow Routing (Manhattan-style)

Inspired by TeX box-and-glue, CSS Flexbox, and Graphviz dot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ast_nodes import ArrowDecl, ContainerDecl, ConstraintExpr, FigureDecl, ObjectDecl
from .constraints import Constraint
from .dag import DAG, build_dag
from .errors import ResolveError
from .ir import FlatIR
from .objects import ArrowObject, LayoutObject, ObjType, Waypoint


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


@dataclass
class Rank:
    """A horizontal layer of nodes."""
    index: int
    nodes: list[str] = field(default_factory=list)
    y: float = 0.0


@dataclass
class RankedLayout:
    """Complete ranked layout data."""
    ranks: list[Rank] = field(default_factory=list)
    node_rank: dict[str, int] = field(default_factory=dict)  # node_name -> rank_index
    # Parent mapping: child -> parent (from arrows or flow layout)
    node_parent: dict[str, str] = field(default_factory=dict)
    # Container membership
    node_container: dict[str, str] = field(default_factory=dict)  # node -> container name


class RankResolver:
    """Three-pass rank-based layout resolver."""

    def __init__(self):
        self.objects: dict[str, LayoutObject] = {}
        self.arrows: list[ArrowObject] = []
        self.constraints: list[Constraint] = []
        self.theme: str = "academic"
        self.figure_name: str = ""
        self.figure_width: float = 140.0
        self._containers: dict[str, ContainerDecl] = {}
        self._flow_h_containers: dict[str, list[str]] = {}  # container -> child names
        self._flow_v_containers: dict[str, list[str]] = {}  # container -> child names
        self._standalone_nodes: list[str] = []  # nodes not in any container
        self._arrow_pairs: list[tuple[str, str]] = []  # (source, target) from arrow decls
        self._bus_groups: list[tuple[str, str, str]] = []  # (group_id, source, target)
        self._bus_map: dict = {}
        self._callouts: list = []  # CalloutInfo list

    def resolve(self, figure: FigureDecl) -> FlatIR:
        """Resolve a figure AST into a FlatIR using rank-based layout."""
        self.figure_name = figure.name
        for p in figure.properties:
            if p.key == "theme":
                self.theme = str(p.value)
            elif p.key == "width":
                val = str(p.value)
                self.figure_width = _parse_dimension(val)

        # Register all objects and arrows
        self._register_all(figure.children)

        # Collect constraints
        self._collect_constraints(figure.children)

        # Generate flow layout constraints (same as legacy)
        self._apply_flow_layouts(figure.children)

        # Collect container info
        self._collect_containers(figure.children)

        # Collect arrow pairs
        self._collect_arrows(figure.children)

        # Collect callouts
        self._collect_callouts(figure.children)

        # Pass 1: Assign ranks
        ranked = self._assign_ranks()

        # Pass 2: Solve geometry
        self._solve_geometry(ranked)

        # Resolve overlaps
        self._resolve_overlaps()

        # Pass 3: Route arrows (Manhattan)
        self._route_arrows(ranked)

        # Compute container bounding boxes
        self._compute_container_bounds()

        # Compute positioning metadata for TikZ
        dag = build_dag(self.constraints, set(self.objects.keys()))
        self._compute_positioning_metadata(ranked, dag)

        return FlatIR(
            objects=self.objects,
            arrows=self.arrows,
            theme=self.theme,
            figure_name=self.figure_name,
            width=self.figure_width,
            callouts=self._callouts,
        )

    # ─── Registration ───

    def _register_all(self, children: list):
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
            name=decl.name,
            obj_type=obj_type,
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
        if "stack" in props and isinstance(props["stack"], (int, float)):
            obj.stack_count = int(props["stack"])
        if "stack-label" in props:
            obj.stack_label = str(props["stack-label"])
        # Parse annotations
        for key in ("annotate-top", "annotate-right", "annotate-bottom", "annotate-left"):
            if key in props:
                direction = key.replace("annotate-", "")
                obj.annotations[direction] = str(props[key])
        self.objects[decl.name] = obj
        if parent:
            obj.parent = parent
        self._register_all(decl.children)

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
        if "ghost" in props and props["ghost"]:
            obj.opacity = 0.2
        elif "opacity" in props:
            obj.opacity = float(props["opacity"])
        if "stack" in props and isinstance(props["stack"], (int, float)):
            obj.stack_count = int(props["stack"])
        if "stack-label" in props:
            obj.stack_label = str(props["stack-label"])
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
            elif hasattr(child, 'children'):
                self._collect_constraints(child.children)

    def _collect_containers(self, children: list):
        """Categorize containers by layout type and track membership."""
        for child in children:
            if isinstance(child, ContainerDecl):
                obj = self.objects.get(child.name)
                if not obj:
                    continue
                if obj.layout == "flow-h":
                    self._flow_h_containers[child.name] = obj.children[:]
                    for cname in obj.children:
                        self.objects[cname].parent = child.name
                elif obj.layout in ("flow-v", ""):
                    self._flow_v_containers[child.name] = obj.children[:]
                    for cname in obj.children:
                        self.objects[cname].parent = child.name
                self._collect_containers(child.children)
            elif isinstance(child, ObjectDecl):
                # Track standalone nodes (no container parent set)
                if child.name in self.objects and not self.objects[child.name].parent:
                    self._standalone_nodes.append(child.name)
                self._collect_containers(child.children)

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

    def _collect_arrows(self, children: list):
        """Collect arrow source/target pairs."""
        bus_groups: dict[str, list[str]] = {}  # target -> [sources]
        for child in children:
            if isinstance(child, ArrowDecl):
                # Validate references with fuzzy matching
                all_names = list(self.objects.keys())
                if child.source not in self.objects:
                    from .errors import suggest_names
                    suggestions = suggest_names(child.source, all_names)
                    raise ResolveError(
                        f"Arrow source '{child.source}' does not exist.",
                        suggestions=suggestions,
                    )
                if child.target not in self.objects:
                    from .errors import suggest_names
                    suggestions = suggest_names(child.target, all_names)
                    raise ResolveError(
                        f"Arrow target '{child.target}' does not exist.",
                        suggestions=suggestions,
                    )
                self._arrow_pairs.append((child.source, child.target))
                # Track bus routing
                if child.route == "bus":
                    bus_groups.setdefault(child.target, []).append(child.source)
            elif hasattr(child, 'children'):
                self._collect_arrows(child.children)

        # Assign bus_group IDs for targets with 3+ sources
        import uuid
        for target, sources in bus_groups.items():
            if len(sources) >= 2:
                gid = f"bus_{uuid.uuid4().hex[:6]}"
                for src in sources:
                    # Find matching arrow in self.arrows (set later)
                    self._bus_groups.append((gid, src, target))

        self._bus_map = {}  # populated later during routing

    def _collect_callouts(self, children: list):
        """Collect callout declarations."""
        from .ast_nodes import CalloutStmt
        from .ir import CalloutInfo
        for child in children:
            if isinstance(child, CalloutStmt):
                self._callouts.append(CalloutInfo(
                    source=child.source,
                    target=child.target,
                    style=child.style,
                    fill=child.fill,
                ))
                # Position the target to the right of the source
                if child.source in self.objects and child.target in self.objects:
                    src = self.objects[child.source]
                    tgt = self.objects[child.target]
                    tgt.x = src.x + src.width / 2 + 40 + tgt.width / 2
                    tgt.y = src.y
            elif hasattr(child, 'children'):
                self._collect_callouts(child.children)

    # ─── Pass 1: Rank Assignment ───

    def _assign_ranks(self) -> RankedLayout:
        """Assign every node to a rank based on topology."""
        ranked = RankedLayout()
        node_rank: dict[str, int] = {}

        # 1. flow-h containers: all children in same rank
        for cname, children in self._flow_h_containers.items():
            # Assign the container itself to the same rank as its children
            # but only if it's referenced in constraints
            for child_name in children:
                if child_name not in node_rank:
                    # Use the first child's rank or create a new one
                    if cname in node_rank:
                        node_rank[child_name] = node_rank[cname]
                    else:
                        # Find the max rank used so far + 1, or start from a good position
                        rank_idx = max(node_rank.values(), default=-1) + 1
                        node_rank[child_name] = rank_idx
                        node_rank[cname] = rank_idx

        # 2. flow-v containers: children in sequential ranks
        for cname, children in self._flow_v_containers.items():
            for i, child_name in enumerate(children):
                if child_name not in node_rank:
                    if cname in node_rank:
                        node_rank[child_name] = node_rank[cname] + i
                    else:
                        # Find what rank the container should be at
                        rank_idx = max(node_rank.values(), default=-1) + 1
                        node_rank[cname] = rank_idx
                        node_rank[child_name] = rank_idx + i

        # 2b. Parallel containers: right-of/left-of → same starting rank
        # Build a map of horizontal constraints between containers
        parallel_pairs: list[tuple[str, str]] = []  # (left, right) container names
        for c in self.constraints:
            if c.target_anchor == "left" and c.source_anchor == "right":
                # target is right-of source
                if c.target_name in self._flow_v_containers and c.source_name in self._flow_v_containers:
                    parallel_pairs.append((c.source_name, c.target_name))
            elif c.target_anchor == "right" and c.source_anchor == "left":
                if c.target_name in self._flow_v_containers and c.source_name in self._flow_v_containers:
                    parallel_pairs.append((c.target_name, c.source_name))

        for left_c, right_c in parallel_pairs:
            left_children = self._flow_v_containers.get(left_c, [])
            right_children = self._flow_v_containers.get(right_c, [])
            if not left_children or not right_children:
                continue
            # Find the starting rank of the left container's first child
            if left_children[0] in node_rank:
                base_rank = node_rank[left_children[0]]
                # Check if container node itself has a rank
            elif left_c in node_rank:
                base_rank = node_rank[left_c]
            else:
                continue
            # Reassign right container's children to parallel ranks
            for i, child_name in enumerate(right_children):
                desired_rank = base_rank + i
                old_rank = node_rank.get(child_name, None)
                if old_rank is not None and old_rank != desired_rank:
                    # Shift this node and all nodes in its container that come after
                    shift = desired_rank - old_rank
                    for j, sibling in enumerate(right_children[i:]):
                        if sibling in node_rank:
                            node_rank[sibling] = node_rank[sibling] + shift
            # Also align the container node
            if right_c in node_rank and left_c in node_rank:
                node_rank[right_c] = node_rank[left_c]

        # 3. Standalone nodes: determine rank from constraints
        # Build a dependency graph for rank assignment
        # X.top = Y.bottom + gap → X is one rank below Y
        # X.center-x = Y.center-x → same rank (or X is aligned with Y)
        rank_constraints: list[tuple[str, str, str]] = []  # (target, source, type)
        for c in self.constraints:
            src_obj = self.objects.get(c.source_name)
            tgt_obj = self.objects.get(c.target_name)
            if src_obj is None or tgt_obj is None:
                continue
            # Skip container-internal constraints (already handled by flow layout)
            if tgt_obj.parent and tgt_obj.parent == src_obj.name:
                continue
            if tgt_obj.parent and src_obj.parent and tgt_obj.parent == src_obj.parent:
                parent_obj = self.objects.get(tgt_obj.parent)
                if parent_obj and parent_obj.layout in ("flow-h", "flow-v", ""):
                    continue

            if c.target_anchor == "top" and c.source_anchor == "bottom":
                rank_constraints.append((c.target_name, c.source_name, "below"))
            elif c.target_anchor == "bottom" and c.source_anchor == "top":
                rank_constraints.append((c.target_name, c.source_name, "above"))
            elif c.target_anchor in ("center-x",) and c.source_anchor in ("center-x",):
                rank_constraints.append((c.target_name, c.source_name, "align-x"))
            elif c.target_anchor in ("center-y",) and c.source_anchor in ("center-y",):
                rank_constraints.append((c.target_name, c.source_name, "align-y"))
            elif c.target_anchor == "left" and c.source_anchor == "right":
                rank_constraints.append((c.target_name, c.source_name, "right-of"))
            elif c.target_anchor == "right" and c.source_anchor == "left":
                rank_constraints.append((c.target_name, c.source_name, "left-of"))

        # Process rank constraints
        # First pass: assign ranks based on "below" constraints
        for target, source, ctype in rank_constraints:
            if ctype == "below":
                # For containers, use the last child's rank + 1 as effective "bottom"
                source_rank = node_rank.get(source)
                if source_rank is not None and source in self._flow_v_containers:
                    children = self._flow_v_containers[source]
                    if children:
                        last_child_rank = max(node_rank.get(c, source_rank) for c in children)
                        source_rank = last_child_rank
                if source_rank is not None:
                    if target not in node_rank:
                        node_rank[target] = source_rank + 1
                    else:
                        # target already has a rank; ensure it's at least source_rank+1
                        node_rank[target] = max(node_rank[target], source_rank + 1)
                elif target in node_rank:
                    node_rank[source] = node_rank[target] - 1
            elif ctype == "above":
                if source in node_rank:
                    if target not in node_rank:
                        node_rank[target] = node_rank[source] - 1
                    else:
                        node_rank[target] = min(node_rank[target], node_rank[source] - 1)
                elif target in node_rank:
                    node_rank[source] = node_rank[target] + 1
            elif ctype == "align-x" or ctype == "align-y":
                # Same rank
                if source in node_rank and target not in node_rank:
                    node_rank[target] = node_rank[source]
                elif target in node_rank and source not in node_rank:
                    node_rank[source] = node_rank[target]
                elif source not in node_rank and target not in node_rank:
                    rank_idx = max(node_rank.values(), default=-1) + 1
                    node_rank[target] = rank_idx
                    node_rank[source] = rank_idx
            elif ctype in ("right-of", "left-of"):
                # Same rank for horizontal neighbors
                if source in node_rank and target not in node_rank:
                    node_rank[target] = node_rank[source]
                elif target in node_rank and source not in node_rank:
                    node_rank[source] = node_rank[target]
                elif source not in node_rank and target not in node_rank:
                    rank_idx = max(node_rank.values(), default=-1) + 1
                    node_rank[target] = rank_idx
                    node_rank[source] = rank_idx

        # Assign remaining nodes that don't have a rank yet
        for name in self.objects:
            if name not in node_rank and self.objects[name].obj_type != ObjType.CONTAINER:
                if not self.objects[name].parent:
                    # Try to infer rank from arrows
                    arrow_rank = self._infer_rank_from_arrows(name, node_rank)
                    if arrow_rank is not None:
                        node_rank[name] = arrow_rank
                    else:
                        rank_idx = max(node_rank.values(), default=-1) + 1
                        node_rank[name] = rank_idx

        # Normalize ranks to start from 0
        if node_rank:
            min_rank = min(node_rank.values())
            if min_rank != 0:
                for name in node_rank:
                    node_rank[name] -= min_rank

        # Build rank list
        max_rank = max(node_rank.values(), default=0)
        ranks: list[Rank] = []
        for i in range(max_rank + 1):
            ranks.append(Rank(index=i))

        # Add non-container nodes to ranks
        for name, rank_idx in node_rank.items():
            obj = self.objects.get(name)
            if obj and obj.obj_type != ObjType.CONTAINER:
                if rank_idx < len(ranks):
                    ranks[rank_idx].nodes.append(name)
                ranked.node_rank[name] = rank_idx

        ranked.ranks = ranks
        ranked.node_rank = node_rank

        # Build parent mapping from arrows
        for src, tgt in self._arrow_pairs:
            if tgt in node_rank and src in node_rank:
                if node_rank[tgt] > node_rank[src]:
                    ranked.node_parent[tgt] = src
                elif node_rank[src] > node_rank[tgt]:
                    ranked.node_parent[src] = tgt

        return ranked

    def _infer_rank_from_arrows(self, name: str, node_rank: dict[str, int]) -> int | None:
        """Try to infer a node's rank from its arrow connections."""
        for src, tgt in self._arrow_pairs:
            if src == name and tgt in node_rank:
                return node_rank[tgt] - 1  # source is above target
            if tgt == name and src in node_rank:
                return node_rank[src] + 1  # target is below source
        return None

    # ─── Pass 2: Geometry Solver ───

    def _solve_geometry(self, ranked: RankedLayout):
        """Position nodes within ranks using rank-based Y + constraint-based X."""
        if not ranked.ranks:
            return

        DEFAULT_RANK_GAP = 12.0  # mm

        # Step 1: Compute Y positions purely from rank structure
        self._compute_rank_y_positions(ranked, DEFAULT_RANK_GAP)

        # Step 2: Compute X positions within each rank
        # Use constraint DAG for nodes with explicit constraints,
        # flexbox centering for others
        dag = build_dag(self.constraints, set(self.objects.keys()))

        for rank in ranked.ranks:
            if not rank.nodes:
                continue

            has_explicit_x = self._has_explicit_x_constraints(rank)

            if has_explicit_x:
                self._apply_x_constraints_for_rank(rank, dag)
            else:
                flow_h_groups = self._find_flow_h_groups_in_rank(rank)
                if flow_h_groups:
                    self._layout_rank_with_flow_h(rank, flow_h_groups, ranked)
                else:
                    self._layout_simple_rank(rank, ranked)

        # Apply alignment constraints
        self._apply_alignment_constraints(ranked)

        # Uniform rank sizing — same-rank boxes get matching widths
        self._uniform_rank_sizing(ranked)

    def _uniform_rank_sizing(self, ranked: RankedLayout):
        """Set all non-container nodes in each rank to the max width in that rank."""
        for rank in ranked.ranks:
            boxes = [n for n in rank.nodes
                     if n in self.objects and self.objects[n].obj_type != ObjType.CONTAINER]
            if len(boxes) < 2:
                continue
            max_w = max(self.objects[n].width for n in boxes)
            for n in boxes:
                self.objects[n].width = max_w

    def _compute_rank_y_positions(self, ranked: RankedLayout, default_gap: float):
        """Compute Y positions for each rank based on rank gap."""
        rank_gaps = self._compute_rank_gaps(ranked, default_gap)

        for rank in ranked.ranks:
            if not rank.nodes:
                continue

            if rank.index == 0:
                rank.y = 0.0
            else:
                prev_rank = ranked.ranks[rank.index - 1]
                # Bottom of previous rank (most negative y - h/2)
                max_prev_bottom = min(
                    (self.objects[n].y - self.objects[n].height / 2 for n in prev_rank.nodes
                     if n in self.objects),
                    default=0.0
                )
                gap = rank_gaps.get(rank.index, default_gap)
                # The gap is the visual distance from prev bottom to current top
                # In y-down: Y.top = prev_bottom - gap
                # Y.top = Y.y + h/2, so Y.y = prev_bottom - gap - h/2
                # Use the max height in this rank
                max_h = max(self.objects[n].height for n in rank.nodes if n in self.objects)
                rank.y = max_prev_bottom - gap - max_h / 2

            # Set all nodes in this rank to rank.y
            for node_name in rank.nodes:
                node = self.objects.get(node_name)
                if node:
                    node.y = rank.y

    def _has_explicit_x_constraints(self, rank: Rank) -> bool:
        """Check if any node in this rank has explicit left/right/center-x constraints."""
        for c in self.constraints:
            if c.target_name in rank.nodes:
                if c.target_anchor in ("left", "right", "center-x", "center"):
                    return True
            if c.source_name in rank.nodes:
                if c.source_anchor in ("left", "right", "center-x", "center"):
                    return True
        return False

    def _apply_x_constraints_for_rank(self, rank: Rank, dag: DAG):
        """Apply constraint-based X positioning for nodes in a rank."""
        for node_name in rank.nodes:
            constraints = dag.get_constraints_for(node_name)
            for c in constraints:
                if c.target_anchor in ("left", "right", "center-x", "center"):
                    self._apply_constraint(c)

    def _apply_constraint(self, c: Constraint):
        """Apply a single constraint."""
        target = self.objects.get(c.target_name)
        source = self.objects.get(c.source_name)
        if target is None or source is None:
            return
        offset_mm = _offset_to_mm(c.offset, c.offset_unit)
        value = source.get_anchor(c.source_anchor) + offset_mm
        target.set_anchor(c.target_anchor, value)

    def _compute_rank_gaps(self, ranked: RankedLayout, default: float) -> dict[int, float]:
        """Compute the gap between consecutive ranks from constraints."""
        gaps: dict[int, float] = {}
        for c in self.constraints:
            if c.target_anchor == "top" and c.source_anchor == "bottom":
                target_rank = ranked.node_rank.get(c.target_name)
                source_rank = ranked.node_rank.get(c.source_name)
                if target_rank is not None and source_rank is not None:
                    if target_rank == source_rank + 1:
                        offset_mm = _offset_to_mm(c.offset, c.offset_unit)
                        gaps[target_rank] = abs(offset_mm)
        return gaps

    def _find_flow_h_groups_in_rank(self, rank: Rank) -> list[list[str]]:
        """Find groups of nodes in this rank that belong to the same flow-h container."""
        groups: dict[str, list[str]] = {}
        ungrouped: list[str] = []

        for node_name in rank.nodes:
            obj = self.objects.get(node_name)
            if obj and obj.parent:
                parent = self.objects.get(obj.parent)
                if parent and parent.layout == "flow-h":
                    groups.setdefault(obj.parent, []).append(node_name)
                    continue
            ungrouped.append(node_name)

        result = list(groups.values())
        # Add single ungrouped nodes as singleton groups
        for n in ungrouped:
            result.append([n])
        return result

    def _layout_rank_with_flow_h(self, rank: Rank, groups: list[list[str]], ranked: RankedLayout):
        """Layout a rank that contains flow-h container groups."""
        # Compute total width including gaps between groups
        group_widths: list[float] = []
        GROUP_GAP = 30.0  # mm between groups

        for group in groups:
            if len(group) > 1:
                # Find parent container for gap
                obj = self.objects[group[0]]
                parent = self.objects.get(obj.parent) if obj.parent else None
                gap = parent.gap if parent else 6.0
                width = sum(self.objects[n].width for n in group) + gap * (len(group) - 1)
            else:
                width = self.objects[group[0]].width
            group_widths.append(width)

        total_width = sum(group_widths) + GROUP_GAP * (len(groups) - 1)
        start_x = -total_width / 2

        for i, group in enumerate(groups):
            group_width = group_widths[i]
            group_center_x = start_x + group_width / 2

            if len(group) > 1:
                obj = self.objects[group[0]]
                parent = self.objects.get(obj.parent) if obj.parent else None
                gap = parent.gap if parent else 6.0
                # Layout within group
                group_start = start_x
                for node_name in group:
                    node = self.objects[node_name]
                    node.x = group_start + node.width / 2
                    node.y = rank.y
                    group_start += node.width + gap
            else:
                node = self.objects[group[0]]
                node.x = group_center_x
                node.y = rank.y

            start_x += group_width + GROUP_GAP

    def _layout_simple_rank(self, rank: Rank, ranked: RankedLayout):
        """Layout a rank with no flow-h containers — just center nodes."""
        if len(rank.nodes) == 1:
            node = self.objects[rank.nodes[0]]
            node.x = 0.0
            node.y = rank.y
            return

        # Multiple standalone nodes: position based on parent alignment
        DEFAULT_GAP = 15.0
        total_width = sum(self.objects[n].width for n in rank.nodes) + DEFAULT_GAP * (len(rank.nodes) - 1)
        start_x = -total_width / 2

        for node_name in rank.nodes:
            node = self.objects[node_name]
            node.x = start_x + node.width / 2
            node.y = rank.y
            start_x += node.width + DEFAULT_GAP

    def _apply_alignment_constraints(self, ranked: RankedLayout):
        """Apply center-x and center-y alignment constraints."""
        for c in self.constraints:
            target = self.objects.get(c.target_name)
            source = self.objects.get(c.source_name)
            if target is None or source is None:
                continue

            if c.target_anchor in ("left", "right") and c.source_anchor in ("left", "right"):
                offset_mm = _offset_to_mm(c.offset, c.offset_unit)
                value = source.get_anchor(c.source_anchor) + offset_mm
                if target.obj_type == ObjType.CONTAINER:
                    target.set_anchor(c.target_anchor, value)
                    # Re-position children that reference this container
                    for cname in target.children:
                        child = self.objects.get(cname)
                        if child and child.obj_type != ObjType.CONTAINER:
                            child.x = target.x
                else:
                    target.set_anchor(c.target_anchor, value)

            if c.target_anchor in ("center-x", "center") and c.source_anchor in ("center-x", "center"):
                offset_mm = _offset_to_mm(c.offset, c.offset_unit)
                if target.obj_type == ObjType.CONTAINER:
                    # Align container to source
                    target.x = source.x + offset_mm
                elif source.obj_type == ObjType.CONTAINER:
                    # Align target to container center
                    container_nodes = [self.objects[n] for n in source.children if n in self.objects and self.objects[n].obj_type != ObjType.CONTAINER]
                    if container_nodes:
                        center = sum(n.x for n in container_nodes) / len(container_nodes)
                        target.x = center + offset_mm
                    else:
                        target.x = source.x + offset_mm
                else:
                    target.x = source.x + offset_mm

            if c.target_anchor in ("center-y",) and c.source_anchor in ("center-y",):
                offset_mm = _offset_to_mm(c.offset, c.offset_unit)
                if target.obj_type == ObjType.CONTAINER:
                    target.y = source.y + offset_mm
                elif source.obj_type == ObjType.CONTAINER:
                    container_nodes = [self.objects[n] for n in source.children if n in self.objects and self.objects[n].obj_type != ObjType.CONTAINER]
                    if container_nodes:
                        center = sum(n.y for n in container_nodes) / len(container_nodes)
                        target.y = center + offset_mm
                    else:
                        target.y = source.y + offset_mm
                else:
                    target.y = source.y + offset_mm

    # ─── Pass 3: Arrow Routing ───

    def _route_arrows(self, ranked: RankedLayout):
        """Generate Manhattan-style arrow paths."""
        # Group arrows by target for bus routing
        target_counts: dict[str, list[int]] = {}
        for i, arrow in enumerate(self.arrows):
            target_counts.setdefault(arrow.target, []).append(i)

        for i, arrow in enumerate(self.arrows):
            src = self.objects.get(arrow.source)
            tgt = self.objects.get(arrow.target)
            if src is None or tgt is None:
                continue

            src_rank = ranked.node_rank.get(arrow.source, -1)
            tgt_rank = ranked.node_rank.get(arrow.target, -1)

            if src_rank == tgt_rank:
                # Intra-rank: horizontal arrow
                arrow.source_anchor = "right" if src.x < tgt.x else "left"
                arrow.target_anchor = "left" if src.x < tgt.x else "right"
                arrow.waypoints = []
            elif src_rank < tgt_rank:
                # Inter-rank: source above target
                dx = abs(src.x - tgt.x)
                siblings = target_counts.get(arrow.target, [])
                arrow.source_anchor = "top"  # bottom in visual (y-down)
                arrow.target_anchor = "bottom"  # top in visual (y-down)

                # Use straight line if source is roughly over target
                align_tolerance = min(src.width, tgt.width) / 2
                if dx < align_tolerance:
                    # Directly above: straight vertical
                    arrow.waypoints = []
                else:
                    # Offset: use Manhattan routing
                    if len(siblings) > 1:
                        idx = siblings.index(i)
                        n = len(siblings)
                        # Distribute entry points
                        if idx == 0:
                            # Center hit
                            arrow.waypoints = [Waypoint(type="l-bend-v")]
                        elif idx == 1:
                            # Left hit
                            arrow.target_anchor = "left"
                            arrow.waypoints = [Waypoint(type="l-bend-v")]
                        else:
                            # Right hit
                            arrow.target_anchor = "right"
                            arrow.waypoints = [Waypoint(type="l-bend-v")]
                    else:
                        arrow.waypoints = [Waypoint(type="l-bend-v")]
            else:
                # Source below target — reverse
                dx = abs(src.x - tgt.x)
                arrow.source_anchor = "bottom"
                arrow.target_anchor = "top"
                align_tolerance = min(src.width, tgt.width) / 2
                if dx < align_tolerance:
                    arrow.waypoints = []
                else:
                    arrow.waypoints = [Waypoint(type="l-bend-v")]

            arrow.auto_routed = True

    def _resolve_overlaps(self, max_iterations: int = 50):
        """Post-resolution pass: detect and fix overlapping objects."""
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

    # ─── Container Bounds ───

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

    # ─── Positioning Metadata for TikZ ───

    def _compute_positioning_metadata(self, ranked: RankedLayout, dag: DAG):
        """Compute relative positioning metadata for TikZ output.
        
        Priority:
        1. Parent-based (from arrows): node is "below" its arrow parent
        2. Rank-based: rank-0 nodes use middle anchor, others use closest reference
        3. Constraint-based: explicit left/right constraints (lowest priority)
        """
        # Build arrow parent map (only within same container)
        arrow_parents: dict[str, str] = {}
        for src, tgt in self._arrow_pairs:
            src_rank = ranked.node_rank.get(src, -1)
            tgt_rank = ranked.node_rank.get(tgt, -1)
            src_obj = self.objects.get(src)
            tgt_obj = self.objects.get(tgt)
            # Only use as parent if they're in the same container (or both standalone)
            same_family = (src_obj and tgt_obj and 
                          (src_obj.parent == tgt_obj.parent or 
                           (not src_obj.parent and not tgt_obj.parent)))
            if tgt_rank > src_rank and same_family:
                arrow_parents[tgt] = src
            elif src_rank > tgt_rank and same_family:
                arrow_parents[src] = tgt

        # Add flow-v container internal arrows as parents
        for cname, children in self._flow_v_containers.items():
            for i in range(len(children) - 1):
                src, tgt = children[i], children[i + 1]
                if tgt not in arrow_parents:
                    arrow_parents[tgt] = src

        positioned = set()

        # Rank 0: position relative to middle node
        if ranked.ranks:
            rank0 = ranked.ranks[0]
            if len(rank0.nodes) > 1:
                middle_node = self._find_middle_node(rank0, ranked)
                if middle_node:
                    positioned.add(middle_node)
                    for node_name in rank0.nodes:
                        if node_name in positioned:
                            continue
                        node = self.objects[node_name]
                        mid_obj = self.objects[middle_node]
                        if node.x < mid_obj.x:
                            node.pos_direction = "left"
                            node.pos_reference = middle_node
                            node.pos_distance = mid_obj.left - node.right
                        else:
                            node.pos_direction = "right"
                            node.pos_reference = middle_node
                            node.pos_distance = node.left - mid_obj.right
                        positioned.add(node_name)
            elif rank0.nodes:
                positioned.add(rank0.nodes[0])

        # Ranks > 0: prefer arrow-parent positioning
        for rank in ranked.ranks[1:]:
            for node_name in rank.nodes:
                node = self.objects[node_name]
                if node.obj_type == ObjType.CONTAINER:
                    continue

                parent_name = arrow_parents.get(node_name)
                if not parent_name:
                    parent_name = ranked.node_parent.get(node_name)

                if parent_name and parent_name in self.objects:
                    parent = self.objects[parent_name]
                    node.pos_direction = "below"
                    node.pos_reference = parent_name
                    node.pos_distance = abs(parent.bottom - node.top)
                    positioned.add(node_name)
                elif rank.index > 0:
                    # Use closest node in previous rank, preferring same container
                    prev_rank = ranked.ranks[rank.index - 1]
                    if prev_rank.nodes:
                        # Prefer nodes from the same container
                        same_container = [n for n in prev_rank.nodes
                                          if self.objects.get(n) and self.objects[n].parent == node.parent]
                        candidates = same_container if same_container else prev_rank.nodes
                        ref_node = min(candidates, key=lambda n: abs(self.objects[n].x - node.x))
                        ref_obj = self.objects[ref_node]
                        node.pos_direction = "below"
                        node.pos_reference = ref_node
                        node.pos_distance = abs(ref_obj.bottom - node.top)
                        positioned.add(node_name)

        # Check for nodes whose parent container has explicit left/right constraints
        # These override rank-based "below" positioning
        for name in list(positioned):
            obj = self.objects.get(name)
            if not obj or obj.obj_type == ObjType.CONTAINER or not obj.parent:
                continue
            parent_obj = self.objects.get(obj.parent)
            if not parent_obj:
                continue
            # Look for left/right constraints on the parent container
            parent_constraints = dag.get_constraints_for(obj.parent)
            for c in parent_constraints:
                direction = _constraint_to_direction(c)
                if direction in ("right", "left"):
                    source_obj = self.objects.get(c.source_name)
                    if source_obj and source_obj.obj_type != ObjType.CONTAINER:
                        # Use the constraint source as reference for the first child
                        if obj.parent and parent_obj.children and parent_obj.children[0] == name:
                            obj.pos_direction = direction
                            obj.pos_reference = c.source_name
                            obj.pos_distance = abs(_offset_to_mm(c.offset, c.offset_unit))
                    break

        # Remaining nodes: use constraint-based positioning
        for name in self.objects:
            if name in positioned:
                continue
            obj = self.objects[name]
            if obj.obj_type == ObjType.CONTAINER:
                continue
            if obj.pos_direction:
                continue

            constraints = dag.get_constraints_for(name)
            for c in constraints:
                direction = _constraint_to_direction(c)
                if direction:
                    source_obj = self.objects.get(c.source_name)
                    if source_obj and source_obj.obj_type == ObjType.CONTAINER:
                        ref = self._last_leaf(c.source_name)
                        if ref is None:
                            ref = c.source_name
                    else:
                        ref = c.source_name
                    dist = abs(_offset_to_mm(c.offset, c.offset_unit))
                    obj.pos_direction = direction
                    obj.pos_reference = ref
                    obj.pos_distance = dist
                    break

        # Set alignment metadata for cross-axis alignment
        for name in self.objects:
            obj = self.objects[name]
            if obj.obj_type == ObjType.CONTAINER:
                continue
            constraints = dag.get_constraints_for(name)
            for c in constraints:
                if c.target_anchor in ("center-x",) and c.source_anchor in ("center-x",):
                    obj.pos_align_direction = "center-x"
                    obj.pos_align_reference = c.source_name
                elif c.target_anchor in ("center-y",) and c.source_anchor in ("center-y",):
                    obj.pos_align_direction = "center-y"
                    obj.pos_align_reference = c.source_name

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

    def _find_middle_node(self, rank: Rank, ranked: RankedLayout) -> str | None:
        """Find the middle node of a rank (for flow-h containers, it's the container's middle child)."""
        if not rank.nodes:
            return None
        if len(rank.nodes) == 1:
            return rank.nodes[0]

        # Check if they're in a flow-h container
        for node_name in rank.nodes:
            obj = self.objects.get(node_name)
            if obj and obj.parent:
                parent = self.objects.get(obj.parent)
                if parent and parent.layout == "flow-h":
                    children = parent.children
                    if len(children) % 2 == 1:
                        return children[len(children) // 2]
                    else:
                        return children[0]  # Use first as anchor

        # Default: return the node closest to x=0
        return min(rank.nodes, key=lambda n: abs(self.objects[n].x))

    def _find_parent_from_arrows(self, node_name: str, ranked: RankedLayout) -> str | None:
        """Find the parent of a node from arrow connections."""
        for src, tgt in self._arrow_pairs:
            if tgt == node_name:
                src_rank = ranked.node_rank.get(src, -1)
                tgt_rank = ranked.node_rank.get(node_name, -1)
                if tgt_rank > src_rank:
                    return src
            if src == node_name:
                tgt_rank = ranked.node_rank.get(tgt, -1)
                src_rank = ranked.node_rank.get(node_name, -1)
                if src_rank > tgt_rank:
                    return tgt
        return None


# ─── Helpers ───

def _resolve_props(decl: ObjectDecl | ContainerDecl) -> dict[str, str | float]:
    props = {}
    for p in decl.properties:
        if isinstance(p.value, bool):
            props[p.key] = p.value
        else:
            props[p.key] = p.value
    return props


def _offset_to_mm(offset: float, unit: str) -> float:
    return offset * _UNIT_TO_MM.get(unit, 1.0)


def _constraint_to_direction(c: Constraint) -> str | None:
    """Map a constraint to a TikZ positioning direction."""
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
