from __future__ import annotations

import collections
import itertools
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import shapely as shp  # type: ignore
from matplotlib.collections import PatchCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from sortedcontainers import SortedDict  # type: ignore

from src.custom_types import ArrangementEdge, Viewport
from src.drawer_utils import Interface, dtPoint, float_isclose


def get_polar_angle(src: dtPoint, dest: dtPoint) -> float:
    dy = dest.position - src.position
    dx = dest.time - src.time
    angle = math.atan2(dy, dx)

    return angle


# Plots a Polygon to pyplot `ax`
def plot_polygon(ax, poly, **kwargs):
    path = Path.make_compound_path(
        Path(np.asarray(poly.exterior.coords)[:, :2]),
        *[Path(np.asarray(ring.coords)[:, :2]) for ring in poly.interiors],
    )

    patch = PathPatch(path, **kwargs)
    collection = PatchCollection([patch], **kwargs)

    ax.add_collection(collection, autolim=True)
    ax.autoscale_view()
    return collection


def convert_to_shapely(points: list[dtPoint]) -> shp.Polygon:
    return shp.Polygon([p.astuple() for p in points])


class SegmentArrangement:
    def __init__(self, viewport: Viewport) -> None:
        self.viewport = viewport
        self.vertices: dict[dtPoint, SortedDict[float, dtPoint]] = collections.defaultdict(
            SortedDict
        )
        self.segment_to_polygon: dict[ArrangementEdge, list[shp.Polygon]] = collections.defaultdict(
            list
        )
        self.segment_to_interface: dict[ArrangementEdge, Interface] = dict()
        self.polygons: dict[int, list[dtPoint]] = dict()
        self.poly_count = 0
        self.base_polygon = -1

        self.built = False

    def build(self, interfaces: list[Interface]) -> None:
        if self.built:
            return
        self.built = True
        # corner points of the viewport
        bottom_left = dtPoint(self.viewport.min_time, self.viewport.min_pos)
        top_left = dtPoint(self.viewport.min_time, self.viewport.max_pos)
        bottom_right = dtPoint(self.viewport.max_time, self.viewport.min_pos)
        top_right = dtPoint(self.viewport.max_time, position=self.viewport.max_pos)

        # lists of points at the edges of the viewport
        left: list[dtPoint] = [bottom_left, top_left]
        right: list[dtPoint] = [bottom_right, top_right]
        top: list[dtPoint] = [top_left, top_right]
        bottom: list[dtPoint] = [bottom_left, bottom_right]

        # create segments to initialize the arrangement, cutting off at the viewport edges
        for interface in interfaces:
            if not interface.has_valid_states():
                continue

            p1, p2 = interface.endpoints

            if p2.time == float("inf"):
                y_pos = interface.get_pos_at_time(self.viewport.max_time)
                assert y_pos
                p2 = dtPoint(self.viewport.max_time, y_pos)

            self.add_segment(p1, p2, interface)

            if p2 == bottom_left or p2 == top_left or p2 == top_right or p2 == bottom_right:
                continue

            if (
                p2.time == self.viewport.max_time
                and p2.position < self.viewport.max_pos
                and p2.position > self.viewport.min_pos
            ):
                right.append(p2)

            time_of_max_pos = interface.get_time_at_pos(self.viewport.max_pos)
            time_of_min_pos = interface.get_time_at_pos(self.viewport.min_pos)

            if time_of_max_pos is not None:
                top.append(dtPoint(time_of_max_pos, self.viewport.max_pos))
            if time_of_min_pos is not None:
                bottom.append(dtPoint(time_of_min_pos, self.viewport.min_pos))

        # create segments along the viewport edges
        bottom.sort(key=lambda x: x.time)
        top.sort(key=lambda x: x.time)
        left.sort(key=lambda x: x.position)
        right.sort(key=lambda x: x.position)

        for edge_list in [bottom, top, left, right]:
            for i in range(len(edge_list) - 1):
                self.add_segment(edge_list[i], edge_list[i + 1])

        edges = self.get_all_directed_edges()
        seen: set[ArrangementEdge] = set()

        for edge in edges:
            if edge in seen:
                continue

            src, dest = edge
            polygon: list[dtPoint] = []

            while (src, dest) not in seen:
                seen.add((src, dest))
                polygon.append(src)

                src, dest = dest, self.get_next_ccw_vertex(src, dest)

            if len(polygon) < 3:
                print("degenerate polygon:", polygon)
                continue

            if float_isclose(
                shoelace(polygon),
                (self.viewport.max_time - self.viewport.min_time)
                * (self.viewport.max_pos - self.viewport.min_pos),
            ):
                continue

            polygon_id = self.add_polygon(polygon)

            for i in range(len(polygon) - 1):
                self.associate_segment_with_polygon((polygon[i], polygon[i + 1]), polygon_id)
            self.associate_segment_with_polygon((polygon[-1], polygon[0]), polygon_id)

    def add_segment(self, p1: dtPoint, p2: dtPoint, interface: Optional[Interface] = None) -> None:
        angle = get_polar_angle(p1, p2)
        self.vertices[p1][angle] = p2

        complement = get_polar_angle(p2, p1)
        self.vertices[p2][complement] = p1

        if interface is not None:
            lp, rp = order_segment((p1, p2))
            self.segment_to_interface[lp, rp] = interface

    def add_polygon(self, polygon: list[dtPoint]) -> int:
        for p in polygon:
            if float_isclose(p.time, self.viewport.min_time):
                self.base_polygon = self.poly_count

        self.polygons[self.poly_count] = polygon
        polygon_id = self.poly_count
        self.poly_count += 1

        return polygon_id

    def get_segment_interface(self, segment: ArrangementEdge) -> Optional[Interface]:
        lp, rp = order_segment(segment)

        if (lp, rp) not in self.segment_to_interface:
            return None

        return self.segment_to_interface[lp, rp]

    def get_segment_geos(self, segment: ArrangementEdge) -> list[int]:
        lp, rp = order_segment(segment)
        if (lp, rp) not in self.segment_to_polygon:
            print("no polygon for segment", lp, rp)
            return []

        return self.segment_to_polygon[lp, rp]

    def associate_segment_with_polygon(self, segment: ArrangementEdge, polygon_id: int) -> None:
        lp, rp = order_segment(segment)
        self.segment_to_polygon[lp, rp].append(polygon_id)

    def get_all_directed_edges(self) -> list[ArrangementEdge]:
        edges = []

        for source, d in self.vertices.items():
            for dest in d.values():
                edges.append((source, dest))
                edges.append((dest, source))

        return edges

    def get_next_ccw_vertex(self, src: dtPoint, dest: dtPoint) -> dtPoint:
        angle = get_polar_angle(dest, src)
        idx: int = self.vertices[dest].bisect_right(angle)

        if idx == len(self.vertices[dest]):
            return self.vertices[dest].peekitem(0)[1]

        return self.vertices[dest].peekitem(idx)[1]

    def get_polygon(self, poly_id: int) -> Optional[list[dtPoint]]:
        if poly_id not in self.polygons:
            return None

        return self.polygons[poly_id]

    def get_base_polygon(self) -> int:
        assert self.base_polygon != -1
        return self.base_polygon

    def get_cleaned_geometries(self) -> list[shp.Polygon]:
        # full polygon
        full_polygon = shp.Polygon(
            [
                (self.viewport.min_time, self.viewport.min_pos),
                (self.viewport.min_time, self.viewport.max_pos),
                (self.viewport.max_time, self.viewport.max_pos),
                (self.viewport.max_time, self.viewport.min_pos),
            ]
        )

        polygons = [convert_to_shapely(poly) for poly in self.polygons.values()]

        out: list[shp.Polygon] = []
        for polygon in polygons:
            # fig, ax = plt.subplots()
            # plot_polygon(ax, polygon, facecolor="red", alpha=0.5)
            # plot_polygon(ax, full_polygon, facecolor="lightblue", alpha=0.5)

            intersection = full_polygon.intersection(shp.make_valid(polygon))

            if intersection.is_empty:
                continue

            if isinstance(intersection, shp.Polygon):
                # plot_polygon(ax, intersection, facecolor="green", alpha=0.5)
                out.append(intersection)
                # temp = intersection.representative_point()

                # ax.plot(temp.x, temp.y, "ro")
            elif isinstance(intersection, shp.MultiPolygon):
                for component in intersection.geoms:
                    # plot_polygon(ax, component, facecolor="green", alpha=0.5)
                    out.append(component)
                    # temp = component.representative_point()
                    # ax.plot(temp.x, temp.y, "ro")

            # fig.show()

        if len(out) == 0:
            out = [full_polygon]
            for i in range(len(out)):
                if float_isclose(out[i].area, full_polygon.area) or out[i].area > full_polygon.area:
                    out.pop(i)
                    break

        return out


def shoelace(x_y: list[dtPoint]) -> float:
    arr = np.array(list(itertools.chain(*[list(point.astuple()) for point in x_y])))
    arr = arr.reshape(-1, 2)

    x = arr[:, 0]
    y = arr[:, 1]

    S1: float = np.sum(x * np.roll(y, -1))
    S2: float = np.sum(y * np.roll(x, -1))

    area: float = 0.5 * np.absolute(S1 - S2)

    return area


def calc_segment_intersection(
    point: dtPoint, slope: float, segment: ArrangementEdge
) -> Optional[dtPoint]:
    lp, rp = order_segment(segment)

    # vertical line
    if float_isclose(rp.time, lp.time):
        if not float_isclose(rp.time, point.time) and rp.time < point.time:
            return None
        return dtPoint(rp.time, point.position + (rp.time - point.time) * slope)

    seg_slope = (rp.position - lp.position) / (rp.time - lp.time)

    if float_isclose(seg_slope, slope):
        return None

    time_of_intersect = (
        slope * point.time - seg_slope * rp.time + rp.position - point.position
    ) / (slope - seg_slope)

    if float_isclose(time_of_intersect, point.time) or time_of_intersect < point.time:
        return None
    if (not float_isclose(time_of_intersect, lp.time) and time_of_intersect < lp.time) or (
        not float_isclose(time_of_intersect, rp.time) and time_of_intersect > rp.time
    ):
        return None

    return dtPoint(time_of_intersect, point.position + (time_of_intersect - point.time) * slope)


def order_segment(segment: ArrangementEdge) -> ArrangementEdge:
    _, lp = min(enumerate(segment), key=lambda x: x[1].time)
    _, rp = max(enumerate(segment), key=lambda x: x[1].time)

    return (lp, rp)


@dataclass
class SegmentTreeNode:
    left_cutoff: float
    right_cutoff: float
    divider: float

    leaf: bool = False
    segments: list = field(default_factory=list)
    left: Optional[SegmentTreeNode] = None
    right: Optional[SegmentTreeNode] = None


class SegmentTree:
    def __init__(self, segments: list[ArrangementEdge]) -> None:
        self.endpoints: list[float] = sorted(
            set(itertools.chain(*[[left.time, right.time] for left, right in segments]))
        )
        self.segments = segments

        self.root = self._build(0, len(self.endpoints) - 1, self.endpoints[0], self.endpoints[-1])

    def _build(self, start: int, end: int, left: float, right: float) -> Optional[SegmentTreeNode]:
        mid = (start + end) // 2
        if start <= end:
            return None
        if start == mid:
            return SegmentTreeNode(left, right, -1, leaf=True)

        node = SegmentTreeNode(left, right, self.endpoints[mid])
        node.left = self._build(start, mid - 1, start, self.endpoints[mid])
        node.right = self._build(mid + 1, end, self.endpoints[mid], end)

        return node

    def _insert_segment(
        self, index: int, left: float, right: float, node: Optional[SegmentTreeNode]
    ) -> None:
        if node is None:
            return
        if right < node.left_cutoff or left > node.right_cutoff:
            return

        if (left < node.left_cutoff or float_isclose(left, node.left_cutoff)) and (
            right > node.right_cutoff or float_isclose(right, node.right_cutoff)
        ):
            node.segments.append(index)
            return

        self._insert_segment(index, left, node.divider, node.left)
        self._insert_segment(index, node.divider, right, node.right)

    def find_segment(self, x, y, node=1, start=0, end=None):
        if end is None:
            end = self.n - 1

        if start == end:
            # Find segment directly above point
            result = None
            min_y = float("inf")
            for seg in self.tree[node]:
                if seg[0] <= x <= seg[1] and seg[2] > y and seg[2] < min_y:
                    min_y = seg[2]
                    result = seg
            return result

        mid = (start + end) // 2
        if x <= self.segments[mid][0]:
            return self.find_segment(x, y, 2 * node, start, mid)
        else:
            return self.find_segment(x, y, 2 * node + 1, mid + 1, end)
