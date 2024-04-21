from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

from src.timeout import timeout
from src.augmenters.base_augmenter import CapacityBottleneck
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

    return jsonify(figure)


if __name__ == "__main__":
    app.run("0.0.0.0", port=3001, debug=False)
