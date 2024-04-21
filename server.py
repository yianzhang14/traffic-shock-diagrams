from dataclasses import asdict

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from src.custom_types import GraphPolygon
from src.fundamental_diagram import FundamentalDiagram
from src.parser import parse
from src.shockwave_drawer import ShockwaveDrawer

app = Flask(__name__)
cors = CORS(app)

SETTINGS = FundamentalDiagram(2.0, 5.0, 1.0)
SIMULATION_TIME = 20
INIT_DENSITY = 1.0


@app.route("/")
def home():
    return "hello world"


@app.route("/diagram", methods=["POST"])
def get_diagram() -> Response:
    body = request.get_json()

    if "augment-info" not in body:
        return Response("need to provide augment-info field to configure augments", 400)
    augment_str: str = body["augment-info"]

    try:
        augments = parse(augment_str)
    except Exception as e:
        return Response(f"badly formed augment-info string: {str(e)}", status=400)

    try:
        drawer = ShockwaveDrawer(SETTINGS, SIMULATION_TIME, augments, INIT_DENSITY)
        drawer.run()
    except Exception as e:
        print(e)
        return Response(f"failed to create shockwave diagram: {str(e)}", 500)

    figure = drawer._create_figure(100, with_trajectories=True, with_polygons=True)
    result = asdict(figure)

    graph_polygon: GraphPolygon
    for graph_polygon in result["polygons"]:
        graph_polygon.polygon = list(graph_polygon.polygon.exterior.coords)

    return jsonify(result)


if __name__ == "__main__":
    app.run("0.0.0.0", port=5000, debug=True)
