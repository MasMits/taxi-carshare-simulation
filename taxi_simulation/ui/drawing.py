"""Colours and drawing helpers shared by every city map (matplotlib)."""

from matplotlib import colormaps

from taxi_simulation.core.passenger import CONFIRMING, WAITING

LEGEND = ("Taxis: yellow = free, orange = assigned/busy, (n) = passengers inside\n"
          "Passengers: blue = searching, purple = confirming, green = taxi coming\n"
          "Arrows: direction; magenta border: blocked; squares: at curb\n"
          "Line: route, X = drop-off")
ROUTE_COLORS = colormaps["tab10"].colors  # one colour per taxi


def taxi_color(taxi):
    """Yellow = available, orange = assigned or carrying passengers."""
    return "tab:orange" if taxi.plan or taxi.onboard else "gold"


def taxi_border(taxi):
    """(colour, width) of the taxi's border: magenta when blocked in traffic."""
    return ("magenta", 2) if taxi.blocked else ("black", 0.8)


def passenger_color(passenger):
    """Blue = searching, purple = waiting for a confirmation, green = a taxi is coming."""
    return {WAITING: "tab:blue", CONFIRMING: "tab:purple"}.get(passenger.state, "tab:green")


def draw_ride(ax, taxi, xy):
    """Dashed route of a taxi carrying passengers, X at each drop-off.

    xy(cell) gives the map coordinates of a road cell.
    """
    route, dropoffs = taxi.ride_route()
    if not route:
        return
    color = ROUTE_COLORS[taxi.unique_id % len(ROUTE_COLORS)]
    xs, ys = zip(*map(xy, route))
    ax.plot(xs, ys, color=color, linewidth=2.5, linestyle="--", alpha=0.9, zorder=2.5)
    for cell in dropoffs:
        x, y = xy(cell)
        ax.plot(x, y, marker="X", markersize=11, color=color,
                markeredgecolor="black", markeredgewidth=0.6, zorder=2.6)


def draw_badge(ax, x, y, count):
    """White circle with the number of passengers inside a taxi."""
    ax.text(x, y, str(count), ha="center", va="center", fontsize=9, fontweight="bold", zorder=4,
            bbox={"boxstyle": "circle,pad=0.2", "facecolor": "white",
                  "edgecolor": "black", "linewidth": 0.6})


def finish_map(ax):
    """Same frame for every map: legend as title, equal axes, no ticks."""
    fig = ax.get_figure()
    fig.set_size_inches(8, 8.4)
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.9)
    ax.set_title(LEGEND, fontsize=10)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
