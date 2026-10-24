"""Web interface of the simulation (SolaraViz)."""

import matplotlib.pyplot as plt
import mesa.visualization.solara_viz as solara_viz
from mesa.visualization import SolaraViz, SpaceRenderer, make_plot_component
from mesa.visualization.components import AgentPortrayalStyle, PropertyLayerStyle

from taxi_simulation.agents import DROPOFF, WAITING, Taxi
from taxi_simulation.model import CityModel

# Colors of the terrain layer: district A, district B, road.
TERRAIN_COLORS = ["#cfe3c8", "#a9cf9c", "#9e9e9e"]
# One color per taxi for the route of its passengers.
ROUTE_COLORS = plt.get_cmap("tab10").colors


def big_layout(num_components):
    """Bigger panels than Mesa's default (half width, 10 rows high), so the map is readable."""
    return [{"i": i, "w": 7 if i == 0 else 5, "h": 16 if i == 0 else 8,
             "moved": False, "x": 0 if i == 0 else 7, "y": 0 if i == 0 else 8 * (i - 1)}
            for i in range(num_components)]


solara_viz.make_initial_grid_layout = big_layout


def spread(agent):
    """Small fixed offset so agents on the same road cell stay visible."""
    return ((agent.unique_id % 3) - 1) * 0.15


def agent_portrayal(agent):
    # Every agent must set edgecolors and linewidths, otherwise Mesa's
    # matplotlib renderer fails when taxis and passengers are drawn together.
    x, y = agent.pos
    if isinstance(agent, Taxi):
        # yellow = free, orange = one passenger, red = shared
        color = {0: "gold", 1: "tab:orange"}.get(len(agent.onboard), "tab:red")
        dx, dy = taxi_offset(agent)
        marker = {(1, 0): ">", (-1, 0): "<", (0, 1): "^", (0, -1): "v"}.get(agent.heading, "s")
        return AgentPortrayalStyle(x=x + dx, y=y + dy, color=color,
                                   marker=marker if agent.in_traffic else "s", size=80, zorder=3,
                                   edgecolors="magenta" if agent.blocked else "black",
                                   linewidths=2 if agent.blocked else 0.8)
    # blue = calling a taxi, green = a taxi is coming
    return AgentPortrayalStyle(x=x + spread(agent), y=y - spread(agent),
                               color="tab:blue" if agent.state == WAITING else "tab:green",
                               marker="o", size=45, zorder=2,
                               edgecolors="white", linewidths=0.5)


def taxi_offset(taxi):
    """Right-hand lanes; parked cars sit at the curb."""
    if taxi.heading is None:
        return spread(taxi), 0.35
    dx, dy = taxi.heading
    offset = 0.18 if taxi.in_traffic else 0.38
    return dy * offset, -dx * offset


def draw_rides(ax, grid):
    """Route of every taxi that carries passengers.

    The line follows the roads from the taxi, through the stops of its plan,
    to the last place where one of its passengers gets off (X).
    """
    for taxi in grid.agents:
        if not isinstance(taxi, Taxi) or not taxi.onboard:
            continue
        last = max(i for i, stop in enumerate(taxi.plan)
                   if stop.kind == DROPOFF and stop.passenger in taxi.onboard)
        stops = taxi.plan[:last + 1]
        route, cell, heading = [taxi.pos], taxi.pos, taxi.heading
        for i, stop in enumerate(stops):
            leg = taxi.route_to(stop.cell, cell, heading, first=i == 0)
            if leg:
                heading = taxi.model.direction(leg[-2] if len(leg) > 1 else cell, leg[-1])
            route.extend(leg)
            cell = stop.cell

        color = ROUTE_COLORS[taxi.unique_id % len(ROUTE_COLORS)]
        dx, dy = taxi_offset(taxi)
        xs, ys = zip(*route)
        ax.plot([x + dx for x in xs], [y + dy for y in ys], color=color,
                linewidth=2.5, linestyle="--", alpha=0.9, zorder=2.5)
        for stop in stops:
            if stop.kind == DROPOFF and stop.passenger in taxi.onboard:
                ax.plot(stop.cell[0] + dx, stop.cell[1] + dy, marker="X", markersize=11,
                        color=color, markeredgecolor="black", markeredgewidth=0.6, zorder=2.6)


def propertylayer_portrayal(layer):
    """Draw the map: grey roads between green districts."""
    return PropertyLayerStyle(colormap=TERRAIN_COLORS, vmin=0, vmax=2, alpha=1.0,
                              colorbar=False)


def post_process(ax):
    fig = ax.get_figure()
    fig.set_size_inches(8, 8.4)
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.9)
    ax.set_title("Taxis: yellow = free, orange = 1 passenger, red = shared\n"
                 "Passengers: blue = calling a taxi, green = taxi coming\n"
                 "Arrows: direction; magenta border: blocked; squares: at curb\n"
                 "Line: route, X = drop-off", fontsize=10)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


model_params = {
    "size": {"type": "SliderInt", "value": 6, "label": "Districts per side",
             "min": 3, "max": 10, "step": 1},
    "district_size": {"type": "SliderInt", "value": 3, "label": "District size (cells)",
                      "min": 2, "max": 6, "step": 1},
    "n_taxis": {"type": "SliderInt", "value": 10, "label": "Taxis",
                "min": 1, "max": 40, "step": 1},
    "capacity": {"type": "SliderInt", "value": 2, "label": "Seats per taxi (1 = no sharing)",
                 "min": 1, "max": 2, "step": 1},
    "allow_detour": {"type": "Checkbox", "value": False,
                     "label": "Taxis may change their route to pick someone up"},
    "demand": {"type": "SliderFloat", "value": 0.3, "label": "New passengers per step",
               "min": 0.1, "max": 2.0, "step": 0.1},
    "taxi_steps_per_cell": {"type": "SliderInt", "value": 1,
                            "label": "Taxi: steps per cell",
                            "min": 1, "max": 5, "step": 1},
    "boarding_time": {"type": "SliderInt", "value": 1, "label": "Pickup time (steps)",
                      "min": 0, "max": 3, "step": 1},
    "max_wait": {"type": "SliderInt", "value": 60, "label": "Maximum wait before cancellation (steps)",
                 "min": 10, "max": 180, "step": 10},
    "traffic": {"type": "Checkbox", "value": True, "label": "Traffic: lanes and queues"},
    "seed": 42,  # fixed: Reset replays the same run
}

class CityRenderer(SpaceRenderer):
    """Mesa's renderer, plus the routes of the taxis carrying passengers.

    Mesa redraws the agents at every step, and rebuilds the renderer with the
    same class on Reset, so the routes are drawn right after the agents.
    """

    def draw_agents(self, *args, **kwargs):
        result = super().draw_agents(*args, **kwargs)
        draw_rides(self.canvas, self.space)
        return result


model = CityModel(seed=42)
renderer = (
    CityRenderer(model, backend="matplotlib")
    .setup_propertylayer(propertylayer_portrayal)
    .setup_agents(agent_portrayal)
)
renderer.post_process = post_process
renderer.render()

page = SolaraViz(
    model,
    renderer,
    components=[make_plot_component({"Waiting": "tab:blue", "Riding": "tab:green",
                                     "Blocked taxis": "magenta"}),
                make_plot_component({"Served": "tab:green", "Gave up": "tab:red"})],
    model_params=model_params,
    name="Taxi carshare simulation",
    play_interval=200,
)
