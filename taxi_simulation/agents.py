"""Agents of the taxi carshare simulation: passengers and taxis.

Every agent follows the procedural loop perceive -> decide -> act and does at
most one physical action per step. Agents never read each other's attributes:
they only exchange messages (contract net protocol).
"""

from dataclasses import dataclass

from .messages import ACCEPT, CANCEL, CFP, CONFIRM, FAILURE, INFORM, PROPOSE, REFUSE, REJECT, MessageAgent

# Passenger states
WAITING = "waiting"
CONFIRMING = "confirming"
ASSIGNED = "assigned"
RIDING = "riding"
BOARDING = "boarding"
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

    def request_score(self, trip, passenger):
        best = self.best_insertion(trip, passenger)
        if best is None:
            return float("inf")
        if self.plan:
            cost = (self.plan_distance(best[1]) - self.plan_distance(self.plan)) * self.model.taxi_steps_per_cell
        else:
            cost = best[2][0] - self.model.boarding_time
        age = self.model.steps - trip.get("request_step", self.model.steps)
        return cost - self.model.wait_priority * age

    def decide(self, messages):
        now = self.model.steps
        self.offers = {key: value for key, value in self.offers.items()
                       if value["expires_at"] >= now and value["passenger"] in self.model.agents}
        self.latest_round = {passenger: round_id for passenger, round_id in self.latest_round.items()
                             if passenger in self.model.agents}
        # Agent addresses and conversation/offer identities are checked before any mutation.
        messages = [msg for msg in messages if isinstance(msg.sender, Passenger)
                    and msg.sender in self.model.agents and msg.conversation_id is not None]
        for msg in messages:
            if msg.performative in (REJECT, CANCEL):
                offer = self.offers.get(msg.content.get("offer_id"))
                if offer and offer["passenger"] is msg.sender and offer["round_id"] == msg.conversation_id:
                    del self.offers[msg.content["offer_id"]]

        for msg in messages:
            if msg.performative == CFP and msg.conversation_id > self.latest_round.get(msg.sender, 0):
                self.offers = {key: offer for key, offer in self.offers.items()
                               if offer["passenger"] is not msg.sender or offer["round_id"] >= msg.conversation_id}

        accepts = [msg for msg in messages if msg.performative == ACCEPT]

        def score(msg):
            offer = self.offers.get(msg.content.get("offer_id"))
            valid = offer and offer["passenger"] is msg.sender and offer["round_id"] == msg.conversation_id
            return (self.request_score(offer["trip"], msg.sender) if valid else float("inf"),
                    offer["trip"].get("request_step", now) if valid else now, msg.sender.unique_id)

        # Recompute priorities after each commitment because the route has changed.
        while accepts:
            msg = min(accepts, key=score)
            accepts.remove(msg)
            self.accept_offer(msg)

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

        for passenger, contract in self.contracts.items():
            if (any(stop.kind == PICKUP and stop.passenger is passenger for stop in self.plan)
                    and now > contract["pickup_by"] and passenger not in self.late_pickups):
                self.late_pickups.add(passenger)
                self.model.pickup_violations += 1
        if self.boarding_left > 0:
            return BOARD
        if self.plan and self.plan[0].cell == self.pos and not self.route_to_stop(self.plan, 0):
            return SERVE
        return DRIVE if self.plan else WAIT

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
            self.refuse(msg, "expired_or_unknown_offer")
            return
        if (offer["passenger"] is not msg.sender or offer["round_id"] != msg.conversation_id
                or self.latest_round.get(msg.sender) != msg.conversation_id):
            # A foreign sender must not consume another passenger's offer.
            self.offers[offer["offer_id"]] = offer
            self.refuse(msg, "stale_or_foreign_offer")
            return
        trip = dict(offer["trip"], pickup_by=offer["pickup_by"])
        best = self.best_insertion(trip, msg.sender)
        if now >= trip["search_deadline"]:
            self.refuse(msg, "search_timeout")
        elif best is None:
            self.refuse(msg, self.unavailable_reason("commitment_conflict"))
        elif best[2][1] - best[2][0] > offer["ride"]:
            self.refuse(msg, "changed_ride")
        else:
            pickup_by = min(offer["pickup_by"], now + max(0, best[2][0] - self.model.boarding_time)
                            + self.model.pickup_slack)
            self.plan = best[1]
            self.contracts[msg.sender] = {"offer_id": offer["offer_id"],
                                          "round_id": msg.conversation_id, "pickup_by": pickup_by}
            self.reply(msg, CONFIRM, self.contracts[msg.sender].copy())
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
        # Search expiry governs acceptance, not the future time of boarding.
        pickup_by = now + self.model.offer_ttl + pickup_duration
        self.offer_sequence += 1
        offer_id = f"{self.unique_id}:{self.offer_sequence}"
        offer = {"offer_id": offer_id, "passenger": msg.sender, "round_id": msg.conversation_id,
                 "trip": dict(msg.content), "expires_at": min(now + self.model.offer_ttl,
                                                             msg.content["search_deadline"] - 1),
                 "pickup_by": pickup_by, "pickup_at": now + 1 + pickup_duration,
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

    def route_to(self, target, cell=None, heading=None, first=True, pickup_next=None):
        """Include any exit already reserved while traversing a junction."""
        cell = self.pos if cell is None else cell
        heading = self.heading if heading is None and first else heading
        if first and self.junction_exit is not None:
            exit_cell = self.junction_exit
            direction = self.model.direction(cell, exit_cell)
            return (exit_cell,) + self.route_to(target, exit_cell, direction, first=False,
                                                pickup_next=pickup_next)
        if pickup_next is not None:
            return self.model.pickup_route(cell, target, pickup_next, heading)
        return self.model.route(cell, target, heading)

    def route_to_stop(self, plan, index, cell=None, heading=None, first=True):
        """Share the same pickup approach between planning, driving and drawing."""
        stop = plan[index]
        onward = plan[index + 1].cell if stop.kind == PICKUP and index + 1 < len(plan) else None
        return self.route_to(stop.cell, cell, heading, first=first, pickup_next=onward)

    # --- Planning ---------------------------------------------------------------

    def booked(self):
        """Passengers on board or waiting for this taxi."""
        return len(self.onboard) + sum(stop.kind == PICKUP for stop in self.plan)

    def has_pending_pickup(self):
        """A confirmed next pickup cannot be displaced by another booking."""
        return any(stop.kind == PICKUP for stop in self.plan)

    def unavailable_reason(self, fallback):
        if self.booked() >= self.model.capacity:
            return "capacity"
        if self.has_pending_pickup():
            return "pickup_in_progress"
        return fallback

    def plan_distance(self, plan):
        """Road cells to drive to visit all the stops of a plan."""
        distance, cell, heading = 0, self.pos, self.heading
        for i, stop in enumerate(plan):
            route = self.route_to_stop(plan, i, cell, heading, first=i == 0)
            if route:
                heading = self.model.direction(route[-2] if len(route) > 1 else cell, route[-1])
            distance += len(route)
            cell = stop.cell
        return distance

    def evaluate(self, plan):
        """Simulate a plan from the current road cell.

        Returns (finish_time, times) with times[p] = (pickup_t, dropoff_t)
        relative to now, or None if someone's ride would exceed their max_ride.
        """
        m = self.model
        t, cell = self.boarding_left, self.pos
        picked = {p: step - m.steps for p, step in self.onboard.items()}  # already (getting) in
        times = {}
        heading = self.heading
        for i, stop in enumerate(plan):
            route = self.route_to_stop(plan, i, cell, heading, first=i == 0)
            t += m.taxi_steps_per_cell * len(route)
            if route:
                heading = m.direction(route[-2] if len(route) > 1 else cell, route[-1])
            cell = stop.cell
            if stop.kind == PICKUP:
                contract = self.contracts.get(stop.passenger)
                if contract and m.steps + t > contract["pickup_by"]:
                    return None
                t += m.boarding_time  # everyone inside waits while a new passenger gets in
                picked[stop.passenger] = t
            elif t - picked[stop.passenger] > stop.max_ride:
                return None  # too long a ride for this passenger
            else:
                times[stop.passenger] = (picked[stop.passenger], t)
        return t, times

    def best_insertion(self, trip, passenger):
        """Cheapest feasible plan that also serves the new trip.

        A new pickup must be the next stop, with no earlier pickup still
        pending. Existing drop-offs keep their order; the new drop-off may
        follow any of them. Without detours the current route cannot lengthen.
        Returns (finish_time, plan, (pickup_t, dropoff_t)) or None.
        """
        if self.booked() >= self.model.capacity or self.has_pending_pickup():
            return None
        pickup = Stop(trip["pickup"], PICKUP, passenger, trip["max_ride"])
        dropoff = Stop(trip["dropoff"], DROPOFF, passenger, trip["max_ride"])
        old_distance = self.plan_distance(self.plan)
        best = None
        for j in range(len(self.plan) + 1):
            plan = [pickup] + self.plan[:j] + [dropoff] + self.plan[j:]
            if (self.plan and not self.model.allow_detour
                    and self.plan_distance(plan) > old_distance):
                continue  # the current route may not change
            result = self.evaluate(plan)
            if result is None:
                continue
            pickup_t, _ = result[1][passenger]
            deadline = trip.get("pickup_by", float("inf"))
            if self.model.steps + max(0, pickup_t - self.model.boarding_time) > deadline:
                continue
            if best is None or result[0] < best[0]:
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
            self.progress = min(self.progress + 1, self.model.taxi_steps_per_cell)
            if self.progress >= self.model.taxi_steps_per_cell:
                nxt = self.route_to_stop(self.plan, 0)[0]
                self.model.request_move(self, nxt)
        if not self.plan or self.boarding_left:
            self.park()

    def serve_stops_here(self):
        """Serve the stops on this cell in plan order.

        A drop-off is instantaneous; a pickup starts boarding, which takes
        `boarding_time` steps.
        """
        while self.boarding_left == 0 and self.plan and self.plan[0].cell == self.pos:
            if self.route_to_stop(self.plan, 0):
                break  # pass the passenger until returning in the correct lane
            stop = self.plan.pop(0)
            if stop.kind == DROPOFF:
                del self.onboard[stop.passenger]
                self.notify(stop.passenger, "arrived", step=self.model.steps,
                            shared=stop.passenger in self.shared)
                self.contracts.pop(stop.passenger, None)
                self.latest_round.pop(stop.passenger, None)
                self.late_pickups.discard(stop.passenger)
                self.shared.discard(stop.passenger)
            else:
                self.onboard[stop.passenger] = self.model.steps + self.model.boarding_time
                if len(self.onboard) > 1:
                    self.shared.update(self.onboard)
                self.boarding = stop.passenger
                self.boarding_left = self.model.boarding_time
                self.notify(stop.passenger, "boarding", step=self.model.steps)
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
