"""Passenger agent, initiator of the contract net.

Every agent follows the procedural loop perceive -> decide -> act and does at
most one physical action per step. Agents never read each other's attributes:
they only exchange messages (contract net protocol).
"""

from taxi_simulation.core.messages import (ACCEPT, CANCEL, CFP, CONFIRM, FAILURE, INFORM,
                                           PROPOSE, REJECT, MessageAgent)

# Passenger states
WAITING = "waiting"
CONFIRMING = "confirming"
ASSIGNED = "assigned"
RIDING = "riding"
BOARDING = "boarding"
ARRIVED = "arrived"


class Passenger(MessageAgent):
    """A person who needs a ride. Initiator of the contract net.

    Beliefs:
        origin, destination: road cells of the trip.
        request_step: step when the passenger appeared.
        direct_time: duration of the ride without any detour.
        max_ride: longest ride the passenger accepts.
        state: WAITING, CONFIRMING, ASSIGNED, BOARDING, RIDING or ARRIVED.
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
        self.assigned_taxi = None
        self.round_id = 0
        self.offers = {}
        self.pending_offer = None
        self.promised_pickup = None
        self.searches = 0
        self.attempts_in_round = 0
        self.attempted_offers = set()

    def trip(self):
        """Only communicated facts are available to a taxi."""
        return {"pickup": self.origin, "dropoff": self.destination, "max_ride": self.max_ride,
                "request_step": self.request_step,
                "search_deadline": self.request_step + self.model.max_wait}

    def step(self):
        proposals = self.perceive()
        action, offer = self.decide(proposals)
        self.act(action, offer, proposals)

    def perceive(self):
        for msg in self.receive():
            if msg.conversation_id != self.round_id:
                continue
            if msg.sender not in self.model.taxi_directory():
                continue
            offer_id = msg.content.get("offer_id")
            if msg.performative == PROPOSE and self.state == WAITING:
                if (offer_id not in self.attempted_offers
                        and msg.content.get("expires_at", -1) >= self.model.steps):
                    self.offers[offer_id] = msg
                continue
            if (msg.sender is not self.assigned_taxi or self.pending_offer is None
                    or offer_id != self.pending_offer.content["offer_id"]):
                continue
            if msg.performative == CONFIRM and self.state == CONFIRMING:
                self.state = ASSIGNED
                self.promised_pickup = msg.content["pickup_by"]
                self.release_offers()
            elif msg.performative == FAILURE and self.state == CONFIRMING:
                self.state = WAITING
                self.assigned_taxi = None
                self.pending_offer = None
            elif msg.performative == INFORM:
                event = msg.content.get("event")
                if event == "boarding" and self.state == ASSIGNED:
                    self.state = BOARDING
                elif event == "picked_up" and self.state == BOARDING:
                    self.state = RIDING
                    self.pickup_step = msg.content["step"]
                elif event == "arrived" and self.state == RIDING:
                    self.state = ARRIVED
                    self.arrival_step = msg.content["step"]
                    self.shared = msg.content["shared"]
        self.offers = {key: offer for key, offer in self.offers.items()
                       if offer.content["expires_at"] >= self.model.steps}
        return list(self.offers.values())

    def decide(self, proposals):
        if self.state == ARRIVED:
            return "leave", None
        if self.state in (RIDING, BOARDING):
            return ("get in", None) if self.pos is not None else ("wait", None)
        # A confirmed commitment survives the passenger's search timeout.
        if self.state == ASSIGNED:
            return "wait", None
        if self.model.steps - self.request_step >= self.model.max_wait:
            return "cancel", None
        if self.state == CONFIRMING:
            return "wait", None
        acceptable = [offer for offer in proposals if offer.content["ride"] <= self.max_ride]
        if acceptable:
            best = min(acceptable, key=lambda offer: (
                max(self.model.steps, offer.content["pickup_at"]) + offer.content["ride"],
                offer.sender.unique_id))
            return "accept", best
        return "call", None

    def release_offers(self):
        for offer in self.offers.values():
            self.send(offer.sender, REJECT, {"offer_id": offer.content["offer_id"]}, self.round_id)
        self.offers.clear()

    def act(self, action, offer, proposals):
        if action == "accept":
            if self.attempts_in_round:
                self.model.alternative_attempts += 1
            self.attempts_in_round += 1
            self.attempted_offers.add(offer.content["offer_id"])
            self.offers.pop(offer.content["offer_id"], None)
            self.send(offer.sender, ACCEPT, {"offer_id": offer.content["offer_id"]}, self.round_id)
            self.state = CONFIRMING
            self.assigned_taxi = offer.sender
            self.pending_offer = offer
        elif action == "cancel":
            if self.pending_offer is not None:
                self.send(self.assigned_taxi, CANCEL,
                          {"offer_id": self.pending_offer.content["offer_id"]}, self.round_id)
            self.release_offers()
            self.model.gave_up += 1
            self.model.refusal_reasons["search_timeout"] += 1
            self.remove()
        elif action == "call":
            self.release_offers()
            self.round_id += 1
            self.attempts_in_round = 0
            self.attempted_offers.clear()
            if self.searches:
                self.model.repeat_searches += 1
            self.searches += 1
            for taxi in self.model.taxi_directory():
                self.send(taxi, CFP, self.trip(), self.round_id)
        elif action == "get in":
            self.model.grid.remove_agent(self)
        elif action == "leave":
            self.model.record_trip(wait=self.pickup_step - self.request_step,
                                   ride=self.arrival_step - self.pickup_step,
                                   direct_time=self.direct_time, shared=self.shared)
            self.remove()

    def remove(self):
        """Leave the grid too: Agent.remove() does not do it for a MultiGrid."""
        if self.pos is not None:
            self.model.grid.remove_agent(self)
        super().remove()
