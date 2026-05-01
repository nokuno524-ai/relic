"""Arrow router — computes waypoints to route arrows around obstacles."""

from __future__ import annotations

from .objects import ArrowObject, LayoutObject, ObjType, Waypoint


# Padding around object faces for escape points
_ESCAPE_PADDING = 2.0  # mm


class ArrowRouter:
    """Routes arrows around obstacles using orthogonal or bezier waypoints."""

    def route_all(self, objects: dict[str, LayoutObject], arrows: list[ArrowObject]):
        """Route all arrows, setting waypoints and anchors."""
        for arrow in arrows:
            src = objects.get(arrow.source)
            tgt = objects.get(arrow.target)
            if src is None or tgt is None:
                continue

            # Determine best anchors
            src_anchor, tgt_anchor = self._best_anchors(src, tgt)
            arrow.source_anchor = src_anchor
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
                arrow.waypoints = self._route_bezier(esc_src, esc_tgt, obstacles)
            else:
                # Default to orthogonal routing
                arrow.waypoints = self._route_orthogonal(esc_src, esc_tgt, obstacles)
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
    ) -> list[Waypoint]:
        """Generate clean L-bend or Z-bend waypoints for orthogonal routing.
        
        Only returns the INTERMEDIATE bend points, not the start/end.
        The TikZ backend will draw: source_anchor -> waypoints -> target_anchor.
        """
        sx, sy = start
        ex, ey = end

        if abs(sx - ex) < 0.01 and abs(sy - ey) < 0.01:
            # Same point
            return []

        # Try L-bend: go horizontal to target x, then vertical to target y
        # Corner point: (ex, sy) — source goes horizontal, then turns down/up to target
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
            return [Waypoint(x=ex, y=sy, type="corner")]

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
            return [Waypoint(x=sx, y=ey, type="corner")]

        # Both L-bends blocked — use Z-bend (3 segments)
        # Find a clear horizontal channel
        # Try above all obstacles
        max_obs_top = max(obs.top for obs in obstacles) + _ESCAPE_PADDING + 2.0
        # Try below all obstacles  
        min_obs_bottom = min(obs.bottom for obs in obstacles) - _ESCAPE_PADDING - 2.0
        
        mid_x = (sx + ex) / 2

        # Try Z-bend going above
        above_y = max_obs_top
        seg1_clear = not any(
            self._line_intersects_box((sx, sy), (sx, above_y), obs)
            for obs in obstacles
        )
        seg2_clear = not any(
            self._line_intersects_box((sx, above_y), (ex, above_y), obs)
            for obs in obstacles
        )
        seg3_clear = not any(
            self._line_intersects_box((ex, above_y), (ex, ey), obs)
            for obs in obstacles
        )
        if seg1_clear and seg2_clear and seg3_clear:
            return [
                Waypoint(x=sx, y=above_y, type="corner"),
                Waypoint(x=ex, y=above_y, type="corner"),
            ]

        # Try Z-bend going below
        below_y = min_obs_bottom
        seg1_clear = not any(
            self._line_intersects_box((sx, sy), (sx, below_y), obs)
            for obs in obstacles
        )
        seg2_clear = not any(
            self._line_intersects_box((sx, below_y), (ex, below_y), obs)
            for obs in obstacles
        )
        seg3_clear = not any(
            self._line_intersects_box((ex, below_y), (ex, ey), obs)
            for obs in obstacles
        )
        if seg1_clear and seg2_clear and seg3_clear:
            return [
                Waypoint(x=sx, y=below_y, type="corner"),
                Waypoint(x=ex, y=below_y, type="corner"),
            ]

        # Fallback: simple Z-bend at midpoint (may not be perfect but won't crash)
        mid_y = (sy + ey) / 2
        return [
            Waypoint(x=sx, y=mid_y, type="corner"),
            Waypoint(x=ex, y=mid_y, type="corner"),
        ]

    def _route_bezier(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        obstacles: list[LayoutObject],
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

        return [Waypoint(x=ctrl_x, y=ctrl_y, type="control")]
