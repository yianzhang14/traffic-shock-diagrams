from abc import ABC, abstractmethod

from sortedcontainers import SortedList

from src.diagram_utils import Interface


# TODO: fully flesh this out
class TrafficAugmenter(ABC):
    """Abstract base class of all augmenters of the dt-space."""

    @abstractmethod
    def init(self, simulation_time: float, events: SortedList, interfaces: list[Interface]):
        """Initializes an augmenter in the shockwave drawer life cycle. Creates all events the
        augment would generate during the simulation time of the drawer.

        Args:
            simulation_time (float): how long the simulation will last for
            events (SortedList): reference to the event queue
            interfaces (list[Interface]): reference to the list of interfaces
        """
        pass
