"""Arrow router — computes waypoints to route arrows around obstacles."""

from __future__ import annotations

from .objects import ArrowObject, LayoutObject, ObjType, Waypoint


# Padding around object faces for escape points
_ESCAPE_PADDING = 2.0  # mm


class ArrowRouter:
    """Routes arrows around obstacles using orthogonal or bezier waypoints."""

    def route_all(self, objects: dict[str, LayoutObject], arrows: list[ArrowObject]):
        """Route all arrows, setting waypoints and anchors."""
        # Group arrows by target for bus routing
        target_counts: dict[str, list[int]] = {}
        for i, arrow in enumerate(arrows):
            target_counts.setdefault(arrow.target, []).append(i)

        for i, arrow in enumerate(arrows):
            src = objects.get(arrow.source)
            tgt = objects.get(arrow.target)
            if src is None or tgt is None:
                continue

            # Determine best anchors
            src_anchor, tgt_anchor = self._best_anchors(src, tgt)
            arrow.source_anchor = src_anchor
            arrow.target_anchor = tgt_anchor

            # Bus routing: spread anchors when multiple arrows hit same target
            siblings = target_counts.get(arrow.target, [])
            if len(siblings) > 1:
                idx = siblings.index(i)
                n = len(siblings)
                tgt_anchor = self._spread_anchor(tgt_anchor, idx, n, tgt)
                arrow.target_anchor = tgt_anchor

            # Compute escape points
            esc_src = self._escape_point(src, src_anchor)
            esc_tgt = self._escape_point(tgt, tgt_anchor)

            # Find obstacles between escape points
            skip = {arrow.source, arrow.target}
            obstacles = self._find_obstacles(esc_src, esc_tgt, objects, skip)

            if not obstacles:
                # Direct path is clear — no waypoints needed
                arrow.waypoints = []
                arrow.auto_routed = False
                continue

            # Route around obstacles based on route type
            route = arrow.route or "orthogonal"
            if route == "bezier":
                arrow.waypoints = self._route_bezier(
                    esc_src, esc_tgt, obstacles, arrow.source, arrow.target,
                    src_anchor, tgt_anchor)
            else:
                # Default to orthogonal routing
                arrow.waypoints = self._route_orthogonal(
                    esc_src, esc_tgt, obstacles, arrow.source, arrow.target,
                    src_anchor, tgt_anchor, objects)
            arrow.auto_routed = True

    def _best_anchors(self, src: LayoutObject, tgt: LayoutObject) -> tuple[str, str]:
        """Pick best source/target edge anchors based on relative positions."""
        dx = tgt.x - src.x
        dy = tgt.y - src.y

        if abs(dx) >= abs(dy):
            if dx >= 0:
                return "right", "left"
            else:
                return "left", "right"
        else:
            if dy >= 0:
                return "top", "bottom"
            else:
                return "bottom", "top"

    def _spread_anchor(self, anchor: str, idx: int, total: int, obj: LayoutObject) -> str:
        """Distribute target anchors across a face when multiple arrows converge.
        
        Returns an angle-based anchor like '160' for TikZ compass anchors.
        """
        if total <= 1:
            return anchor
        # Map base anchor to angle range on that face
        angle_ranges = {
            "top": (100, 170),     # top face: 100° to 170° (visual top)
            "bottom": (10, 80),    # bottom face: 10° to 80° (visual bottom)
            "left": (170, 190),    # left face
            "right": (-10, 10),    # right face
        }
        base_range = angle_ranges.get(anchor, (45, 135))
        # Distribute evenly
        if total == 1:
            angle = (base_range[0] + base_range[1]) // 2
        else:
            angle = base_range[0] + (base_range[1] - base_range[0]) * idx / (total - 1)
        return str(int(angle))

    def _escape_point(self, obj: LayoutObject, anchor: str) -> tuple[float, float]:
        """Compute a point just outside the object face with padding."""
        match anchor:
            case "right":
                return (obj.right + _ESCAPE_PADDING, obj.y)
            case "left":
                return (obj.left - _ESCAPE_PADDING, obj.y)
            case "top":
                return (obj.x, obj.top + _ESCAPE_PADDING)
            case "bottom":
                return (obj.x, obj.bottom - _ESCAPE_PADDING)
            case _:
                return (obj.x, obj.y)

    def _find_obstacles(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        objects: dict[str, LayoutObject],
        skip: set[str],
    ) -> list[LayoutObject]:
        """Find objects whose bbox intersects the line segment from start to end."""
        obstacles = []
        for name, obj in objects.items():
            if name in skip:
                continue
            if obj.obj_type == ObjType.CONTAINER:
                continue
            if 0 < obj.opacity < 0.5:
                continue
            if self._line_intersects_box(start, end, obj):
                obstacles.append(obj)
        return obstacles

    def _line_intersects_box(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        obj: LayoutObject,
    ) -> bool:
        """Check if line segment (start→end) intersects the object's bounding box."""
        sx, sy = start
        ex, ey = end
        left, right = obj.left, obj.right
        bottom, top = obj.bottom, obj.top

        if left <= sx <= right and bottom <= sy <= top:
            return True
        if left <= ex <= right and bottom <= ey <= top:
            return True

        dx = ex - sx
        dy = ey - sy

        tmin = 0.0
        tmax = 1.0

        if abs(dx) < 1e-10:
            if sx < left or sx > right:
                return False
        else:
            t1 = (left - sx) / dx
            t2 = (right - sx) / dx
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return False

        if abs(dy) < 1e-10:
            if sy < bottom or sy > top:
                return False
        else:
            t1 = (bottom - sy) / dy
            t2 = (top - sy) / dy
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return False

        return True

    def _route_orthogonal(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        obstacles: list[LayoutObject],
        src_name: str,
        tgt_name: str,
        src_anchor: str,
        tgt_anchor: str,
        objects: dict[str, LayoutObject],
    ) -> list[Waypoint]:
        """Generate clean L-bend or Z-bend waypoints for orthogonal routing.
        
        Returns relational waypoints that reference objects by name.
        The TikZ backend will use -|, |-, and offset syntax.
        """
        sx, sy = start
        ex, ey = end

        if abs(sx - ex) < 0.01 and abs(sy - ey) < 0.01:
            return []

        src = objects[src_name]
        tgt = objects[tgt_name]

        # Try L-bend: go horizontal to target x, then vertical to target y
        corner1 = (ex, sy)
        h_clear = not any(
            self._line_intersects_box((sx, sy), corner1, obs)
            for obs in obstacles
        )
        v_clear = not any(
            self._line_intersects_box(corner1, (ex, ey), obs)
            for obs in obstacles
        )
        if h_clear and v_clear:
            # L-bend: horizontal first, then vertical → TikZ -|
            return [Waypoint(type="l-bend-h")] 

        # Try the other L-bend: go vertical first, then horizontal
        corner2 = (sx, ey)
        v_clear2 = not any(
            self._line_intersects_box((sx, sy), corner2, obs)
            for obs in obstacles
        )
        h_clear2 = not any(
            self._line_intersects_box(corner2, (ex, ey), obs)
            for obs in obstacles
        )
        if v_clear2 and h_clear2:
            # L-bend: vertical first, then horizontal → TikZ |-
            return [Waypoint(type="l-bend-v")] 

        # Both L-bends blocked — use Z-bend via intermediate connector
        # Compute escape offsets relative to source/target anchors
        max_obs_top = max(obs.top for obs in obstacles) + _ESCAPE_PADDING + 2.0
        min_obs_bottom = min(obs.bottom for obs in obstacles) - _ESCAPE_PADDING - 2.0

        # In y-down coords: 'top' (y+h/2) is visual bottom, 'bottom' (y-h/2) is visual top
        # 'above' the obstacle = lower y (visual top side) = min_obs_bottom
        # 'below' the obstacle = higher y (visual bottom side) = max_obs_top
        above_y = min_obs_bottom  # visual above (lower y in y-down)
        below_y = max_obs_top     # visual below (higher y in y-down)
        go_above = True

        # Try Z-bend going above (visual above = lower y)
        seg1_clear = not any(self._line_intersects_box((sx, sy), (sx, above_y), obs) for obs in obstacles)
        seg2_clear = not any(self._line_intersects_box((sx, above_y), (ex, above_y), obs) for obs in obstacles)
        seg3_clear = not any(self._line_intersects_box((ex, above_y), (ex, ey), obs) for obs in obstacles)
        if not (seg1_clear and seg2_clear and seg3_clear):
            # Try Z-bend going below (visual below = higher y)
            seg1_clear = not any(self._line_intersects_box((sx, sy), (sx, below_y), obs) for obs in obstacles)
            seg2_clear = not any(self._line_intersects_box((sx, below_y), (ex, below_y), obs) for obs in obstacles)
            seg3_clear = not any(self._line_intersects_box((ex, below_y), (ex, ey), obs) for obs in obstacles)
            go_above = False

        detour_y = above_y if go_above else below_y
        # offset relative to source escape point
        y_off = detour_y - sy

        # Generate Z-bend waypoints: source anchor → escape point → -| → target
        return [
            Waypoint(type="z-bend-escape", ref_object=src_name, y_offset=y_off),
        ]

    def _route_bezier(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        obstacles: list[LayoutObject],
        src_name: str = "",
        tgt_name: str = "",
        src_anchor: str = "",
        tgt_anchor: str = "",
    ) -> list[Waypoint]:
        """Generate bezier control points to curve around obstacles."""
        sx, sy = start
        ex, ey = end

        mid_x = (sx + ex) / 2
        mid_y = (sy + ey) / 2

        dx = ex - sx
        dy = ey - sy
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-10:
            return []

        perp_x = -dy / length
        perp_y = dx / length

        offset = max(
            max(obs.width for obs in obstacles) / 2,
            max(obs.height for obs in obstacles) / 2,
        ) + _ESCAPE_PADDING + 2.0

        ctrl_x = mid_x + perp_x * offset
        ctrl_y = mid_y + perp_y * offset

        # Express as offset from midpoint between source and target anchors
        if src_name and tgt_name:
            # For primarily vertical paths, use vertical control point offset
            # For primarily horizontal, use horizontal
            if abs(dy) > abs(dx):
                # Vertical: control point should offset vertically
                ctrl_offset_x = 0.0
                ctrl_offset_y = perp_y * offset
                # Use the sign of dy to determine direction
                if abs(ctrl_offset_y) < 1.0:
                    ctrl_offset_y = offset if dy >= 0 else -offset
            else:
                # Horizontal: control point should offset horizontally
                ctrl_offset_x = perp_x * offset
                ctrl_offset_y = 0.0
                if abs(ctrl_offset_x) < 1.0:
                    ctrl_offset_x = offset if dx >= 0 else -offset

            return [Waypoint(
                type="control",
                mid_source=src_name,
                mid_target=tgt_name,
                x_offset=ctrl_offset_x,
                y_offset=ctrl_offset_y,
                x=ctrl_x, y=ctrl_y,
            )]

        return [Waypoint(x=ctrl_x, y=ctrl_y, type="control")]
