"""Traffic: simultaneous moves, separate lanes, reserved junction exits."""


class Traffic:
    """Mixed into CityModel."""

    def lane_key(self, cell, heading):
        """One slot per direction on roads; a junction is a shared conflict zone."""
        return (cell, None if self.is_intersection(cell) else heading)

    def request_move(self, taxi, destination):
        self._move_requests[taxi] = destination

    def resolve_traffic(self):
        """Use a single occupancy snapshot: no passing through a car that moves later.

        Junctions admit one car only when its exit lane is clear. That exit is
        reserved until the car leaves, preventing cars from blocking the box.
        Longest-waiting cars get priority; stable IDs break ties reproducibly.
        Idle taxis and taxis boarding passengers wait at the curb, off the lane.
        """
        occupied = {self.lane_key(t.pos, t.heading): t for t in self.taxis() if t.in_traffic}
        reserved = {self.lane_key(t.junction_exit, self.direction(t.pos, t.junction_exit)): t
                    for t in self.taxis() if t.junction_exit is not None}
        claimed = set()
        order = sorted(self._move_requests, key=lambda t: (-t.queue_wait, t.unique_id))
        for taxi in order:
            nxt = self._move_requests[taxi]
            heading = self.direction(taxi.pos, nxt)
            key = self.lane_key(nxt, heading)
            exit_cell = None
            keys = [key]
            if not taxi.in_traffic:
                keys.append(self.lane_key(taxi.pos, heading))
            if self.is_intersection(nxt) and nxt != taxi.plan[0].cell:
                exit_cell = taxi.route_to(taxi.plan[0].cell, cell=nxt, heading=heading, first=False)[0]
                keys.append(self.lane_key(exit_cell, self.direction(nxt, exit_cell)))
            blocked = any(
                (k in occupied and occupied[k] is not taxi)
                or (k in reserved and reserved[k] is not taxi) or k in claimed
                for k in keys
            )
            if blocked:
                taxi.blocked = True
                taxi.traffic_delay += 1
                taxi.queue_wait += 1
                taxi.count_idle()
                continue
            claimed.update(keys)
            self.grid.move_agent(taxi, nxt)
            taxi.heading = heading
            taxi.junction_exit = exit_cell
            taxi.in_traffic = True
            taxi.progress = 0
            taxi.queue_wait = 0
            taxi.count_km()
            taxi.serve_stops_here()
            if not taxi.plan or taxi.boarding_left:
                taxi.park()
        self._move_requests.clear()
