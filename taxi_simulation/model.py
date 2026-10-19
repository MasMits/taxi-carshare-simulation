"""Mesa grid, agents and next-tick message delivery."""

import mesa
from mesa.space import MultiGrid

from .agents import PassengerAgent, TaxiAgent
from .city import CityMap


class TaxiModel(mesa.Model):
    def __init__(
        self, street_count=4, block_spacing=4, taxi_start=None, passenger_start=None, destination=None
    ):
        super().__init__()
        self.config = dict(
            street_count=street_count,
            block_spacing=block_spacing,
            taxi_start=taxi_start,
            passenger_start=passenger_start,
            destination=destination,
        )
        self.city = CityMap(street_count, block_spacing)
        self.grid = MultiGrid(self.city.size, self.city.size, torus=False)
        streets = self.city.streets
        taxi_start = taxi_start or (streets[0], streets[0])
        passenger_start = passenger_start or (streets[1], streets[-2])
        destination = destination or (streets[-1], streets[-1])
        for point in (taxi_start, passenger_start, destination):
            if point not in self.city.road_cells:
                raise ValueError(f"Position {point} must be a road cell")
        self.ticks = 0
        self.events, self.messages, self.pending = [], [], []
        self.taxi, self.passenger = TaxiAgent(self), PassengerAgent(self, destination)
        self.grid.place_agent(self.taxi, taxi_start)
        self.grid.place_agent(self.passenger, passenger_start)
        self.log("One passenger and one taxi are ready. No trip requested yet.")

    def log(self, text):
        self.events.append((self.ticks, text))

    def send(self, message):
        self.pending.append(message)
        self.messages.append(message)
        self.log(f"{message.sender.role} → {message.recipient.role}: {message.describe()}")

    def step(self):
        if not self.running:
            return
        self.ticks += 1
        pending, self.pending = self.pending, []
        for message in pending:
            message.recipient.inbox.append(message)
        self.passenger.step()
        self.taxi.step()
        if self.passenger.state == "arrived" and self.taxi.state == "done":
            self.running = False
            self.log("Trip complete. Both agents remain on the map.")
