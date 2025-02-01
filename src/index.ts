import { CapacityBottleneck } from "./augmenters/base_augmenter";
import { FundamentalDiagram } from "./fundamental_diagram";
import { ShockwaveDrawer } from "./shockwave_drawer";
import { DefaultFigureResult, FigureResult, Viewport } from "./types";

export * from "./types";
export * from "./shockwave_drawer";
export * from "./fundamental_diagram";
export * from "./drawer_utils";
export * from "./augmenters/linear_bottleneck";
export * from "./augmenters/traffic_light";
export * from "./augmenters/base_augmenter";

interface FigureParams {
  fundDia: FundamentalDiagram,
  simulationTime: number,
  numTrajectories: number,
  withTrajectories: boolean,
  withPolygons: boolean,
  viewport?: Viewport
}

interface FundamentalDiagramParams {
  freeflowSpeed: number,
  jamDensity: number,
  trafficWaveSpeed: number,
  initDensity: number
}

export function createFundamentalDiagram({
  freeflowSpeed,
  jamDensity,
  trafficWaveSpeed,
  initDensity
}: FundamentalDiagramParams): FundamentalDiagram {
  return new FundamentalDiagram(freeflowSpeed, jamDensity, trafficWaveSpeed, initDensity);
}

export function createFigureFactory({
  fundDia, simulationTime, numTrajectories, withTrajectories, withPolygons, viewport
}: FigureParams): [
    (augments: CapacityBottleneck[]) => FigureResult,
    (params: FundamentalDiagramParams) => void
  ] {
  let prev = DefaultFigureResult;

  let sd = new ShockwaveDrawer(
    fundDia
  );

  return [
    (augments: CapacityBottleneck[]): FigureResult => {
      try {
        sd.run(simulationTime, augments);
        const fig = sd.generateFigure(numTrajectories, withTrajectories, withPolygons, viewport);
        prev = fig;
      } catch (err) {
        console.error("error when creating figure: ", err);
      }

      return prev;
    },
    (params: FundamentalDiagramParams) => {
      sd = new ShockwaveDrawer(createFundamentalDiagram(params));
    }
  ];
}