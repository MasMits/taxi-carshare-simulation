"""Static map drawing, separate from the simulation and playback controls."""

from matplotlib.colors import ListedColormap


def draw_map(ax, model):
    city = model.city
    roads = [[(x, y) in city.road_cells for x in range(city.size)] for y in range(city.size)]
    ax.imshow(roads, origin="lower", cmap=ListedColormap(["#edf2e9", "#cbd2da"]))
    ax.set(
        xticks=city.streets,
        yticks=city.streets,
        xticklabels=[f"Ave {i + 1}" for i in range(len(city.streets))],
        yticklabels=[f"St {i + 1}" for i in range(len(city.streets))],
    )
    boundaries = [i - 0.5 for i in range(city.size + 1)]
    ax.set_xticks(boundaries, minor=True)
    ax.set_yticks(boundaries, minor=True)
    ax.grid(which="minor", color="white")
    ax.tick_params(which="minor", length=0)
    (pickup_line,) = ax.plot([], [], "--", color="orange", label="Pickup route")
    (trip_line,) = ax.plot([], [], "--", color="seagreen", label="Trip route")
    ax.scatter(*model.passenger.destination, marker="*", c="purple", s=180, label="Destination")
    taxi_marker = ax.scatter(*model.taxi.pos, marker="s", c="gold", s=200, label="Taxi")
    person_marker = ax.scatter(*model.passenger.pos, c="royalblue", s=60, label="Passenger")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=5, fontsize=8)
    return pickup_line, trip_line, taxi_marker, person_marker
