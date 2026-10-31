"""Planning of a taxi: routes to its stops, and where a new trip fits in its plan."""

from dataclasses import dataclass

from taxi_simulation.core.passenger import Passenger

# Kinds of stop in a taxi plan
PICKUP = "pickup"
DROPOFF = "dropoff"


@dataclass
class Stop:
    """One stop of a taxi plan."""

    cell: tuple[int, int]
    kind: str               # PICKUP or DROPOFF
    passenger: Passenger    # address for messages, its attributes are never read
    max_ride: float         # passenger tolerance, received in the call for proposals


class TaxiPlanner:
    """Mixed into Taxi, which holds the plan, the passengers on board and the contracts."""

    def route_to(self, target, cell=None, heading=None, first=True):
        """Include any exit already reserved while traversing a junction."""
        cell = self.pos if cell is None else cell
        heading = self.heading if heading is None and first else heading
        if first and self.junction_exit is not None:
            exit_cell = self.junction_exit
            direction = self.model.direction(cell, exit_cell)
            return (exit_cell,) + self.route_to(target, exit_cell, direction, first=False)
        return self.model.route(cell, target, heading)

    def booked(self):
        """Passengers on board or waiting for this taxi."""
        return len(self.onboard) + sum(stop.kind == PICKUP for stop in self.plan)

    def has_pending_pickup(self):
        """Whether any confirmed passenger is still waiting for pickup."""
        return any(stop.kind == PICKUP for stop in self.plan)

    def unavailable_reason(self, fallback):
        if self.booked() >= self.model.capacity:
            return "capacity"
        if self.has_pending_pickup() and not self.model.allow_multiple_pickups:
            return "pickup_in_progress"
        return fallback

    def legs(self, plan):
        """Drive through a plan from here: yield each stop and the road cells leading to it."""
        cell, heading = self.pos, self.heading
        for i, stop in enumerate(plan):
            route = self.route_to(stop.cell, cell, heading, first=i == 0)
            if route:
                heading = self.model.direction(route[-2] if len(route) > 1 else cell, route[-1])
            cell = stop.cell
            yield stop, route

    def plan_distance(self, plan):
        """Road cells to drive to visit all the stops of a plan."""
        return sum(len(route) for _, route in self.legs(plan))

    def ride_route(self):
        """Road cells until the last passenger on board gets off, and their drop-off cells.

        Used to draw the ride on the map.
        """
        dropoffs = [i for i, stop in enumerate(self.plan)
                    if stop.kind == DROPOFF and stop.passenger in self.onboard]
        if not dropoffs:
            return [], []
        route = [self.pos]
        for _, leg in self.legs(self.plan[:dropoffs[-1] + 1]):
            route.extend(leg)
        return route, [self.plan[i].cell for i in dropoffs]

    def evaluate(self, plan):
        """Simulate a plan from the current road cell.

        Returns (finish_time, times) with times[p] = (pickup_t, dropoff_t)
        relative to now, or None if someone's ride would exceed their max_ride.
        """
        m = self.model
        t = self.boarding_left
        picked = {p: step - m.steps for p, step in self.onboard.items()}  # already (getting) in
        times = {}
        for stop, route in self.legs(plan):
            t += m.taxi_steps_per_cell * len(route)
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

        A new pickup is always the next stop and can precede pending pickups.
        Disabling multiple pickups allows only one pending pickup at a time.
        Existing stops keep their order and commitments remain feasible.
        Without detours the current route cannot lengthen.
        Returns (finish_time, plan, (pickup_t, dropoff_t)) or None.
        """
        if self.booked() >= self.model.capacity:
            return None
        if self.has_pending_pickup() and not self.model.allow_multiple_pickups:
            return None
        pickup = Stop(trip["pickup"], PICKUP, passenger, trip["max_ride"])
        dropoff = Stop(trip["dropoff"], DROPOFF, passenger, trip["max_ride"])
        old_distance = self.plan_distance(self.plan)
        best = None
        for j in range(len(self.plan) + 1):
            plan = [pickup] + self.plan[:j] + [dropoff] + self.plan[j:]
            if (self.plan and not self.model.allow_detour
                    and self.plan_distance(plan) > old_distance):
                continue
            result = self.evaluate(plan)
            if result is None:
                continue
            if best is None or result[0] < best[0]:
                best = (result[0], plan, result[1][passenger])
        return best
