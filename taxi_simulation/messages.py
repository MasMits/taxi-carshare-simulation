"""Direct communication between agents (FIPA-ACL style).

Mesa has no message passing, so the model (the environment) carries messages
from the sender to the receiver's mailbox.
"""

from dataclasses import dataclass, field

import mesa

# Performatives of the contract net protocol
CFP = "cfp"
PROPOSE = "propose"
REFUSE = "refuse"
ACCEPT = "accept-proposal"
REJECT = "reject-proposal"
FAILURE = "failure"
INFORM = "inform"
CANCEL = "cancel"


@dataclass
class Message:
    performative: str
    sender: mesa.Agent
    receiver: mesa.Agent
    content: dict = field(default_factory=dict)
    conversation_id: int | None = None


class MessageAgent(mesa.Agent):
    """An agent with a mailbox. It never touches another agent directly."""

    def __init__(self, model):
        super().__init__(model)
        self.inbox = []

    def send(self, receiver, performative, content=None, conversation_id=None):
        self.model.deliver(Message(performative, self, receiver, content or {}, conversation_id))

    def receive(self):
        """Return the received messages and empty the mailbox."""
        messages, self.inbox = self.inbox, []
        return messages
