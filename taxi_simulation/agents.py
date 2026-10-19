"""Passenger and taxi state machines using Mesa agents."""

from collections import deque

import mesa

from .messages import Message


class PassengerAgent(mesa.Agent):
    role = "Passenger"

    def __init__(self, model, destination):
        super().__init__(model)
        self.destination, self.state = destination, "ready"
        self.inbox, self.trip_route = [], ()
        self.pickup_tick = self.arrival_tick = None

    def step(self):
        if self.state == "ready":
            self.trip_route = tuple(self.model.city.find_path(self.pos, self.destination))
            self.model.send(Message("CFP", self, self.model.taxi, self.trip_route))
            self.state = "requesting"
        messages, self.inbox = self.inbox, []
        for message in messages:
            if message.kind == "PROPOSE" and self.state == "requesting":
                self.model.send(Message("ACCEPT", self, message.sender, self.trip_route))
                self.state = "waiting"
            elif message.kind == "BOARD" and self.state == "waiting":
                if self.pos != message.sender.pos:
                    raise RuntimeError("Taxi must be at the pickup before boarding")
                self.state, self.pickup_tick = "riding", self.model.ticks
                self.model.send(Message("BOARDED", self, message.sender))
            elif message.kind == "ARRIVED" and self.state == "riding":
                if self.pos != self.destination:
                    raise RuntimeError("Passenger has not reached the destination")
                self.state, self.arrival_tick = "arrived", self.model.ticks


class TaxiAgent(mesa.Agent):
    role = "Taxi"

    def __init__(self, model):
        super().__init__(model)
        self.state, self.passenger = "idle", None
        self.inbox, self.path = [], deque()
        self.trip_route = self.pickup_route = ()
        self.distance = 0

    def step(self):
        messages, self.inbox = self.inbox, []
        for message in messages:
            if message.kind == "CFP" and self.state == "idle":
                self.passenger, self.trip_route = message.sender, message.route
                self.pickup_route = tuple(self.model.city.find_path(self.pos, message.route[0]))
                self.model.send(Message("PROPOSE", self, self.passenger, eta=len(self.pickup_route) - 1))
                self.state = "offered"
                return
            if message.kind == "ACCEPT" and self.state == "offered":
                self.path, self.state = deque(self.pickup_route[1:]), "to_pickup"
                return
            if message.kind == "BOARDED" and self.state == "awaiting_boarding":
                self.path, self.state = deque(self.trip_route[1:]), "transporting"
                return
        if self.state in ("to_pickup", "transporting"):
            if self.path:
                self.model.grid.move_agent(self, self.path.popleft())
                self.distance += 1
                if self.state == "transporting":
                    self.model.grid.move_agent(self.passenger, self.pos)
            if not self.path:
                self.state = "boarding" if self.state == "to_pickup" else "dropping_off"
        elif self.state in ("boarding", "dropping_off"):
            kind, self.state = (
                ("BOARD", "awaiting_boarding") if self.state == "boarding" else ("ARRIVED", "done")
            )
            self.model.send(Message(kind, self, self.passenger))
