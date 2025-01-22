import collections
import math

from sortedcontainers import SortedDict  # type: ignore

from src.custom_types import ArrangementEdge
from src.drawer_utils import dtPoint


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

    def add_segment(self, p1: dtPoint, p2: dtPoint) -> None:
        angle = get_polar_angle(p1, p2)
        self.vertices[p1][angle] = p2

        complement = get_polar_angle(p2, p1)
        self.vertices[p2][complement] = p1

    def get_dict(self, p: dtPoint) -> SortedDict:
        return self.vertices[p]

    def get_all_edges(self) -> list[ArrangementEdge]:
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
