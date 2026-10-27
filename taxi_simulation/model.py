"""The city: square districts separated by one-cell roads.

Every row and column whose index is a multiple of (district_size + 1) is a road.
Taxis drive only on roads; routes respect their heading until a junction.
Passengers appear on road cells and call taxis; the model carries their messages.

Quick check:  python -m taxi_simulation.model
"""

from collections import Counter, deque

import mesa
import numpy as np
from mesa.space import MultiGrid, PropertyLayer

from .agents import ASSIGNED, BOARDING, CONFIRMING, RIDING, WAITING, Passenger, Taxi

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
        max_wait: search timeout before a taxi confirms; does not limit pickup time.
        offer_ttl: validity of a proposal in steps; alternatives survive a failed acceptance.
        pickup_slack: maximum extra pickup delay allowed when confirming an offer.
        wait_priority: time-cost discount per step the requesting passenger has waited.
        traffic: enforce directional lanes and junction reservations.
        cell_km: length of one road cell, in km.
        co2_per_km: CO2 a taxi emits per km driven, in grams.
        idle_co2_per_step: CO2 a taxi emits per step while stuck in traffic, in grams.
        stop_at: the simulation stops at this step (0 = never), so runs can be compared.
        seed: random seed (reproducible runs).
    """

    def __init__(self, size=6, district_size=3, n_taxis=10, capacity=2,
                 allow_detour=False, demand=0.3, taxi_steps_per_cell=1, boarding_time=1,
                 max_detour=1.5, max_wait=60, traffic=True,
                 cell_km=0.25, co2_per_km=150, idle_co2_per_step=25, stop_at=1000, seed=None,
                 offer_ttl=6, pickup_slack=3, wait_priority=0.5):
        super().__init__(rng=seed)
        # Passenger requests have their own random generator: with the same seed,
        # every run gets the same passengers, whatever the taxis do. Runs with
        # 1 to 4 seats per taxi can then be compared fairly.
        self.demand_rng = np.random.default_rng(seed)
        if max_wait <= 0 or taxi_steps_per_cell < 1 or boarding_time < 0:
            raise ValueError("max_wait and taxi_steps_per_cell must be positive; boarding_time nonnegative")
        if offer_ttl < 1 or pickup_slack < 0 or wait_priority < 0:
            raise ValueError("offer_ttl must be positive; pickup_slack and wait_priority nonnegative")
        self.offer_ttl = offer_ttl
        self.pickup_slack = pickup_slack
        self.wait_priority = wait_priority
        self.refusal_reasons = Counter()
        self.repeat_searches = 0
        self.alternative_attempts = 0
        self.confirmed_orders = 0
        self.pickup_violations = 0
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
        self.cell_km = cell_km
        self.co2_per_km = co2_per_km
        self.idle_co2_per_step = idle_co2_per_step
        self.stop_at = stop_at
        self._move_requests = {}

        self.build_map()
        self.is_road = set(self.roads)
        self._distances = {}  # target -> {road cell: road distance to target}
        self._routes = {}
        self._pickup_routes = {}
        self._pickup_distances = {}

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
            "Waiting": lambda m: m.count(WAITING, CONFIRMING, ASSIGNED),
            "Riding": lambda m: m.count(BOARDING, RIDING),
            "Served": lambda m: len(m.trips),
            "Gave up": lambda m: m.gave_up,
            "Confirming": lambda m: m.count(CONFIRMING),
            "Repeat searches": lambda m: m.repeat_searches,
            "Alternative attempts": lambda m: m.alternative_attempts,
            "Confirmed orders": lambda m: m.confirmed_orders,
            "Pickup violations": lambda m: m.pickup_violations,
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
            "CO2 (kg)": lambda m: m.co2() / 1000,
            "CO2 per passenger (g)": lambda m: m.co2() / max(1, len(m.trips)),
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

    def pickup_route(self, start, pickup, onward, heading=None):
        """Reach a pickup facing a shortest onward leg; turn while still empty.

        Search cell/heading states, since passing a pickup in the wrong lane is
        not a service stop. Reverse distances are shared by all starts and all
        destinations requiring the same arrival direction at this pickup.
        """
        route = self.route(start, pickup, heading)
        if not self.traffic or onward == pickup or self.is_intersection(pickup):
            return route
        distance = self.distances_to(onward)
        arrivals = frozenset(self.direction(pickup, nxt) for nxt in self.road_neighbours(pickup)
                             if distance[nxt] == distance[pickup] - 1)
        arrival = self.direction(route[-2] if len(route) > 1 else start, route[-1]) if route else heading
        if arrival is None or arrival in arrivals:
            return route
        key = (pickup, arrivals)
        if key not in self._pickup_distances:
            distances = {(pickup, direction): 0 for direction in arrivals}
            queue = deque(distances)
            while queue:
                cell, direction = queue.popleft()
                for previous in self.road_neighbours(cell):
                    if self.direction(previous, cell) != direction:
                        continue
                    headings = ({self.direction(neighbour, previous)
                                 for neighbour in self.road_neighbours(previous)}
                                if self.is_intersection(previous) else (direction,))
                    for previous_heading in headings:
                        state = (previous, previous_heading)
                        if state not in distances:
                            distances[state] = distances[cell, direction] + 1
                            queue.append(state)
            self._pickup_distances[key] = distances
        route_key = (start, pickup, arrivals, heading)
        if route_key not in self._pickup_routes:
            distances = self._pickup_distances[key]
            state, cells, states = (start, heading), [], []
            while state[0] != pickup or state[1] not in arrivals:
                cell, direction = state
                neighbours = [(nxt, self.direction(cell, nxt)) for nxt in self.road_neighbours(cell)
                              if direction is None or self.is_intersection(cell)
                              or self.direction(cell, nxt) == direction]
                state = min(neighbours, key=lambda nxt: distances[nxt])
                cells.append(state[0])
                states.append(state)
            cells = tuple(cells)
            for index, state in enumerate([(start, heading)] + states):
                self._pickup_routes[state[0], pickup, arrivals, state[1]] = cells[index:]
        return self._pickup_routes[route_key]

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
                exit_cell = taxi.route_to_stop(taxi.plan, 0, cell=nxt, heading=heading, first=False)[0]
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
                taxi.count_idle()
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
        for _ in range(self.demand_rng.poisson(self.demand)):
            origin = self.random_request_cell()
            destination = self.random_request_cell()
            while self.distance(origin, destination) < self.block:
                destination = self.random_request_cell()
            self.add_passenger(origin, destination)

    def random_request_cell(self):
        """A random road cell for a passenger request (own generator, see __init__)."""
        return self.roads[self.demand_rng.integers(len(self.roads))]

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

    def co2(self):
        """CO2 emitted by the whole fleet so far, in grams."""
        return sum(taxi.co2 for taxi in self.taxis())

    def driven_km(self):
        """Kilometres driven by the whole fleet so far."""
        return self.vehicle_km() * self.cell_km

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
        if self.stop_at and self.steps >= self.stop_at:
            self.running = False  # the interface stops playing here


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
    print(f"CO2: {data['CO2 (kg)']:.1f} kg in total, {data['CO2 per passenger (g)']:.0f} g per passenger")
