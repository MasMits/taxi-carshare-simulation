"""Agents of the taxi carshare simulation: passengers and taxis.

Every agent follows the procedural loop perceive -> decide -> act and does at
most one physical action per step. Agents never read each other's attributes:
they only exchange messages (contract net protocol).
"""

from dataclasses import dataclass

from .messages import ACCEPT, CFP, FAILURE, INFORM, PROPOSE, REFUSE, REJECT, MessageAgent

# Passenger states
WAITING = "waiting"
ASSIGNED = "assigned"
RIDING = "riding"
ARRIVED = "arrived"

# Kinds of stop in a taxi plan
PICKUP = "pickup"
DROPOFF = "dropoff"

# Taxi actions
BOARD = "board"
SERVE = "serve"
DRIVE = "drive"
WAIT = "wait"


class Passenger(MessageAgent):
    """A person who needs a ride. Initiator of the contract net.

    Beliefs:
        origin, destination: road cells of the trip.
        request_step: step when the passenger appeared.
        direct_time: duration of the ride without any detour.
        max_ride: longest ride the passenger accepts.
        state: WAITING, ASSIGNED, RIDING or ARRIVED.
        pickup_step, arrival_step: told by the taxi.
        shared: whether the taxi was shared during the ride.
    """

    def __init__(self, model, origin, destination):
        super().__init__(model)
        self.origin = origin
        self.destination = destination
        self.request_step = model.steps
        self.direct_time = model.travel_time(origin, destination)
        self.max_ride = model.max_detour * self.direct_time
        self.state = WAITING
        self.pickup_step = None
        self.arrival_step = None
        self.shared = False

    def trip(self):
        """What the passenger tells the taxis."""
        return {"pickup": self.origin, "dropoff": self.destination, "max_ride": self.max_ride}

    def step(self):
        proposals = self.perceive()
        action, offer = self.decide(proposals)
        self.act(action, offer, proposals)

    def perceive(self):
        """Update beliefs from the taxis' messages; return the new offers."""
        proposals = []
        for msg in self.receive():
            if msg.performative == PROPOSE:
                proposals.append(msg)
            elif msg.performative == FAILURE:
                self.state = WAITING  # the taxi could not keep its offer
            elif msg.performative == INFORM and msg.content["event"] == "picked_up":
                self.state = RIDING
                self.pickup_step = msg.content["step"]
            elif msg.performative == INFORM and msg.content["event"] == "arrived":
                self.state = ARRIVED
                self.arrival_step = msg.content["step"]
                self.shared = msg.content["shared"]
        return proposals

    def decide(self, proposals):
        """Return (action, chosen offer)."""
        if self.state == ARRIVED:
            return "leave", None
        if self.state == RIDING:
            return ("get in", None) if self.pos is not None else ("wait", None)
        if self.state == ASSIGNED:
            return "wait", None

        acceptable = [p for p in proposals if p.content["ride"] <= self.max_ride]
        if acceptable:
            # The best offer brings the passenger to the destination earliest.
            best = min(acceptable, key=lambda p: p.content["pickup_eta"] + p.content["ride"])
            return "accept", best
        return "call", None

    def act(self, action, offer, proposals):
        if action == "accept":
            self.send(offer.sender, ACCEPT, self.trip(), self.unique_id)
            for proposal in proposals:
                if proposal is not offer:
                    self.send(proposal.sender, REJECT, conversation_id=self.unique_id)
            self.state = ASSIGNED
        elif action == "call":
            for taxi in self.model.taxi_directory():
                self.send(taxi, CFP, self.trip(), self.unique_id)
        elif action == "get in":
            self.model.grid.remove_agent(self)  # now inside the taxi
        elif action == "leave":
            self.model.record_trip(wait=self.pickup_step - self.request_step,
                                   ride=self.arrival_step - self.pickup_step,
                                   direct_time=self.direct_time,
                                   shared=self.shared)
            self.remove()

    def remove(self):
        """Leave the grid too: Agent.remove() does not do it for a MultiGrid."""
        if self.pos is not None:
            self.model.grid.remove_agent(self)
        super().remove()


@dataclass
class Stop:
    """One stop of a taxi plan."""

    cell: tuple[int, int]
    kind: str               # PICKUP or DROPOFF
    passenger: Passenger    # address for messages, its attributes are never read
    max_ride: float         # passenger tolerance, received in the call for proposals


class Taxi(MessageAgent):
    """A taxi driving along the roads. Participant of the contract net.

    A taxi takes up to `capacity` passengers. For each call it looks for the
    cheapest way to insert the new pickup and drop-off into its plan, without
    making anyone's ride longer than they accept.

    Beliefs:
        plan: stops still to visit, in order.
        onboard: passenger -> step when they are fully on board.
        shared: passengers who shared the taxi during their ride.
        boarding, boarding_left: passenger getting in, and steps still needed.
        progress: steps already spent on the current road cell.
        km, km_empty: road cells driven, in total and with nobody on board.
    """

    def __init__(self, model):
        super().__init__(model)
        self.plan = []
        self.onboard = {}
        self.shared = set()
        self.boarding = None
        self.boarding_left = 0
        self.progress = 0
        self.km = 0
        self.km_empty = 0

    def step(self):
        messages = self.receive()       # perceive
        action = self.decide(messages)  # deliberate
        self.act(action)                # act

    def decide(self, messages):
        # Accepts first: they change the plan the next answers depend on.
        for msg in sorted(messages, key=lambda m: m.performative != ACCEPT):
            if msg.performative not in (ACCEPT, CFP):
                continue  # REJECT: nothing to undo, taxis keep no reservation
            best = self.best_insertion(msg.content, msg.sender)
            if msg.performative == ACCEPT:
                if best:
                    self.plan = best[1]
                else:
                    self.send(msg.sender, FAILURE)  # the plan changed since the offer
            elif best:
                pickup_t, dropoff_t = best[2]
                self.send(msg.sender, PROPOSE,
                          {"pickup_eta": pickup_t, "ride": dropoff_t - pickup_t})
            else:
                self.send(msg.sender, REFUSE)

        if self.boarding_left > 0:
            return BOARD
        if self.plan and self.plan[0].cell == self.pos:
            return SERVE
        return DRIVE if self.plan else WAIT

    # --- Planning ---------------------------------------------------------------

    def booked(self):
        """Passengers on board or waiting for this taxi."""
        return len(self.onboard) + sum(stop.kind == PICKUP for stop in self.plan)

    def plan_distance(self, plan):
        """Road cells to drive to visit all the stops of a plan."""
        cells = [self.pos] + [stop.cell for stop in plan]
        return sum(self.model.distance(a, b) for a, b in zip(cells, cells[1:]))

    def evaluate(self, plan):
        """Simulate a plan from the current road cell.

        Returns (finish_time, times) with times[p] = (pickup_t, dropoff_t)
        relative to now, or None if someone's ride would exceed their max_ride.
        """
        m = self.model
        t, cell = self.boarding_left, self.pos
        picked = {p: step - m.steps for p, step in self.onboard.items()}  # already (getting) in
        times = {}
        for stop in plan:
            t += m.travel_time(cell, stop.cell)
            cell = stop.cell
            if stop.kind == PICKUP:
                t += m.boarding_time  # everyone inside waits while a new passenger gets in
                picked[stop.passenger] = t
            elif t - picked[stop.passenger] > stop.max_ride:
                return None  # too long a ride for this passenger
            else:
                times[stop.passenger] = (picked[stop.passenger], t)
        return t, times

    def best_insertion(self, trip, passenger):
        """Cheapest feasible plan that also serves the new trip.

        The pickup goes at position i, the drop-off at position j >= i; the
        existing stops keep their order. Without detours, the new passenger
        must be on the current route. Returns (finish_time, plan,
        (pickup_t, dropoff_t)) or None.
        """
        if self.booked() >= self.model.capacity:
            return None
        pickup = Stop(trip["pickup"], PICKUP, passenger, trip["max_ride"])
        dropoff = Stop(trip["dropoff"], DROPOFF, passenger, trip["max_ride"])
        old_distance = self.plan_distance(self.plan)
        best = None
        for i in range(len(self.plan) + 1):
            for j in range(i, len(self.plan) + 1):
                plan = self.plan[:i] + [pickup] + self.plan[i:j] + [dropoff] + self.plan[j:]
                if (self.plan and not self.model.allow_detour
                        and self.plan_distance(plan) > old_distance):
                    continue  # the current route may not change
                result = self.evaluate(plan)
                if result is not None and (best is None or result[0] < best[0]):
                    best = (result[0], plan, result[1][passenger])
        return best

    # --- Acting -----------------------------------------------------------------

    def act(self, action):
        if action == BOARD:
            self.boarding_left -= 1
            if self.boarding_left == 0:
                self.finish_boarding()
                self.serve_stops_here()
        elif action == SERVE:
            self.serve_stops_here()
        elif action == DRIVE:
            # Driving along a road cell takes `taxi_steps_per_cell` steps,
            # then the taxi moves to the next one.
            self.progress += 1
            if self.progress >= self.model.taxi_steps_per_cell:
                self.progress = 0
                self.model.grid.move_agent(self, self.model.next_cell(self.pos, self.plan[0].cell))
                self.count_km()
                self.serve_stops_here()

    def serve_stops_here(self):
        """Serve the stops on this cell in plan order.

        A drop-off is instantaneous; a pickup starts boarding, which takes
        `boarding_time` steps.
        """
        while self.boarding_left == 0 and self.plan and self.plan[0].cell == self.pos:
            stop = self.plan.pop(0)
            if stop.kind == DROPOFF:
                del self.onboard[stop.passenger]
                self.send(stop.passenger, INFORM, {"event": "arrived", "step": self.model.steps,
                                                   "shared": stop.passenger in self.shared})
                self.shared.discard(stop.passenger)
            else:
                self.onboard[stop.passenger] = self.model.steps + self.model.boarding_time
                if len(self.onboard) > 1:
                    self.shared.update(self.onboard)
                self.boarding = stop.passenger
                self.boarding_left = self.model.boarding_time
                self.progress = 0
                if self.boarding_left == 0:
                    self.finish_boarding()

    def finish_boarding(self):
        self.send(self.boarding, INFORM, {"event": "picked_up", "step": self.model.steps})

    def count_km(self):
        self.km += 1
        if not self.onboard:
            self.km_empty += 1
