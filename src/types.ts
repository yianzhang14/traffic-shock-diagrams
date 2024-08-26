import { State, dtPoint } from "./drawer_utils";

export type GraphTrajectory = dtPoint[];

export interface GraphLine {
  point1: dtPoint,
  point2: dtPoint,
};

export interface GraphInterface extends GraphLine {
  above: State | undefined,
  below: State | undefined
};

export interface GraphPolygon {
  points: dtPoint[],
  state: State,
  point: dtPoint,
  label: string
};

export interface FigureResult {
  max_pos: number,
  min_pos: number,
  max_time: number,
  min_time: number,
  user_interfaces: GraphLine[],
  interfaces: GraphInterface[],
  polygons: GraphPolygon[],
  trajectories: GraphTrajectory[]
};

