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
            # Primarily horizontal
            if dx >= 0:
                return "right", "left"
            else:
                return "left", "right"
        else:
            # Primarily vertical
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
            # Skip ghosted objects
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
        # Use separating axis theorem with the line segment vs AABB
        sx, sy = start
        ex, ey = end
        left, right = obj.left, obj.right
        bottom, top = obj.bottom, obj.top

        # Check if either endpoint is inside the box
        if left <= sx <= right and bottom <= sy <= top:
            return True
        if left <= ex <= right and bottom <= ey <= top:
            return True

        # Parametric line: P(t) = start + t * (end - start), t in [0, 1]
        dx = ex - sx
        dy = ey - sy

        tmin = 0.0
        tmax = 1.0

        # Check X slab
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

        # Check Y slab
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
        """Generate S-bend waypoints for orthogonal routing."""
        sx, sy = start
        ex, ey = end

        # Compute a midpoint offset to go around obstacles
        # Use the perpendicular direction to offset
        dx = ex - sx
        dy = ey - sy

        # Determine primary direction and offset perpendicular
        if abs(dx) >= abs(dy):
            # Horizontal primary — offset vertically
            # Find max obstacle extent to determine offset
            max_y_extent = 0.0
            for obs in obstacles:
                max_y_extent = max(max_y_extent, obs.top, obs.bottom)
            mid_x = (sx + ex) / 2

            # Offset above or below based on where there's more room
            offset = max(obs.height for obs in obstacles) / 2 + _ESCAPE_PADDING + 2.0
            if sy >= 0:
                offset_y = max(obs.top for obs in obstacles) + offset
            else:
                offset_y = min(obs.bottom for obs in obstacles) - offset

            return [
                Waypoint(x=mid_x, y=sy, type="corner"),
                Waypoint(x=mid_x, y=offset_y, type="corner"),
                Waypoint(x=mid_x, y=ey, type="corner"),
            ]
        else:
            # Vertical primary — offset horizontally
            offset = max(obs.width for obs in obstacles) / 2 + _ESCAPE_PADDING + 2.0
            mid_y = (sy + ey) / 2

            if sx >= 0:
                offset_x = max(obs.right for obs in obstacles) + offset
            else:
                offset_x = min(obs.left for obs in obstacles) - offset

            return [
                Waypoint(x=sx, y=mid_y, type="corner"),
                Waypoint(x=offset_x, y=mid_y, type="corner"),
                Waypoint(x=ex, y=mid_y, type="corner"),
            ]

    def _route_bezier(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        obstacles: list[LayoutObject],
    ) -> list[Waypoint]:
        """Generate a bezier control point perpendicular to the line."""
        sx, sy = start
        ex, ey = end

        mid_x = (sx + ex) / 2
        mid_y = (sy + ey) / 2

        # Perpendicular direction
        dx = ex - sx
        dy = ey - sy
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1e-10:
            return []

        # Perpendicular unit vector
        perp_x = -dy / length
        perp_y = dx / length

        # Offset enough to clear obstacles
        offset = max(
            max(obs.width for obs in obstacles) / 2,
            max(obs.height for obs in obstacles) / 2,
        ) + _ESCAPE_PADDING + 2.0

        ctrl_x = mid_x + perp_x * offset
        ctrl_y = mid_y + perp_y * offset

        return [Waypoint(x=ctrl_x, y=ctrl_y, type="control")]
