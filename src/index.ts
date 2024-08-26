import { CapacityBottleneck } from "./augmenters/base_augmenter";
import { FundamentalDiagram } from "./fundamental_diagram";
import { ShockwaveDrawer } from "./shockwave_drawer";
import { FigureResult } from "./types";

export * from "./types";
export * from "./shockwave_drawer";
export * from "./fundamental_diagram";
export * from "./drawer_utils";
export * from "./augmenters/linear_bottleneck";
export * from "./augmenters/traffic_light";
export * from "./augmenters/base_augmenter";

export function getShockwave(
  freeflow_speed: number, 
  jam_density: number, 
  traffic_wave_speed: number, 
  init_density: number, 
  bottlenecks: CapacityBottleneck[],
  set_max_time: number,
  num_trajectories: number,
  with_trajectories: boolean,
  with_polygons: boolean,
  set_max_pos?: number
): FigureResult {
  const diagram = new FundamentalDiagram(
    freeflow_speed, jam_density, traffic_wave_speed, init_density
  );

  const drawer = new ShockwaveDrawer(diagram, bottlenecks);
  drawer.run(set_max_time);

  return drawer.runAndGenerateFigure(
    num_trajectories, with_trajectories, with_polygons, set_max_time, set_max_pos
  );
}