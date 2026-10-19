"""Direct agent messages for requesting and completing a trip."""

from dataclasses import dataclass

from mesa import Agent

from .city import Cell


@dataclass(frozen=True)
class Message:
    kind: str
    sender: Agent
    recipient: Agent
    route: tuple[Cell, ...] = ()
    eta: int | None = None

    def describe(self) -> str:
        if self.kind == "CFP":
            return f"Pick me up at {self.route[0]} and take me to {self.route[-1]}."
        if self.kind == "PROPOSE":
            return f"I can pick you up in {self.eta} road moves."
        return {
            "ACCEPT": "Accepted. I will wait here.",
            "BOARD": "I am here. Please board.",
            "BOARDED": "I am in the taxi. Ready to go.",
            "ARRIVED": "We have reached your destination.",
        }[self.kind]
