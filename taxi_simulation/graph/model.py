"""Road-graph city: junctions joined by road sections, on a Mesa NetworkGrid.

Each section is cut into slots (graph nodes) with one lane per direction.
The graph decides how taxis move; coordinates are only used to draw the map.
"""

import math

import networkx as nx
from mesa.space import NetworkGrid

from taxi_simulation.core.model import CityModel


class GraphCityModel(CityModel):
    """Base of the ring and irregular cities: they only add their build_map."""

    map_labels = []  # (x, y, text) written on the map

    def __init__(self, n_taxis=16, allow_detour=True, **kwargs):
        super().__init__(n_taxis=n_taxis, allow_detour=allow_detour, **kwargs)

    def start_network(self):
        self.network = nx.Graph()
        self.coordinates = {}
        self.junctions = set()
        self.sections = []
        self._directions = {}
        self.min_trip = 4

    def add_junction(self, index, x, y):
        node = (-1, index)
        self.junctions.add(node)
        self.coordinates[node] = (x, y)
        self.network.add_node(node)
        return node

    def add_section(self, start, end, point, length):
        """A road from start to end; point(t) gives its shape for t in [0, 1]."""
        section_id = len(self.sections)
        steps = max(2, math.ceil(length / 1.5))
        nodes = [start]
        for i in range(1, steps):
            node = (section_id, i)
            self.coordinates[node] = point(i / steps)
            nodes.append(node)
        nodes.append(end)
        for a, b in zip(nodes, nodes[1:]):
            self.network.add_edge(a, b)
            self._directions[a, b] = (section_id, 1)
            self._directions[b, a] = (section_id, -1)
        self.sections.append(tuple(nodes))

    def add_straight(self, start, end):
        x1, y1 = self.coordinates[start]
        x2, y2 = self.coordinates[end]
        self.add_section(start, end, lambda t: (x1 + t * (x2 - x1), y1 + t * (y2 - y1)),
                         math.hypot(x2 - x1, y2 - y1))

    def finish_network(self):
        nx.set_node_attributes(self.network, self.coordinates, "pos")
        self.grid = NetworkGrid(self.network)
        self.roads = list(self.network)

    def road_neighbours(self, cell):
        return iter(self.network[cell])

    def is_intersection(self, cell):
        return cell in self.junctions

    def direction(self, start, end):
        return self._directions[start, end]
