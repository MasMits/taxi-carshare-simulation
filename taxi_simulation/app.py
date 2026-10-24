"""Web interface of the simulation (SolaraViz)."""

from mesa.visualization import SolaraViz, SpaceRenderer
from mesa.visualization.components import AgentPortrayalStyle, PropertyLayerStyle

from taxi_simulation.agents import WAITING, Taxi
from taxi_simulation.model import CityModel

# Colors of the terrain layer: district A, district B, road.
TERRAIN_COLORS = ["#cfe3c8", "#a9cf9c", "#9e9e9e"]


def spread(agent):
    """Small fixed offset so agents on the same road cell stay visible."""
    return ((agent.unique_id % 3) - 1) * 0.15


def agent_portrayal(agent):
    # Every agent must set edgecolors and linewidths, otherwise Mesa's
    # matplotlib renderer fails when taxis and passengers are drawn together.
    x, y = agent.pos
    if isinstance(agent, Taxi):
        # yellow = free, orange = carrying a passenger
        return AgentPortrayalStyle(x=x + spread(agent), y=y + spread(agent),
                                   color="tab:orange" if agent.onboard else "gold",
                                   marker="s", size=45, zorder=3,
                                   edgecolors="black", linewidths=0.8)
    # blue = calling a taxi, green = a taxi is coming
    return AgentPortrayalStyle(x=x + spread(agent), y=y - spread(agent),
                               color="tab:blue" if agent.state == WAITING else "tab:green",
                               marker="o", size=25, zorder=2,
                               edgecolors="white", linewidths=0.5)


def propertylayer_portrayal(layer):
    """Draw the map: grey roads between green districts."""
    return PropertyLayerStyle(colormap=TERRAIN_COLORS, vmin=0, vmax=2, alpha=1.0,
                              colorbar=False)


def post_process(ax):
    ax.set_title("Taxis: yellow = free, orange = busy.  Passengers: blue = calling, green = taxi coming")
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
    "demand": {"type": "SliderFloat", "value": 0.6, "label": "New passengers per step",
               "min": 0.1, "max": 2.0, "step": 0.1},
    "taxi_steps_per_cell": {"type": "SliderInt", "value": 1,
                            "label": "Taxi speed: steps per road cell (1 = fastest)",
                            "min": 1, "max": 5, "step": 1},
    "boarding_time": {"type": "SliderInt", "value": 1, "label": "Time for a passenger to get in (steps)",
                      "min": 0, "max": 3, "step": 1},
    "seed": 42,  # fixed: Reset replays the same run
}

model = CityModel(seed=42)
renderer = (
    SpaceRenderer(model, backend="matplotlib")
    .setup_propertylayer(propertylayer_portrayal)
    .setup_agents(agent_portrayal)
)
renderer.post_process = post_process
renderer.render()

page = SolaraViz(
    model,
    renderer,
    components=[],
    model_params=model_params,
    name="Taxi carshare simulation",
    play_interval=200,
)
