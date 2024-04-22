from dataclasses import dataclass
from decimal import Decimal
from typing import Union

import matplotlib.axes
import matplotlib.figure
from shapely.geometry import Polygon  # type: ignore

from src.drawer_utils import State, dtPoint

Axes = matplotlib.axes.Axes
Figure = matplotlib.figure.Figure

Value = Union[float, Decimal]
Color = tuple[float, float, float]


@dataclass
class GraphLine:
    point1: dtPoint
    point2: dtPoint
    color: Color


@dataclass
class GraphInterface(GraphLine):
    above: State | None
    below: State | None


@dataclass
class GraphPolygon:
    polygon: Polygon
    state: State
    point: dtPoint
    label: str


@dataclass
class FigureResult:
    max_pos: float
    min_pos: float
    max_time: float
    min_time: float
    user_interfaces: list[GraphLine]
    interfaces: list[GraphInterface]
    polygons: list[GraphPolygon]
    trajectories: list[GraphLine]
