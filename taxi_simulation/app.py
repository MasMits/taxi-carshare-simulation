"""Web interface of the simulation (SolaraViz)."""

from mesa.visualization import SolaraViz, SpaceRenderer
from mesa.visualization.components import AgentPortrayalStyle, PropertyLayerStyle

from taxi_simulation.agents import Taxi
from taxi_simulation.model import CityModel

# Colors of the terrain layer: district A, district B, road.
TERRAIN_COLORS = ["#cfe3c8", "#a9cf9c", "#9e9e9e"]


def spread(agent):
    """Small fixed offset so two taxis on the same road cell stay visible."""
    return ((agent.unique_id % 3) - 1) * 0.15


def agent_portrayal(agent):
    x, y = agent.pos
    if isinstance(agent, Taxi):
        return AgentPortrayalStyle(x=x + spread(agent), y=y + spread(agent), color="gold",
                                   marker="s", size=45, zorder=3,
                                   edgecolors="black", linewidths=0.8)
    return AgentPortrayalStyle()


def propertylayer_portrayal(layer):
    """Draw the map: grey roads between green districts."""
    return PropertyLayerStyle(colormap=TERRAIN_COLORS, vmin=0, vmax=2, alpha=1.0,
                              colorbar=False)


def post_process(ax):
    ax.set_title("Taxi carshare city: taxis drive on the grey roads")
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
    "crossing_time": {"type": "SliderInt", "value": 1, "label": "Steps per road cell",
                      "min": 1, "max": 5, "step": 1},
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
