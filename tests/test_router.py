"""Tests for arrow router."""

import pytest

from relic.objects import ArrowObject, LayoutObject, ObjType, Waypoint
from relic.router import ArrowRouter


def _box(name: str, x: float, y: float, w: float = 20.0, h: float = 8.0, **kw) -> LayoutObject:
    kw.setdefault("width", w)
    kw.setdefault("height", h)
    return LayoutObject(name=name, obj_type=ObjType.BOX, x=x, y=y, **kw)


class TestAnchorSelection:
    def test_horizontal_right_left(self):
        src = _box("a", 0, 0)
        tgt = _box("b", 40, 0)
        router = ArrowRouter()
        sa, ta = router._best_anchors(src, tgt)
        assert sa == "right"
        assert ta == "left"

    def test_vertical_top_bottom(self):
        src = _box("a", 0, 0)
        tgt = _box("b", 0, 30)
        sa, ta = ArrowRouter()._best_anchors(src, tgt)
        assert sa == "top"
        assert ta == "bottom"

    def test_diagonal_prefers_horizontal(self):
        src = _box("a", 0, 0)
        tgt = _box("b", 30, 20)
        sa, ta = ArrowRouter()._best_anchors(src, tgt)
        assert sa == "right"


class TestEscapePoints:
    def test_escape_right(self):
        obj = _box("a", 10, 5, width=20, height=8)
        router = ArrowRouter()
        ex, ey = router._escape_point(obj, "right")
        assert ex > obj.right
        assert abs(ey - obj.y) < 0.01

    def test_escape_top(self):
        obj = _box("a", 10, 5, width=20, height=8)
        _, ey = ArrowRouter()._escape_point(obj, "top")
        assert ey > obj.top

    def test_escape_left(self):
        obj = _box("a", 10, 5, width=20, height=8)
        ex, _ = ArrowRouter()._escape_point(obj, "left")
        assert ex < obj.left

    def test_escape_bottom(self):
        obj = _box("a", 10, 5, width=20, height=8)
        _, ey = ArrowRouter()._escape_point(obj, "bottom")
        assert ey < obj.bottom


class TestLineBoxIntersection:
    def test_line_through_box(self):
        obj = _box("obs", 20, 0, width=10, height=10)
        router = ArrowRouter()
        assert router._line_intersects_box((0, 0), (40, 0), obj) is True

    def test_line_misses_box(self):
        obj = _box("obs", 20, 30, width=10, height=10)
        router = ArrowRouter()
        assert router._line_intersects_box((0, 0), (40, 0), obj) is False


class TestRouting:
    def test_direct_no_obstacles(self):
        """Arrow with no obstacles should have no waypoints."""
        objects = {
            "a": _box("a", 0, 0),
            "b": _box("b", 40, 0),
        }
        arrow = ArrowObject(source="a", target="b")
        ArrowRouter().route_all(objects, [arrow])
        assert arrow.waypoints == []
        assert arrow.auto_routed is False

    def test_blocked_orthogonal_waypoints(self):
        """Arrow blocked by obstacle should get waypoints."""
        objects = {
            "a": _box("a", 0, 0),
            "obs": _box("obs", 20, 0, width=10, height=10),
            "b": _box("b", 40, 0),
        }
        arrow = ArrowObject(source="a", target="b", route="orthogonal")
        ArrowRouter().route_all(objects, [arrow])
        assert len(arrow.waypoints) > 0
        assert all(isinstance(wp, Waypoint) for wp in arrow.waypoints)

    def test_blocked_bezier_control_point(self):
        """Bezier arrow blocked by obstacle should get control points."""
        objects = {
            "a": _box("a", 0, 0),
            "obs": _box("obs", 20, 0, width=10, height=10),
            "b": _box("b", 40, 0),
        }
        arrow = ArrowObject(source="a", target="b", route="bezier")
        ArrowRouter().route_all(objects, [arrow])
        assert len(arrow.waypoints) > 0
        assert all(wp.type == "control" for wp in arrow.waypoints)

    def test_skips_containers(self):
        """Containers should not be treated as obstacles."""
        objects = {
            "a": _box("a", 0, 0),
            "cont": LayoutObject(name="cont", obj_type=ObjType.CONTAINER, x=20, y=0, width=10, height=10),
            "b": _box("b", 40, 0),
        }
        arrow = ArrowObject(source="a", target="b")
        ArrowRouter().route_all(objects, [arrow])
        assert arrow.waypoints == []

    def test_skips_ghosted(self):
        """Ghosted objects should not be obstacles."""
        objects = {
            "a": _box("a", 0, 0),
            "ghost": _box("ghost", 20, 0, width=10, height=10, opacity=0.2),
            "b": _box("b", 40, 0),
        }
        arrow = ArrowObject(source="a", target="b")
        ArrowRouter().route_all(objects, [arrow])
        assert arrow.waypoints == []

    def test_anchors_set(self):
        """Anchors should be set on routed arrows."""
        objects = {
            "a": _box("a", 0, 0),
            "b": _box("b", 40, 0),
        }
        arrow = ArrowObject(source="a", target="b")
        ArrowRouter().route_all(objects, [arrow])
        assert arrow.source_anchor == "right"
        assert arrow.target_anchor == "left"
