"""Square roads and breadth-first shortest paths."""

from collections import deque

Cell = tuple[int, int]


class CityMap:
    def __init__(self, street_count=4, block_spacing=4):
        if street_count < 2 or block_spacing < 2:
            raise ValueError("Use at least two streets, separated by at least two cells")
        self.streets = tuple(1 + i * block_spacing for i in range(street_count))
        self.size = self.streets[-1] + 2
        self.road_cells = {
            (x, y)
            for x in range(1, self.size - 1)
            for y in range(1, self.size - 1)
            if x in self.streets or y in self.streets
        }

    def find_path(self, start: Cell, goal: Cell) -> list[Cell]:
        if start not in self.road_cells or goal not in self.road_cells:
            raise ValueError("Path endpoints must be on roads")
        queue, visited = deque([[start]]), {start}
        while queue:
            path = queue.popleft()
            x, y = path[-1]
            if (x, y) == goal:
                return path
            for cell in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
                if cell in self.road_cells and cell not in visited:
                    visited.add(cell)
                    queue.append(path + [cell])
        raise ValueError("No road connects these locations")
