"""Taxi agent, participant of the contract net."""

from taxi_simulation.core.messages import (ACCEPT, CANCEL, CFP, CONFIRM, FAILURE, INFORM,
                                           PROPOSE, REFUSE, REJECT, MessageAgent)
from taxi_simulation.core.passenger import Passenger
from taxi_simulation.core.planning import DROPOFF, PICKUP, TaxiPlanner

# Taxi actions
BOARD = "board"
SERVE = "serve"
DRIVE = "drive"
WAIT = "wait"


class Taxi(TaxiPlanner, MessageAgent):
    """A taxi driving along the roads. Participant of the contract net.

    A taxi takes up to `capacity` passengers. For each call it looks for the
    cheapest way to insert the new pickup and drop-off into its plan, without
    making anyone's predicted ride longer than they accept. Traffic can add
    unpredicted delay after an offer is accepted.

    Beliefs:
        plan: stops still to visit, in order.
        onboard: passenger -> step when they are fully on board.
        shared: passengers who shared the taxi during their ride.
        boarding, boarding_left: passenger getting in, and steps still needed.
        progress: steps already spent on the current road cell.
        km, km_empty: road cells driven, in total and with nobody on board.
        co2: grams of CO2 emitted, by driving and by idling in traffic jams.
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
        self.co2 = 0.0
        self.heading = None
        self.in_traffic = False
        self.junction_exit = None
        self.blocked = False
        self.traffic_delay = 0
        self.queue_wait = 0
        self.offers = {}
        self.latest_round = {}
        self.contracts = {}
        self.offer_sequence = 0
        self.late_pickups = set()

    def step(self):
        self.blocked = False
        messages = self.receive()       # perceive
        action = self.decide(messages)  # deliberate
        self.act(action)                # act

    def reply(self, msg, performative, content):
        self.send(msg.sender, performative, content, msg.conversation_id)

    def refuse(self, msg, reason, performative=FAILURE):
        self.model.refusal_reasons[reason] += 1
        self.reply(msg, performative, {"reason": reason, "offer_id": msg.content.get("offer_id")})

    def notify(self, passenger, event, **content):
        contract = self.contracts.get(passenger)
        if contract is not None:
            self.send(passenger, INFORM, {"event": event, "offer_id": contract["offer_id"],
                                         **content}, contract["round_id"])

    def matches_offer(self, offer, msg):
        """A reply must belong to both the passenger and the negotiation round."""
        return (bool(offer) and offer["passenger"] is msg.sender
                and offer["round_id"] == msg.conversation_id)

    def request_score(self, trip, passenger):
        best = self.best_insertion(trip, passenger)
        if best is None:
            return float("inf")
        if self.plan:
            cost = (self.plan_distance(best[1]) - self.plan_distance(self.plan)) * self.model.taxi_steps_per_cell
        else:
            cost = best[2][0] - self.model.boarding_time
        return cost

    def decide(self, messages):
        messages = self.prepare_messages(messages)
        self.process_acceptances(messages)
        self.answer_calls(messages)
        self.count_late_pickups()

        if self.boarding_left > 0:
            return BOARD
        if self.plan and self.plan[0].cell == self.pos:
            return SERVE
        return DRIVE if self.plan else WAIT

    def prepare_messages(self, messages):
        """Discard departed passengers and apply cancellations/new rounds before acceptance."""
        self.offers = {key: value for key, value in self.offers.items()
                       if value["passenger"] in self.model.agents}
        self.latest_round = {passenger: round_id for passenger, round_id in self.latest_round.items()
                             if passenger in self.model.agents}
        # Agent addresses and conversation/offer identities are checked before any mutation.
        messages = [msg for msg in messages if isinstance(msg.sender, Passenger)
                    and msg.sender in self.model.agents and msg.conversation_id is not None]
        for msg in messages:
            if msg.performative in (REJECT, CANCEL):
                offer = self.offers.get(msg.content.get("offer_id"))
                if self.matches_offer(offer, msg):
                    del self.offers[msg.content["offer_id"]]

        for msg in messages:
            if msg.performative == CFP and msg.conversation_id > self.latest_round.get(msg.sender, 0):
                self.offers = {key: offer for key, offer in self.offers.items()
                               if offer["passenger"] is not msg.sender or offer["round_id"] >= msg.conversation_id}
        return messages

    def acceptance_priority(self, msg):
        offer = self.offers.get(msg.content.get("offer_id"))
        if not self.matches_offer(offer, msg):
            return float("inf"), msg.sender.unique_id
        return self.request_score(offer["trip"], msg.sender), msg.sender.unique_id

    def process_acceptances(self, messages):
        accepts = [msg for msg in messages if msg.performative == ACCEPT]
        # Recompute priorities after each commitment because the route has changed.
        while accepts:
            msg = min(accepts, key=self.acceptance_priority)
            accepts.remove(msg)
            self.accept_offer(msg)

    def answer_calls(self, messages):
        # Proposals do not reserve seats, so CFP order cannot improve allocation.
        # Only the newest round from each sender is eligible in this batch.
        calls = {}
        for msg in messages:
            if msg.performative == CFP:
                previous = calls.get(msg.sender)
                if previous is None or msg.conversation_id > previous.conversation_id:
                    calls[msg.sender] = msg
        for msg in sorted(calls.values(), key=lambda msg: msg.sender.unique_id):
            self.propose(msg)

    def count_late_pickups(self):
        for passenger, contract in self.contracts.items():
            if (any(stop.kind == PICKUP and stop.passenger is passenger for stop in self.plan)
                    and self.model.steps > contract["pickup_by"] and passenger not in self.late_pickups):
                self.late_pickups.add(passenger)
                self.model.pickup_violations += 1

    def accept_offer(self, msg):
        now = self.model.steps
        contract = self.contracts.get(msg.sender)
        if contract:
            if (contract["offer_id"] == msg.content.get("offer_id")
                    and contract["round_id"] == msg.conversation_id):
                self.reply(msg, CONFIRM, contract.copy())
            return  # duplicate accepts never insert a second pickup
        offer = self.offers.pop(msg.content.get("offer_id"), None)
        if not offer:
            self.refuse(msg, "unknown_offer")
            return
        if not self.matches_offer(offer, msg) or self.latest_round.get(msg.sender) != msg.conversation_id:
            # A foreign sender must not consume another passenger's offer.
            self.offers[offer["offer_id"]] = offer
            self.refuse(msg, "stale_or_foreign_offer")
            return
        trip = offer["trip"]
        best = self.best_insertion(trip, msg.sender)
        if now >= trip["search_deadline"]:
            self.refuse(msg, "search_timeout")
            return
        if best is None:
            self.refuse(msg, self.unavailable_reason("commitment_conflict"))
            return

        _, plan, (pickup_t, dropoff_t) = best
        if dropoff_t - pickup_t > offer["ride"]:
            self.refuse(msg, "changed_ride")
            return

        pickup_duration = max(0, pickup_t - self.model.boarding_time)
        pickup_by = now + pickup_duration + self.model.pickup_slack
        contract = {"offer_id": offer["offer_id"], "round_id": msg.conversation_id, "pickup_by": pickup_by}
        self.plan = plan
        self.contracts[msg.sender] = contract
        self.reply(msg, CONFIRM, contract.copy())
        self.model.confirmed_orders += 1

    def propose(self, msg):
        now = self.model.steps
        if msg.sender in self.contracts or msg.conversation_id <= self.latest_round.get(msg.sender, 0):
            return
        self.latest_round[msg.sender] = msg.conversation_id
        self.offers = {key: value for key, value in self.offers.items() if value["passenger"] is not msg.sender}
        if now >= msg.content["search_deadline"]:
            self.refuse(msg, "search_timeout", REFUSE)
            return
        best = self.best_insertion(msg.content, msg.sender)
        if best is None:
            self.refuse(msg, self.unavailable_reason("route_constraints"), REFUSE)
            return
        pickup_t, dropoff_t = best[2]
        pickup_duration = max(0, pickup_t - self.model.boarding_time)
        self.offer_sequence += 1
        offer_id = f"{self.unique_id}:{self.offer_sequence}"
        offer = {"offer_id": offer_id, "passenger": msg.sender, "round_id": msg.conversation_id,
                 "trip": dict(msg.content), "pickup_at": now + 1 + pickup_duration,
                 "pickup_eta": pickup_t, "ride": dropoff_t - pickup_t}
        self.offers[offer_id] = offer
        self.reply(msg, PROPOSE, {key: value for key, value in offer.items()
                                 if key not in ("passenger", "trip", "round_id")})

    def park(self):
        """Pull over; retain heading so restarting cannot reverse mid-block."""
        self.in_traffic = False
        self.junction_exit = None
        self.progress = 0
        self.queue_wait = 0

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
            self.progress = min(self.progress + 1, self.model.taxi_steps_per_cell)
            if self.progress >= self.model.taxi_steps_per_cell:
                nxt = self.route_to(self.plan[0].cell)[0]
                self.model.request_move(self, nxt)
        if not self.plan or self.boarding_left:
            self.park()

    def serve_stops_here(self):
        """Serve the stops on this cell in plan order.

        A drop-off is instantaneous; a pickup starts boarding, which takes
        `boarding_time` steps.
        """
        while self.boarding_left == 0 and self.plan and self.plan[0].cell == self.pos:
            stop = self.plan.pop(0)
            if stop.kind == DROPOFF:
                self.drop_off(stop.passenger)
            else:
                self.start_boarding(stop.passenger)

    def drop_off(self, passenger):
        del self.onboard[passenger]
        self.notify(passenger, "arrived", step=self.model.steps, shared=passenger in self.shared)
        self.contracts.pop(passenger, None)
        self.latest_round.pop(passenger, None)
        self.late_pickups.discard(passenger)
        self.shared.discard(passenger)

    def start_boarding(self, passenger):
        self.onboard[passenger] = self.model.steps + self.model.boarding_time
        if len(self.onboard) > 1:
            self.shared.update(self.onboard)
        self.boarding = passenger
        self.boarding_left = self.model.boarding_time
        self.notify(passenger, "boarding", step=self.model.steps)
        self.progress = 0
        if self.boarding_left == 0:
            self.finish_boarding()

    def finish_boarding(self):
        self.notify(self.boarding, "picked_up", step=self.model.steps)

    def count_km(self):
        """One road cell driven: count it and the CO2 it emits."""
        self.km += 1
        if not self.onboard:
            self.km_empty += 1
        self.co2 += self.model.cell_km * self.model.co2_per_km

    def count_idle(self):
        """One step stuck in traffic: the engine runs without moving."""
        self.co2 += self.model.idle_co2_per_step
