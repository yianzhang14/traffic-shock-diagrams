import * as fs from "fs";

import { HorizontalBottleneck, CapacityBottleneck, FundamentalDiagram, ShockwaveDrawer } from "./src/index";

// alternatively, look at getShockwave
const diagram = new FundamentalDiagram(3.0, 5.0, 1.0, 0.9);

const augments: CapacityBottleneck[] = [];
augments.push(new HorizontalBottleneck(35, 25.2, 58, 1.3));
augments.push(new HorizontalBottleneck(48, 14, 37.4, 0));

const drawer = new ShockwaveDrawer(diagram, augments);

drawer.run(150);
fs.writeFile("output.json", JSON.stringify(drawer.generateFigure(100, true, true, {max_pos: 150, min_pos: 0, max_time: 150, min_time: 0})), (err) => {console.error(err);});