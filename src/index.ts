import { CapacityBottleneck } from "./augmenters/base_augmenter";
import { FundamentalDiagram } from "./fundamental_diagram";
import { ShockwaveDrawer } from "./shockwave_drawer";
import { DEFAULT_FIGURERESULT, Viewport } from "./types";

export * from "./types";
export * from "./shockwave_drawer";
export * from "./fundamental_diagram";
export * from "./drawer_utils";
export * from "./augmenters/linear_bottleneck";
export * from "./augmenters/traffic_light";
export * from "./augmenters/base_augmenter";

interface FigureParams {
    fund_dia: FundamentalDiagram,
    simulation_time: number,
    num_trajectories: number,
    with_trajectories:boolean,
    with_polygons: boolean,
    viewport?: Viewport
}

interface FundamentalDiagramParams {
    freeflow_speed: number,
    jam_density: number,
    traffic_wave_speed: number,
    init_density: number
}

export function createFundamentalDiagram({ 
  freeflow_speed, 
  jam_density, 
  traffic_wave_speed, 
  init_density 
}: FundamentalDiagramParams): FundamentalDiagram {
  return new FundamentalDiagram(freeflow_speed, jam_density, traffic_wave_speed, init_density);
}

export function createFigureFactory({
  fund_dia, simulation_time, num_trajectories, with_trajectories, with_polygons, viewport
}: FigureParams) {
  let prev = DEFAULT_FIGURERESULT;

  let sd = new ShockwaveDrawer(
    fund_dia
  );

  return [
    function(augments: CapacityBottleneck[]) {
      try {
        sd.run(simulation_time, augments);
        const fig = sd.generateFigure(num_trajectories, with_trajectories, with_polygons, viewport);
        prev = fig;
      } catch (err) {
        console.error("error when creating figure: ", err);
      }

      return prev;
    },
    function(params: FundamentalDiagramParams) {
      sd = new ShockwaveDrawer(createFundamentalDiagram(params));
    }
  ];
}