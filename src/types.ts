import { Feature, Polygon } from "geojson";

import { State, dtPoint } from "./drawer_utils";

export type GraphTrajectory = dtPoint[];

export type polygon_t = Feature<Polygon>;

interface HasToString {
  toString: () => string;
}

export class Pair<T extends HasToString> {
  first: T;
  second: T;

  constructor(first: T, second: T) {
    this.first = first;
    this.second = second;
  }

  public toString(): string {
    return `${this.first.toString()};${this.second.toString()}`;
  }
}



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
  trajectories: GraphTrajectory[],
  states: State[]
};

export const DEFAULT_FIGURERESULT: FigureResult = {
  max_pos: 0,
  min_pos: 0,
  max_time: 0,
  min_time: 0,
  user_interfaces: [],
  interfaces: [],
  polygons: [],
  trajectories: [],
  states: []
};

