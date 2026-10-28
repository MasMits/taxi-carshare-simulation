"""Roads of a city: what each map must define, and the routes taxis drive on them."""

from collections import deque


class RoadMap:
    """Mixed into CityModel, which creates the route caches."""

    # --- Map: each city defines these -----------------------------------------

    def build_map(self):
        """Create self.grid (a Mesa space), self.roads (all road cells) and
        self.min_trip (trips shorter than this many road cells are walked)."""
        raise NotImplementedError

    def road_neighbours(self, cell):
        """Road cells reachable in one move."""
        raise NotImplementedError

    def is_intersection(self, cell):
        """Whether cars may turn (or reverse) on this cell."""
        raise NotImplementedError

    def direction(self, start, end):
        """Heading of a move between two neighbouring road cells."""
        raise NotImplementedError

    # --- Routes ---------------------------------------------------------------

    def distances_to(self, target):
        """Road distance from every road cell to target (breadth-first search).

        Computed once per target and cached: the map never changes.
        """
        if target not in self._distances:
            dist, queue = {target: 0}, deque([target])
            while queue:
                cell = queue.popleft()
                for nxt in self.road_neighbours(cell):
                    if nxt not in dist:
                        dist[nxt] = dist[cell] + 1
                        queue.append(nxt)
            self._distances[target] = dist
        return self._distances[target]

    def random_road_cell(self):
        """A random road cell of the city."""
        return self.random.choice(self.roads)

    def distance(self, a, b):
        """Number of road cells to drive from a to b."""
        return self.distances_to(b)[a]

    def travel_time(self, a, b):
        """Steps a taxi needs to drive from road cell a to road cell b."""
        return self.taxi_steps_per_cell * self.distance(a, b)

    def next_cell(self, pos, target, heading=None):
        """Continue in-lane, or choose a shortest route at a junction."""
        if self.traffic and heading is not None and not self.is_intersection(pos):
            return next(cell for cell in self.road_neighbours(pos)
                        if self.direction(pos, cell) == heading)
        dist = self.distances_to(target)
        return min(self.road_neighbours(pos), key=lambda cell: dist[cell])

    def route(self, start, target, heading=None):
        """Follow the current lane to a junction before turning or reversing."""
        key = (start, target, heading if self.traffic else None)
        if key not in self._routes:
            cells, cell = [], start
            while cell != target:
                nxt = self.next_cell(cell, target, heading)
                heading = self.direction(cell, nxt)
                cells.append(nxt)
                cell = nxt
            self._routes[key] = tuple(cells)
        return self._routes[key]

    def pickup_route(self, start, pickup, onward, heading=None):
        """Reach a pickup facing a shortest onward leg; turn while still empty.

        Search cell/heading states, since passing a pickup in the wrong lane is
        not a service stop. Reverse distances are shared by all starts and all
        destinations requiring the same arrival direction at this pickup.
        """
        route = self.route(start, pickup, heading)
        if not self.traffic or onward == pickup or self.is_intersection(pickup):
            return route
        distance = self.distances_to(onward)
        arrivals = frozenset(self.direction(pickup, nxt) for nxt in self.road_neighbours(pickup)
                             if distance[nxt] == distance[pickup] - 1)
        arrival = self.direction(route[-2] if len(route) > 1 else start, route[-1]) if route else heading
        if arrival is None or arrival in arrivals:
            return route
        key = (pickup, arrivals)
        if key not in self._pickup_distances:
            distances = {(pickup, direction): 0 for direction in arrivals}
            queue = deque(distances)
            while queue:
                cell, direction = queue.popleft()
                for previous in self.road_neighbours(cell):
                    if self.direction(previous, cell) != direction:
                        continue
                    headings = ({self.direction(neighbour, previous)
                                 for neighbour in self.road_neighbours(previous)}
                                if self.is_intersection(previous) else (direction,))
                    for previous_heading in headings:
                        state = (previous, previous_heading)
                        if state not in distances:
                            distances[state] = distances[cell, direction] + 1
                            queue.append(state)
            self._pickup_distances[key] = distances
        route_key = (start, pickup, arrivals, heading)
        if route_key not in self._pickup_routes:
            distances = self._pickup_distances[key]
            state, cells, states = (start, heading), [], []
            while state[0] != pickup or state[1] not in arrivals:
                cell, direction = state
                neighbours = [(nxt, self.direction(cell, nxt)) for nxt in self.road_neighbours(cell)
                              if direction is None or self.is_intersection(cell)
                              or self.direction(cell, nxt) == direction]
                state = min(neighbours, key=lambda nxt: distances[nxt])
                cells.append(state[0])
                states.append(state)
            cells = tuple(cells)
            for index, state in enumerate([(start, heading)] + states):
                self._pickup_routes[state[0], pickup, arrivals, state[1]] = cells[index:]
        return self._pickup_routes[route_key]
