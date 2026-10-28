"""Grid city: square districts separated by one-cell roads.

Every row and column whose index is a multiple of (district_size + 1) is a road.

Quick check:  python -m taxi_simulation.grid.model
"""

from mesa.space import MultiGrid, PropertyLayer

from taxi_simulation.core.model import CityModel

# Values of the "terrain" layer, used to draw the map.
DISTRICT_A = 0  # districts are painted as a checkerboard of A and B
DISTRICT_B = 1
ROAD = 2


class GridCityModel(CityModel):
    """A city of size x size square districts on a Mesa MultiGrid.

    Args:
        size: the city is size x size districts.
        district_size: side of one district, in cells.
        **kwargs: simulation parameters, see CityModel.
    """

    def __init__(self, size=6, district_size=3, seed=None, **kwargs):
        self.size = size
        self.district_size = district_size
        super().__init__(seed=seed, **kwargs)

    def build_map(self):
        self.block = self.district_size + 1
        self.min_trip = self.block
        width = self.size * self.block + 1
        self.terrain = PropertyLayer("terrain", width, width, ROAD, dtype=int)
        self.grid = MultiGrid(width, width, torus=False, property_layers=[self.terrain])
        self.roads = []
        for x in range(width):
            for y in range(width):
                district = self.district_at((x, y))
                if district is None:
                    self.roads.append((x, y))
                else:
                    col, row = district % self.size, district // self.size
                    self.terrain.set_cell(
                        (x, y), DISTRICT_A if (col + row) % 2 == 0 else DISTRICT_B
                    )
        self.is_road = set(self.roads)

    def district_at(self, cell):
        """District id of a cell, or None if the cell is a road."""
        x, y = cell
        if x % self.block == 0 or y % self.block == 0:
            return None
        return (y // self.block) * self.size + x // self.block

    def road_neighbours(self, cell):
        """Road cells reachable in one move (no diagonals)."""
        x, y = cell
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nxt in self.is_road:
                yield nxt

    def is_intersection(self, cell):
        return cell[0] % self.block == 0 and cell[1] % self.block == 0

    @staticmethod
    def direction(start, end):
        return (end[0] - start[0], end[1] - start[1])


if __name__ == "__main__":
    model = GridCityModel(seed=1)
    print(f"city: {model.size} x {model.size} districts, grid {model.grid.width} x "
          f"{model.grid.height} cells, {len(model.taxis())} taxis")
    for _ in range(200):
        model.step()
    data = model.datacollector.get_model_vars_dataframe().iloc[-1]
    print(f"after {model.steps} steps: {model.spawned} passengers, {int(data['Served'])} served")
    print(f"avg wait {data['Avg wait']:.1f} steps, avg ride {data['Avg ride']:.1f} steps, "
          f"avg detour {data['Avg detour']:.2f}, km per passenger {data['Km per passenger']:.1f}")
    print(f"CO2: {data['CO2 (kg)']:.1f} kg in total, {data['CO2 per passenger (g)']:.0f} g per passenger")
