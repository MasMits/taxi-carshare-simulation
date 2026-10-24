"""The city: square districts separated by one-cell roads.

Every row and column whose index is a multiple of (district_size + 1) is a road.
Taxis drive only on roads, along the shortest route (breadth-first search).

Quick check:  python -m taxi_simulation.model
"""

from collections import deque

import mesa
from mesa.space import MultiGrid, PropertyLayer

from .agents import Taxi

# Values of the "terrain" layer, used to draw the map.
DISTRICT_A = 0  # districts are painted as a checkerboard of A and B
DISTRICT_B = 1
ROAD = 2


class CityModel(mesa.Model):
    """Environment + scheduler of the simulation.

    All parameters of the simulation are defined here, so the sliders and the
    batch_run keys stay the same.

    Args:
        size: the city is size x size districts.
        district_size: side of one district, in cells.
        n_taxis: number of taxis.
        capacity: seats per taxi, 1 = classic taxi.
        allow_detour: False = no route change for shared rides.
        demand: mean number of new requests per step.
        crossing_time: steps needed to drive along one road cell.
        boarding_time: steps needed to pick a passenger up.
        max_wait: passenger patience in steps.
        max_detour: accepted ride <= max_detour * direct time.
        warmup: statistics ignore requests made before this step.
        seed: random seed (reproducible runs).
    """

    def __init__(self, size=6, district_size=3, n_taxis=10, capacity=2,
                 allow_detour=True, demand=0.6, crossing_time=1, boarding_time=1,
                 max_wait=20, max_detour=1.5, warmup=0, seed=None):
        super().__init__(rng=seed)  # `seed=` is deprecated since Mesa 3.5
        self.size = size
        self.district_size = district_size
        self.capacity = capacity
        self.allow_detour = allow_detour
        self.demand = demand
        self.crossing_time = crossing_time
        self.boarding_time = boarding_time
        self.max_wait = max_wait
        self.max_detour = max_detour
        self.warmup = warmup

        # A road every `block` cells, including the city border.
        self.block = district_size + 1
        width = size * self.block + 1
        self.terrain = PropertyLayer("terrain", width, width, ROAD, dtype=int)
        self.grid = MultiGrid(width, width, torus=False, property_layers=[self.terrain])

        self.roads = []  # every cell a taxi may drive on
        for x in range(width):
            for y in range(width):
                district = self.district_at((x, y))
                if district is None:
                    self.roads.append((x, y))
                else:
                    col, row = district % size, district // size
                    self.terrain.set_cell(
                        (x, y), DISTRICT_A if (col + row) % 2 == 0 else DISTRICT_B
                    )
        self.is_road = set(self.roads)
        self._distances = {}  # target -> {road cell: road distance to target}

        for _ in range(n_taxis):
            self.grid.place_agent(Taxi(self), self.random_road_cell())

        # The DataCollector is an observer: it may read agent attributes,
        # agents may not read each other's (encapsulation).
        self.datacollector = mesa.DataCollector(model_reporters={
            "Vehicle km": lambda m: sum(taxi.km for taxi in m.taxis()),
        })
        self.datacollector.collect(self)

    # --- Map ------------------------------------------------------------------

    def district_at(self, cell):
        """District id of a cell, or None if the cell is a road."""
        x, y = cell
        if x % self.block == 0 or y % self.block == 0:
            return None
        return (y // self.block) * self.size + x // self.block

    def road_neighbours(self, cell):
        """Road cells reachable in one move (no diagonals)."""
        x, y = cell
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nxt in self.is_road:
                yield nxt

    def distances_to(self, target):
        """Road distance from every road cell to target (breadth-first search).

        Computed once per target and cached: the map never changes.
        """
        if target not in self._distances:
            dist, queue = {target: 0}, deque([target])
            while queue:
                cell = queue.popleft()
                for nxt in self.road_neighbours(cell):
                    if nxt not in dist:
                        dist[nxt] = dist[cell] + 1
                        queue.append(nxt)
            self._distances[target] = dist
        return self._distances[target]

    # --- Environment services: what agents may perceive and use -------------

    def random_road_cell(self):
        """A random road cell of the city."""
        return self.random.choice(self.roads)

    def distance(self, a, b):
        """Number of road cells to drive from a to b."""
        return self.distances_to(b)[a]

    def travel_time(self, a, b):
        """Steps a taxi needs to drive from road cell a to road cell b."""
        return self.crossing_time * self.distance(a, b)

    def next_cell(self, pos, target):
        """Next road cell on a shortest road route from pos to target."""
        dist = self.distances_to(target)
        return min(self.road_neighbours(pos), key=lambda cell: dist[cell])

    def taxis(self):
        """All taxis of the city."""
        return self.agents.select(agent_type=Taxi)

    # --- Scheduling -----------------------------------------------------------

    def step(self):
        """One step of the synchronous runtime: every taxi acts once (random order)."""
        self.taxis().shuffle_do("step")
        self.datacollector.collect(self)


if __name__ == "__main__":
    # Follow one taxi: it moves one road cell every `crossing_time` steps.
    model = CityModel(n_taxis=1, crossing_time=2, seed=1)
    taxi = model.taxis().to_list()[0]
    print(f"city: {model.size} x {model.size} districts, grid {model.grid.width} x "
          f"{model.grid.height} cells, {len(model.roads)} road cells")
    for _ in range(12):
        model.step()
        print(f"step {model.steps:2}: taxi on {taxi.pos} (road: {taxi.pos in model.is_road}), "
              f"target {taxi.target}, km {taxi.km}")
