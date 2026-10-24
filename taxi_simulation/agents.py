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

    A taxi carries one passenger at a time: it only makes offers while it is free.

    Beliefs:
        plan: stops still to visit, in order.
        onboard: passenger -> step when they are fully on board.
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

    def is_free(self):
        return not self.plan and not self.onboard

    def step(self):
        messages = self.receive()       # perceive
        action = self.decide(messages)  # deliberate
        self.act(action)                # act

    def decide(self, messages):
        # Accepts first: they change the plan the next answers depend on.
        for msg in sorted(messages, key=lambda m: m.performative != ACCEPT):
            if msg.performative == ACCEPT:
                if self.is_free():
                    trip = msg.content
                    self.plan = [Stop(trip["pickup"], PICKUP, msg.sender, trip["max_ride"]),
                                 Stop(trip["dropoff"], DROPOFF, msg.sender, trip["max_ride"])]
                else:
                    self.send(msg.sender, FAILURE)
            elif msg.performative == CFP:
                if self.is_free():
                    trip = msg.content
                    self.send(msg.sender, PROPOSE, {
                        "pickup_eta": self.model.travel_time(self.pos, trip["pickup"])
                                      + self.model.boarding_time,
                        "ride": self.model.travel_time(trip["pickup"], trip["dropoff"]),
                    })
                else:
                    self.send(msg.sender, REFUSE)
            # REJECT: nothing to undo, taxis keep no reservation

        if self.boarding_left > 0:
            return BOARD
        if self.plan and self.plan[0].cell == self.pos:
            return SERVE
        return DRIVE if self.plan else WAIT

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
