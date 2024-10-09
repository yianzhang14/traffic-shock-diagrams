from dataclasses import asdict
from typing import Any, Optional

from flask import Flask, Response, jsonify
from flask_cors import CORS
from flask_pydantic import validate  # type: ignore
from pydantic import BaseModel

from src.fundamental_diagram import DiagramSettings, FundamentalDiagram
from src.parser import parse
from src.shockwave_drawer import ShockwaveDrawer

app = Flask(__name__)
cors = CORS(app)

DEFAULT_SETTINGS = FundamentalDiagram(2.0, 5.0, 1.0, 1.0)
DEFAULT_SIMULATION_TIME = 20


@app.route("/")
def home():
    return "hello world"


@app.route("/parameters", methods=["GET"])
def get_parameters():
    result = {
        "freeflow_speed": DEFAULT_SETTINGS.freeflow_speed,
        "jam_density": DEFAULT_SETTINGS.jam_density,
        "traffic_wave_speed": DEFAULT_SETTINGS.trafficwave_speed,
        "init_density": DEFAULT_SETTINGS.init_density,
        "simulation_time": DEFAULT_SIMULATION_TIME,
    }

    return jsonify(result)


@app.route("/.well-known/acme-challenge/daU_nzxyw8w0nEjqjRwgvSRBujKzg_In0eSS092dZSI")
def certbot():
    return "daU_nzxyw8w0nEjqjRwgvSRBujKzg_In0eSS092dZSI.6wI3KO3aYOlguCK0isl5AGIxEQ8dLDxoLTngTjSOV2Y"


class DiagramPostBody(BaseModel):
    augment_info: str

    with_polygons: Optional[bool] = None
    num_trajectories: Optional[int] = None
    with_trajectories: Optional[bool] = None

    max_time: Optional[float] = None
    max_pos: Optional[float] = None

    settings: Optional[DiagramSettings] = None
    simulation_time: Optional[float] = None


@app.route("/diagram", methods=["POST"])
@validate()
def get_diagram(body: DiagramPostBody) -> Response:
    try:
        augments = parse(body.augment_info)
    except Exception as e:
        return Response(f"badly formed augment-info string: {str(e)}", status=400)

    try:
        drawer: ShockwaveDrawer
        if body.settings:
            drawer = ShockwaveDrawer(body.settings.create_fundamental_diagram(), augments)
        else:
            drawer = ShockwaveDrawer(DEFAULT_SETTINGS, augments)

        drawer.run(body.simulation_time or DEFAULT_SIMULATION_TIME)
    except Exception as e:
        print(e)
        return Response(f"failed to create shockwave diagram: {str(e)}", 500)

    figure = drawer._create_figure(
        body.num_trajectories or 100,
        with_trajectories=body.with_trajectories or True,
        with_polygons=body.with_polygons or True,
    )
    result: dict[str, Any] = asdict(figure)

    graph_polygon: dict[str, Any]
    for graph_polygon in result["polygons"]:
        graph_polygon["polygon"] = list(graph_polygon["polygon"].exterior.coords)

    trajectories: list[list[dict[str, float]]] = []
    for trajectory in figure.trajectories:
        cur_trajectory: list[dict[str, float]] = []
        for line in trajectory:
            cur_trajectory.append(asdict(line.point1))
        cur_trajectory.append(asdict(trajectory[-1].point2))
        trajectories.append(cur_trajectory)
    result["trajectories"] = trajectories

    for interface in result["interfaces"]:
        del interface["color"]
    for interface in result["user_interfaces"]:
        del interface["color"]

    result["states"] = list(drawer._get_states())

    return jsonify(result)


if __name__ == "__main__":
    app.run(
        "0.0.0.0",
        port=5000,
        debug=True,
        ssl_context=("certs/fullchain.pem", "certs/privkey.pem"),
        threaded=True,
    )
