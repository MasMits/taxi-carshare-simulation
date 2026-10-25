"""Graph-city example: two circular roads, radial streets and a centre."""

import math

from .graph_model import RoadGraphModel


class RingCityModel(RoadGraphModel):
    """Build rings using the shared agents, directional road slots and traffic."""

    map_title = "Ring-road simulation: two rings, radial streets and a city centre"
    map_labels = [(0, 17.1, "Outer ring"), (0, 9.3, "Inner ring")]

    def __init__(self, arms=8, **kwargs):
        if arms not in (4, 6, 8, 10, 12):
            raise ValueError("arms must be one of 4, 6, 8, 10 or 12")
        self.arms = arms
        super().__init__(**kwargs)

    def build_map(self):
        self.initialize_network()
        rings = []
        for ring_index, radius in enumerate((8.0, 15.0)):
            ring = []
            for i in range(self.arms):
                angle = 2 * math.pi * i / self.arms
                ring.append(self.add_junction(ring_index * self.arms + i,
                                             radius * math.cos(angle), radius * math.sin(angle)))
            rings.append(ring)
        centre = self.add_junction(2 * self.arms, 0, 0)

        for ring, radius in zip(rings, (8.0, 15.0)):
            for i in range(self.arms):
                angle = 2 * math.pi * i / self.arms
                span = 2 * math.pi / self.arms
                self.add_section(ring[i], ring[(i + 1) % self.arms],
                                 lambda t, r=radius, a=angle, s=span: (r * math.cos(a + t * s),
                                                                    r * math.sin(a + t * s)),
                                 radius * span)
        for i in range(self.arms):
            self.add_straight(rings[0][i], rings[1][i])
            self.add_straight(centre, rings[0][i])

        self.finish_network()
