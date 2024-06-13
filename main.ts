import { HorizontalBottleneck, CapacityBottleneck, FundamentalDiagram, ShockwaveDrawer } from "./src/index";

const diagram = new FundamentalDiagram(2, 5.0, 1.0, 1.0);

const augments: CapacityBottleneck[] = [];
augments.push(new HorizontalBottleneck(10, 10, 20, 0));

const drawer = new ShockwaveDrawer(diagram, augments);

drawer.run(20);
console.log(JSON.stringify(drawer.generateFigure(100, true, false).interfaces, null, 2));
// console.log(drawer.getInterfaces());