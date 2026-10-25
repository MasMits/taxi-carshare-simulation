"""Seeded, connected irregular city: unequal blocks, loops and dead-end streets."""

import math
import random

import networkx as nx

from .graph_model import RoadGraphModel


def streets_cross(a, b, c, d):
    """Detect a proper crossing between roads without a shared endpoint."""
    def orientation(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return orientation(a, b, c) * orientation(a, b, d) < -1e-9 and (
        orientation(c, d, a) * orientation(c, d, b) < -1e-9
    )


class IrregularCityModel(RoadGraphModel):
    """Connect scattered junctions with a Euclidean minimum spanning tree.

    Add short non-crossing roads to form loops, preserving cul-de-sacs.
    Map randomness is independent of the agents' seed. Each visible crossing
    is an actual junction; roads have discrete slots in both directions.
    """

    map_title = "Irregular city: unequal street lengths, junctions, loops and dead ends"
    map_labels = []

    def __init__(self, map_seed=7, junction_count=28, extra_roads=0.65, **kwargs):
        if not 12 <= junction_count <= 40:
            raise ValueError("junction_count must be between 12 and 40")
        if not 0 <= extra_roads <= 1:
            raise ValueError("extra_roads must be between 0 and 1")
        self.map_seed = map_seed
        self.junction_count = junction_count
        self.extra_roads = extra_roads
        super().__init__(**kwargs)

    def build_map(self):
        self.initialize_network()
        map_rng = random.Random(self.map_seed)
        points = []
        for _ in range(10000):
            candidate = (map_rng.uniform(-14.5, 14.5), map_rng.uniform(-14.5, 14.5))
            if all(math.dist(candidate, point) >= 3.0 for point in points):
                points.append(candidate)
            if len(points) == self.junction_count:
                break
        else:
            raise ValueError("Could not place the requested junctions")

        candidates = nx.Graph()
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                candidates.add_edge(i, j, length=math.dist(points[i], points[j]))
        streets = nx.minimum_spanning_tree(candidates, weight="length")
        protected = set(sorted(node for node, degree in streets.degree if degree == 1)[:3])
        ordered = sorted(candidates.edges(data=True), key=lambda e: e[2]["length"])
        for a, b, data in ordered:
            if streets.has_edge(a, b) or a in protected or b in protected:
                continue
            if data["length"] > 11 or streets.degree[a] >= 4 or streets.degree[b] >= 4:
                continue
            if map_rng.random() > self.extra_roads:
                continue
            if any(streets_cross(points[a], points[b], points[c], points[d])
                   for c, d in streets.edges if not {a, b} & {c, d}):
                continue
            if not all(self.wide_enough(streets, points, u, v) for u, v in ((a, b), (b, a))):
                continue
            streets.add_edge(a, b, **data)

        self.street_graph = streets
        nodes = [self.add_junction(i, *point) for i, point in enumerate(points)]
        for a, b in sorted(streets.edges):
            self.add_straight(nodes[a], nodes[b])
        self.finish_network()

    @staticmethod
    def wide_enough(streets, points, start, end):
        """Avoid acute added forks whose lanes would visually overlap."""
        x, y = points[start]
        dx, dy = points[end][0] - x, points[end][1] - y
        for neighbour in streets[start]:
            nx_, ny_ = points[neighbour][0] - x, points[neighbour][1] - y
            cosine = (dx * nx_ + dy * ny_) / (math.hypot(dx, dy) * math.hypot(nx_, ny_))
            if cosine > math.cos(math.radians(30)):
                return False
        return True
