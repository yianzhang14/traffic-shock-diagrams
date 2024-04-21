import ast
from typing import Any

from src.augmenters.base_augmenter import CapacityBottleneck
from src.augmenters.linear_bottleneck import HorizontalBottleneck, LineBottleneck
from src.augmenters.traffic_light import TrafficLight
from src.drawer_utils import dtPoint


def convert_to_dtpoint(args: list[Any]) -> None:
    for i in range(len(args)):
        cur = args[i]
        if (
            isinstance(cur, tuple)
            and len(cur) == 2
            and isinstance(cur[0], (float, int))
            and isinstance(cur[1], (float, int))
        ):
            args[i] = dtPoint(cur[0], cur[1])


def parse(config_str: str) -> list[CapacityBottleneck]:
    augments: list[CapacityBottleneck] = []
    config_str = config_str.replace(" ", "")

    for line in config_str.split(";"):
        if len(line) == 0:
            continue

        tokens = line.split(",")
        bottleneck_type = tokens[0]
        args: list[Any] = ast.literal_eval(f"[{','.join((tokens[1:-1]))}]")
        kwargs: dict[str, Any] = ast.literal_eval(tokens[-1])
        convert_to_dtpoint(args)

        augment: CapacityBottleneck
        match bottleneck_type:
            case "tl":  # traffic light
                augment = TrafficLight(*args, **kwargs)
            case "hb":  # horizontal bottleneck
                augment = HorizontalBottleneck(*args, **kwargs)
            case "lb":
                continue
                augment = LineBottleneck(*args, **kwargs)
            case _:
                continue

        augments.append(augment)

    return augments
