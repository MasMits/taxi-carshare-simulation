"""Shared road-graph space for cities with discrete, directional lane slots."""

import math

import networkx as nx
from mesa.space import NetworkGrid

from .model import CityModel


class RoadGraphModel(CityModel):
    """Geometry draws roads; topology and (section, direction) control traffic."""

    def __init__(self, n_taxis=16, allow_detour=True, scenario=None, **kwargs):
        # Mesa's Reset supplies a default Scenario; these demos use explicit parameters.
        super().__init__(n_taxis=n_taxis, allow_detour=allow_detour, **kwargs)

    def initialize_network(self):
        self.network = nx.Graph()
        self.coordinates = {}
        self.junctions = set()
        self.sections = []
        self._directions = {}
        self.block = 4

    def add_junction(self, index, x, y):
        node = (-1, index)
        self.junctions.add(node)
        self.coordinates[node] = (x, y)
        self.network.add_node(node)
        return node

    def add_section(self, start, end, point, length):
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

    def next_cell(self, pos, target, heading=None):
        if self.traffic and heading is not None and not self.is_intersection(pos):
            return next(n for n in self.network[pos] if self.direction(pos, n) == heading)
        distances = self.distances_to(target)
        return min(self.network[pos], key=lambda node: distances[node])

    def lane_vector(self, pos, heading):
        """Local road tangent, for drawing vehicles on the correct side."""
        if heading is None:
            return (1.0, 0.0)
        for neighbour in self.network[pos]:
            if self.direction(pos, neighbour) == heading:
                a, b = self.coordinates[pos], self.coordinates[neighbour]
                break
            if self.direction(neighbour, pos) == heading:
                a, b = self.coordinates[neighbour], self.coordinates[pos]
                break
        else:
            return (1.0, 0.0)
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        return ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
