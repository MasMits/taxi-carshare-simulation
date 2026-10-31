"""The city, whatever its map: agents, message transport, traffic, statistics.

Each map (grid, ring, irregular) is a subclass that builds its roads and says
how they connect: build_map, road_neighbours, is_intersection and direction.
Everything else (routes, traffic, passengers, statistics) works on any map.
"""

from collections import Counter

import mesa
import numpy as np

from taxi_simulation.core.passenger import ASSIGNED, BOARDING, CONFIRMING, RIDING, WAITING, Passenger
from taxi_simulation.core.roads import RoadMap
from taxi_simulation.core.taxi import Taxi
from taxi_simulation.core.traffic import Traffic


class CityModel(RoadMap, Traffic, mesa.Model):
    """Environment + scheduler of the simulation.

    All parameters of the simulation are defined here, so the sliders and the
    batch_run keys are the same for every map.

    Args:
        n_taxis: number of taxis.
        capacity: seats per taxi, 1 = classic taxi.
        allow_detour: False = no route change for shared rides.
        allow_multiple_pickups: allow a new next pickup while another pickup is pending.
        demand: mean number of new requests per step.
        taxi_steps_per_cell: steps needed to drive along one road cell.
        boarding_time: steps needed to pick a passenger up.
        max_detour: accepted ride <= max_detour * direct time.
        max_wait: search timeout before a taxi confirms; does not limit pickup time.
        pickup_slack: maximum extra pickup delay allowed when confirming an offer.
        cell_km: length of one road cell, in km.
        co2_per_km: CO2 a taxi emits per km driven, in grams.
        idle_co2_per_step: CO2 a taxi emits per step while stuck in traffic, in grams.
        stop_at: the simulation stops at this step (0 = never), so runs can be compared.
        seed: random seed (reproducible runs).
        scenario: given by Mesa's Reset to models that take **kwargs; not used.
    """

    def __init__(self, n_taxis=10, capacity=2, allow_detour=False, demand=0.3,
                 taxi_steps_per_cell=1, boarding_time=1, max_detour=1.5, max_wait=60,
                 pickup_slack=3,
                 cell_km=0.25, co2_per_km=150, idle_co2_per_step=25, stop_at=1000,
                 seed=None, scenario=None, allow_multiple_pickups=True):
        super().__init__(rng=seed)
        # Passenger requests have their own random generator: with the same seed,
        # every run gets the same passengers, whatever the taxis do. Runs with
        # 1 to 4 seats per taxi can then be compared fairly.
        self.demand_rng = np.random.default_rng(seed)
        if max_wait <= 0 or taxi_steps_per_cell < 1 or boarding_time < 0:
            raise ValueError("max_wait and taxi_steps_per_cell must be positive; boarding_time nonnegative")
        if pickup_slack < 0:
            raise ValueError("pickup_slack must be nonnegative")
        self.capacity = capacity
        self.allow_detour = allow_detour
        self.allow_multiple_pickups = allow_multiple_pickups
        self.demand = demand
        self.taxi_steps_per_cell = taxi_steps_per_cell
        self.boarding_time = boarding_time
        self.max_detour = max_detour
        self.max_wait = max_wait
        self.pickup_slack = pickup_slack
        self.cell_km = cell_km
        self.co2_per_km = co2_per_km
        self.idle_co2_per_step = idle_co2_per_step
        self.stop_at = stop_at

        self.build_map()
        self._distances = {}  # target -> {road cell: road distance to target}
        self._routes = {}
        self._move_requests = {}

        for _ in range(n_taxis):
            self.grid.place_agent(Taxi(self), self.random_road_cell())

        # Statistics
        self.spawned = 0
        self.gave_up = 0
        self.messages_sent = 0
        self.trips = []  # finished trips: wait, ride, detour, shared
        self.refusal_reasons = Counter()
        self.repeat_searches = 0
        self.alternative_attempts = 0
        self.confirmed_orders = 0
        self.pickup_violations = 0

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
            "Vehicle km": lambda m: m.driven_km(),
            "Km per passenger": lambda m: m.driven_km() / max(1, len(m.trips)),
            "Service %": lambda m: 100 * len(m.trips) / max(1, len(m.trips) + m.gave_up),
            "Shared %": lambda m: 100 * m.average("shared"),
            "Empty km %": lambda m: 100 * sum(t.km_empty for t in m.taxis())
                                    / max(1, m.vehicle_km()),
            "CO2 (kg)": lambda m: m.co2() / 1000,
            "CO2 per passenger (g)": lambda m: m.co2() / max(1, len(m.trips)),
        })
        self.datacollector.collect(self)

    # --- Agents and messages --------------------------------------------------

    def taxis(self):
        """All taxis of the city."""
        return self.agents.select(agent_type=Taxi)

    def taxi_directory(self):
        """Yellow pages: the taxis' addresses, so passengers can call them."""
        return self.taxis()

    def passengers(self):
        return self.agents.select(agent_type=Passenger)

    def deliver(self, message):
        """Message transport: put the message in the receiver's mailbox."""
        if message.receiver in self.agents:
            message.receiver.inbox.append(message)
            self.messages_sent += 1

    def spawn_passengers(self):
        """New requests of this step (Poisson). Trips shorter than min_trip are walked."""
        for _ in range(self.demand_rng.poisson(self.demand)):
            origin = self.random_request_cell()
            destination = self.random_request_cell()
            while self.distance(origin, destination) < self.min_trip:
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
        """Road cells driven by the whole fleet so far."""
        return sum(taxi.km for taxi in self.taxis())

    def driven_km(self):
        """Kilometres driven by the whole fleet so far."""
        return self.vehicle_km() * self.cell_km

    def co2(self):
        """CO2 emitted by the whole fleet so far, in grams."""
        return sum(taxi.co2 for taxi in self.taxis())

    # --- Scheduling -----------------------------------------------------------

    def step(self):
        """One step of the synchronous runtime.

        Passengers act first (call, accept, cancel), then taxis answer and
        request moves, each group in random order. Resolve moves together
        before collecting statistics. One protocol round takes one step.
        """
        if not self.running:
            return  # finished at stop_at; the interface may still ask for a few steps
        self.spawn_passengers()
        self.passengers().shuffle_do("step")
        self.taxis().shuffle_do("step")
        self.resolve_traffic()
        self.datacollector.collect(self)
        if self.stop_at and self.steps >= self.stop_at:
            self.running = False  # the interface stops playing here
