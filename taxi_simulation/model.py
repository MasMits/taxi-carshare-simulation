"""The city: square districts separated by one-cell roads.

Every row and column whose index is a multiple of (district_size + 1) is a road.
Taxis drive only on roads, along the shortest route (breadth-first search).
Passengers appear on road cells and call taxis; the model carries their messages.

Quick check:  python -m taxi_simulation.model
"""

from collections import deque

import mesa
from mesa.space import MultiGrid, PropertyLayer

from .agents import ASSIGNED, RIDING, WAITING, Passenger, Taxi

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
        taxi_steps_per_cell: steps needed to drive along one road cell.
        boarding_time: steps needed to pick a passenger up.
        max_detour: accepted ride <= max_detour * direct time.
        seed: random seed (reproducible runs).
    """

    def __init__(self, size=6, district_size=3, n_taxis=10, capacity=2,
                 allow_detour=False, demand=0.6, taxi_steps_per_cell=1, boarding_time=1,
                 max_detour=1.5, seed=None):
        super().__init__(rng=seed)
        self.size = size
        self.district_size = district_size
        self.capacity = capacity
        self.allow_detour = allow_detour
        self.demand = demand
        self.taxi_steps_per_cell = taxi_steps_per_cell
        self.boarding_time = boarding_time
        self.max_detour = max_detour

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

        # Statistics
        self.spawned = 0
        self.messages_sent = 0
        self.trips = []  # finished trips: wait, ride, detour, shared

        # The DataCollector is an observer: it may read agent attributes,
        # agents may not read each other's (encapsulation).
        self.datacollector = mesa.DataCollector(model_reporters={
            "Waiting": lambda m: m.count(WAITING, ASSIGNED),
            "Riding": lambda m: m.count(RIDING),
            "Served": lambda m: len(m.trips),
            "Avg wait": lambda m: m.average("wait"),
            "Avg ride": lambda m: m.average("ride"),
            "Avg detour": lambda m: m.average("detour"),
            "Vehicle km": lambda m: m.vehicle_km(),
            "Km per passenger": lambda m: m.vehicle_km() / max(1, len(m.trips)),
            "Shared %": lambda m: 100 * m.average("shared"),
            "Empty km %": lambda m: 100 * sum(t.km_empty for t in m.taxis())
                                    / max(1, m.vehicle_km()),
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
        return self.taxi_steps_per_cell * self.distance(a, b)

    def next_cell(self, pos, target):
        """Next road cell on a shortest road route from pos to target."""
        dist = self.distances_to(target)
        return min(self.road_neighbours(pos), key=lambda cell: dist[cell])

    def taxis(self):
        """All taxis of the city."""
        return self.agents.select(agent_type=Taxi)

    def taxi_directory(self):
        """Yellow pages: the taxis' addresses, so passengers can call them."""
        return self.taxis()

    def deliver(self, message):
        """Message transport: put the message in the receiver's mailbox."""
        message.receiver.inbox.append(message)
        self.messages_sent += 1

    # --- Passengers -----------------------------------------------------------

    def spawn_passengers(self):
        """New requests of this step (Poisson). Trips shorter than one block are walked."""
        for _ in range(self.rng.poisson(self.demand)):
            origin = self.random_road_cell()
            destination = self.random_road_cell()
            while self.distance(origin, destination) < self.block:
                destination = self.random_road_cell()
            self.add_passenger(origin, destination)

    def add_passenger(self, origin, destination):
        passenger = Passenger(self, origin, destination)
        self.grid.place_agent(passenger, origin)
        self.spawned += 1
        return passenger

    def passengers(self):
        return self.agents.select(agent_type=Passenger)

    # --- Statistics -----------------------------------------------------------

    def record_trip(self, wait, ride, direct_time, shared):
        """Called by a passenger at the end of the trip."""
        self.trips.append({"wait": wait, "ride": ride,
                           "detour": ride / direct_time, "shared": shared})

    def count(self, *states):
        return sum(p.state in states for p in self.passengers())

    def average(self, key):
        return sum(t[key] for t in self.trips) / len(self.trips) if self.trips else 0

    def vehicle_km(self):
        return sum(taxi.km for taxi in self.taxis())

    # --- Scheduling -----------------------------------------------------------

    def step(self):
        """One step of the synchronous runtime.

        Passengers act first (call, accept), then taxis (answer, drive), each
        group in random order. One round of the protocol takes one step.
        """
        self.spawn_passengers()
        self.passengers().shuffle_do("step")
        self.taxis().shuffle_do("step")
        self.datacollector.collect(self)


if __name__ == "__main__":
    model = CityModel(seed=1)
    print(f"city: {model.size} x {model.size} districts, grid {model.grid.width} x "
          f"{model.grid.height} cells, {len(model.taxis())} taxis")
    for _ in range(200):
        model.step()
    data = model.datacollector.get_model_vars_dataframe().iloc[-1]
    print(f"after {model.steps} steps: {model.spawned} passengers, {int(data['Served'])} served")
    print(f"avg wait {data['Avg wait']:.1f} steps, avg ride {data['Avg ride']:.1f} steps, "
          f"avg detour {data['Avg detour']:.2f}, km per passenger {data['Km per passenger']:.1f}")
