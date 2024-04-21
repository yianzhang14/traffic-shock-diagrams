from abc import ABC, abstractmethod

from src.shockwave_drawer import ShockwaveDrawer


# TODO: fully flesh this out
class TrafficAugmenter(ABC):
    """Abstract base class of all augmenters of the dt-space."""

    @abstractmethod
    def init(self, drawer: ShockwaveDrawer):
        """Initializes an augmenter in the shockwave drawer life cycle. Creates all events the
        augment would generate during the simulation time of the drawer.

        Args:
            simulation_time (float): how long the simulation will last for
            events (SortedList): reference to the event queue
            interfaces (list[Interface]): reference to the list of interfaces
        """
        pass


class CapacityBottleneck(TrafficAugmenter):
    def __init__(self, bottleneck: float):
        self.bottleneck = bottleneck
