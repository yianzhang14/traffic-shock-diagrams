from dataclasses import asdict
from typing import Any

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

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


@app.route("/parameters", methods=["GET"])
def get_parameters():
    result = {
        "freeflow-speed": SETTINGS.freeflow_speed,
        "jam-density": SETTINGS.jam_density,
        "traffic-wave-speed": SETTINGS.trafficwave_speed,
        "init-density": INIT_DENSITY,
        "simulation-time": SIMULATION_TIME,
    }

    return jsonify(result)


@app.route("/diagram", methods=["POST"])
def get_diagram() -> Response:
    body = request.get_json()

    if "augment-info" not in body:
        return Response("need to provide augment-info field to configure augments", 400)
    # TODO: add max-time, max-pos, num_trajectories, with_polygons,
    # and with_trajectories as parameters
    augment_str: str = body["augment-info"]

    max_time: float | None = None
    max_pos: float | None = None
    if "max-time" in body:
        max_time = body["max-time"]
    if "max-pos" in body:
        max_pos = body["max-pos"]

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
    result: dict[str, Any] = asdict(figure)

    graph_polygon: dict[str, Any]
    for graph_polygon in result["polygons"]:
        graph_polygon["polygon"] = list(graph_polygon["polygon"].exterior.coords)

    return jsonify(result)


if __name__ == "__main__":
    app.run("0.0.0.0", port=5000, debug=True)
