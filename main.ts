import * as fs from "fs";

import { HorizontalBottleneck, CapacityBottleneck, FundamentalDiagram, ShockwaveDrawer } from "./src/index";

// alternatively, look at getShockwave
const diagram = new FundamentalDiagram(2, 5.0, 1.0, 1);

const augments: CapacityBottleneck[] = [];
// augments.push(new HorizontalBottleneck(16.1, 27.5, 50.7, 1));
augments.push(new HorizontalBottleneck(30, 20, 40, 0));

const drawer = new ShockwaveDrawer(diagram, augments);

drawer.run(150);
fs.writeFile("output.json", JSON.stringify(drawer.generateFigure(100, true, true)), (err) => {console.error(err);});