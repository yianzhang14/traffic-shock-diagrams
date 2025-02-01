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
  // label: string
};

export interface Viewport {
  maxPos: number,
  minPos: number,
  maxTime: number,
  minTime: number
}

export interface FigureResult {
  viewport: Viewport,
  userInterfaces: GraphLine[],
  interfaces: GraphInterface[],
  polygons: GraphPolygon[],
  trajectories: GraphTrajectory[],
  states: State[]
};

export const DefaultFigureResult: FigureResult = {
  viewport: { maxPos: 0, minPos: 0, maxTime: 0, minTime: 0 },
  userInterfaces: [],
  interfaces: [],
  polygons: [],
  trajectories: [],
  states: []
};

