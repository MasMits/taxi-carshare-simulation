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
