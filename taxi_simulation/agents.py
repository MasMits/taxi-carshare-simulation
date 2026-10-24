"""Agents of the taxi carshare simulation.

Every agent follows the procedural loop perceive -> decide -> act and does at
most one physical action per step.
"""

import mesa

# Taxi actions
PICK_TARGET = "pick target"
DRIVE = "drive"


class Taxi(mesa.Agent):
    """A taxi driving along the roads.

    When the taxi has no target, or has reached it, it picks a random road cell
    and drives there.

    Beliefs:
        target: road cell the taxi is driving to (None = no target).
        progress: steps already spent on the current road cell.
        km: road cells driven so far.
    """

    def __init__(self, model):
        super().__init__(model)
        self.target = None
        self.progress = 0
        self.km = 0

    def step(self):
        action = self.decide()  # 1. perceive (own position) + 2. deliberate
        self.act(action)        # 3. act

    def decide(self):
        """Choose one action for this step."""
        if self.target is None or self.target == self.pos:
            return PICK_TARGET
        return DRIVE

    def act(self, action):
        if action == PICK_TARGET:
            self.target = self.model.random_road_cell()
        elif action == DRIVE:
            # Driving along a road cell takes `crossing_time` steps,
            # then the taxi moves to the next one.
            self.progress += 1
            if self.progress >= self.model.crossing_time:
                self.progress = 0
                next_cell = self.model.next_cell(self.pos, self.target)
                self.model.grid.move_agent(self, next_cell)
                self.km += 1
