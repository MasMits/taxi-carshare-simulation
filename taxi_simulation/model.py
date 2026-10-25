"""The city: square districts separated by one-cell roads.

Every row and column whose index is a multiple of (district_size + 1) is a road.
Taxis drive only on roads; routes respect their heading until a junction.
Passengers appear on road cells and call taxis; the model carries their messages.

Quick check:  python -m taxi_simulation.model
"""

from collections import deque

import mesa
from mesa.space import MultiGrid, PropertyLayer

from .agents import ASSIGNED, BOARDING, RIDING, WAITING, Passenger, Taxi

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
        max_wait: cancel an uncollected request after this many steps.
        traffic: enforce directional lanes and junction reservations.
        seed: random seed (reproducible runs).
    """

    def __init__(self, size=6, district_size=3, n_taxis=10, capacity=2,
                 allow_detour=False, demand=0.3, taxi_steps_per_cell=1, boarding_time=1,
                 max_detour=1.5, max_wait=60, traffic=True, seed=None):
        super().__init__(rng=seed)
        if max_wait <= 0 or taxi_steps_per_cell < 1 or boarding_time < 0:
            raise ValueError("max_wait and taxi_steps_per_cell must be positive; boarding_time nonnegative")
        self.size = size
        self.district_size = district_size
        self.capacity = capacity
        self.allow_detour = allow_detour
        self.demand = demand
        self.taxi_steps_per_cell = taxi_steps_per_cell
        self.boarding_time = boarding_time
        self.max_detour = max_detour
        self.max_wait = max_wait
        self.traffic = traffic
        self._move_requests = {}

        self.build_map()
        self.is_road = set(self.roads)
        self._distances = {}  # target -> {road cell: road distance to target}
        self._routes = {}

        for _ in range(n_taxis):
            self.grid.place_agent(Taxi(self), self.random_road_cell())

        # Statistics
        self.spawned = 0
        self.gave_up = 0
        self.messages_sent = 0
        self.trips = []  # finished trips: wait, ride, detour, shared

        # The DataCollector is an observer: it may read agent attributes,
        # agents may not read each other's (encapsulation).
        self.datacollector = mesa.DataCollector(model_reporters={
            "Waiting": lambda m: m.count(WAITING, ASSIGNED),
            "Riding": lambda m: m.count(BOARDING, RIDING),
            "Served": lambda m: len(m.trips),
            "Gave up": lambda m: m.gave_up,
            "Blocked taxis": lambda m: sum(t.blocked for t in m.taxis()),
            "Traffic delay": lambda m: sum(t.traffic_delay for t in m.taxis()),
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

    def build_map(self):
        """Build the default rectangular city; other road networks override this."""
        self.block = self.district_size + 1
        width = self.size * self.block + 1
        self.terrain = PropertyLayer("terrain", width, width, ROAD, dtype=int)
        self.grid = MultiGrid(width, width, torus=False, property_layers=[self.terrain])
        self.roads = []
        for x in range(width):
            for y in range(width):
                district = self.district_at((x, y))
                if district is None:
                    self.roads.append((x, y))
                else:
                    col, row = district % self.size, district // self.size
                    self.terrain.set_cell(
                        (x, y), DISTRICT_A if (col + row) % 2 == 0 else DISTRICT_B
                    )

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

    def next_cell(self, pos, target, heading=None):
        """Continue in-lane, or choose a shortest route at a junction."""
        if self.traffic and heading is not None and not self.is_intersection(pos):
            return (pos[0] + heading[0], pos[1] + heading[1])
        dist = self.distances_to(target)
        return min(self.road_neighbours(pos), key=lambda cell: dist[cell])

    def is_intersection(self, cell):
        return cell[0] % self.block == 0 and cell[1] % self.block == 0

    def route(self, start, target, heading=None):
        """Follow the current lane to a junction before turning or reversing."""
        key = (start, target, heading if self.traffic else None)
        if key not in self._routes:
            cells, cell = [], start
            while cell != target:
                nxt = self.next_cell(cell, target, heading)
                heading = self.direction(cell, nxt)
                cells.append(nxt)
                cell = nxt
            self._routes[key] = tuple(cells)
        return self._routes[key]

    # --- Traffic: simultaneous moves, separate lanes, reserved junction exits --

    def lane_key(self, cell, heading):
        """One slot per direction on roads; a junction is a shared conflict zone."""
        return (cell, None if self.is_intersection(cell) else heading)

    def request_move(self, taxi, destination):
        self._move_requests[taxi] = destination

    def resolve_traffic(self):
        """Use a single occupancy snapshot: no passing through a car that moves later.

        Junctions admit one car only when its exit lane is clear. That exit is
        reserved until the car leaves, preventing cars from blocking the box.
        Longest-waiting cars get priority; stable IDs break ties reproducibly.
        Idle taxis and taxis boarding passengers wait at the curb, off the lane.
        """
        occupied = {self.lane_key(t.pos, t.heading): t for t in self.taxis() if t.in_traffic}
        reserved = {self.lane_key(t.junction_exit, self.direction(t.pos, t.junction_exit)): t
                    for t in self.taxis() if t.junction_exit is not None}
        claimed = set()
        order = sorted(self._move_requests, key=lambda t: (-t.queue_wait, t.unique_id))
        for taxi in order:
            nxt = self._move_requests[taxi]
            heading = self.direction(taxi.pos, nxt)
            key = self.lane_key(nxt, heading)
            exit_cell = None
            keys = [key]
            if not taxi.in_traffic:
                keys.append(self.lane_key(taxi.pos, heading))
            if self.traffic and self.is_intersection(nxt) and nxt != taxi.plan[0].cell:
                exit_cell = self.next_cell(nxt, taxi.plan[0].cell, heading)
                keys.append(self.lane_key(exit_cell, self.direction(nxt, exit_cell)))
            blocked = self.traffic and any(
                (k in occupied and occupied[k] is not taxi)
                or (k in reserved and reserved[k] is not taxi) or k in claimed
                for k in keys
            )
            if blocked:
                taxi.blocked = True
                taxi.traffic_delay += 1
                taxi.queue_wait += 1
                continue
            claimed.update(keys)
            self.grid.move_agent(taxi, nxt)
            taxi.heading = heading
            taxi.junction_exit = exit_cell
            taxi.in_traffic = True
            taxi.progress = 0
            taxi.queue_wait = 0
            taxi.count_km()
            taxi.serve_stops_here()
            if not taxi.plan or taxi.boarding_left:
                taxi.park()
        self._move_requests.clear()

    @staticmethod
    def direction(start, end):
        return (end[0] - start[0], end[1] - start[1])

    def taxis(self):
        """All taxis of the city."""
        return self.agents.select(agent_type=Taxi)

    def taxi_directory(self):
        """Yellow pages: the taxis' addresses, so passengers can call them."""
        return self.taxis()

    def deliver(self, message):
        """Message transport: put the message in the receiver's mailbox."""
        if message.receiver in self.agents:
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

        Passengers act first (call, accept, cancel), then taxis answer and
        request moves, each group in random order. Resolve moves together
        before collecting statistics. One protocol round takes one step.
        """
        self.spawn_passengers()
        self.passengers().shuffle_do("step")
        self.taxis().shuffle_do("step")
        self.resolve_traffic()
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
