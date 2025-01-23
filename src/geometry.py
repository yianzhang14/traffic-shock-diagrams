from __future__ import annotations

import collections
import itertools
import math
from dataclasses import dataclass, field
from typing import Optional

from sortedcontainers import SortedDict  # type: ignore

from src.custom_types import ArrangementEdge
from src.drawer_utils import Interface, dtPoint, float_isclose


def get_polar_angle(src: dtPoint, dest: dtPoint) -> float:
    dy = dest.position - src.position
    dx = dest.time - src.time
    angle = math.atan2(dy, dx)

    return angle


class SegmentArrangement:
    def __init__(self) -> None:
        self.vertices: dict[dtPoint, SortedDict[float, dtPoint]] = collections.defaultdict(
            SortedDict
        )
        self.segment_dict: dict[ArrangementEdge, Interface] = dict()

    def add_segment(self, p1: dtPoint, p2: dtPoint, interface: Optional[Interface] = None) -> None:
        angle = get_polar_angle(p1, p2)
        self.vertices[p1][angle] = p2

        complement = get_polar_angle(p2, p1)
        self.vertices[p2][complement] = p1

        points = [p1, p2]
        _, lp = max(enumerate(points), key=lambda x: x[1].time)
        _, rp = min(enumerate(points), key=lambda x: x[1].time)

        if interface is not None:
            self.segment_dict[lp, rp] = interface

    def lookup_segment(self, p1: dtPoint, p2: dtPoint) -> Optional[Interface]:
        points = [p1, p2]
        _, lp = min(enumerate(points), key=lambda x: x[1].time)
        _, rp = max(enumerate(points), key=lambda x: x[1].time)

        if (lp, rp) not in self.segment_dict:
            return None

        return self.segment_dict[lp, rp]

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

    def _insert_segment(self, segment: ArrangementEdge, node: SegmentTreeNode) -> None:
        if segment[1].time < node.left_cutoff or segment[0].time > node.right_cutoff:
            return

        if (
            segment[0].time < node.left_cutoff or float_isclose(segment[0].time, node.left_cutoff)
        ) and (
            segment[1].time > node.right_cutoff or float_isclose(segment[1].time, node.right_cutoff)
        ):
            pass

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
