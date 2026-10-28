"""Grid city page, drawn with Mesa's matplotlib SpaceRenderer."""

from mesa.visualization import SpaceRenderer
from mesa.visualization.components import AgentPortrayalStyle, PropertyLayerStyle

from taxi_simulation.core.taxi import Taxi
from taxi_simulation.grid.model import GridCityModel
from taxi_simulation.ui.drawing import (draw_badge, draw_ride, finish_map, passenger_color,
                                        taxi_border, taxi_color)
from taxi_simulation.ui.page import city_page, simulation_params, slider

# Colors of the terrain layer: district A, district B, road.
TERRAIN_COLORS = ["#cfe3c8", "#a9cf9c", "#9e9e9e"]
ARROWS = {(1, 0): ">", (-1, 0): "<", (0, 1): "^", (0, -1): "v"}


def spread(agent):
    """Small fixed offset so agents on the same road cell stay visible."""
    return ((agent.unique_id % 3) - 1) * 0.15


def taxi_offset(taxi):
    """Right-hand lanes; parked cars sit at the curb."""
    if taxi.heading is None:
        return spread(taxi), 0.35
    dx, dy = taxi.heading
    offset = 0.18 if taxi.in_traffic else 0.38
    return dy * offset, -dx * offset


def agent_portrayal(agent):
    # Every agent must set edgecolors and linewidths, otherwise Mesa's
    # matplotlib renderer fails when taxis and passengers are drawn together.
    x, y = agent.pos
    if isinstance(agent, Taxi):
        dx, dy = taxi_offset(agent)
        border, width = taxi_border(agent)
        marker = ARROWS.get(agent.heading, "s") if agent.in_traffic else "s"
        return AgentPortrayalStyle(x=x + dx, y=y + dy, color=taxi_color(agent), marker=marker,
                                   size=80, zorder=3, edgecolors=border, linewidths=width)
    return AgentPortrayalStyle(x=x + spread(agent), y=y - spread(agent), color=passenger_color(agent),
                               marker="o", size=45, zorder=2, edgecolors="white", linewidths=0.5)


def propertylayer_portrayal(layer):
    """Draw the map: grey roads between green districts."""
    return PropertyLayerStyle(colormap=TERRAIN_COLORS, vmin=0, vmax=2, alpha=1.0, colorbar=False)


class GridRenderer(SpaceRenderer):
    """Mesa's renderer, plus the rides and passenger counts of busy taxis.

    Mesa redraws the agents at every step, and rebuilds the renderer with the
    same class on Reset, so the extras are drawn right after the agents.
    """

    def draw_agents(self, *args, **kwargs):
        result = super().draw_agents(*args, **kwargs)
        ax = self.canvas
        for text in list(ax.texts):  # Mesa clears the markers at each step, not the texts
            text.remove()
        for taxi in self.space.agents:
            if isinstance(taxi, Taxi) and taxi.onboard:
                dx, dy = taxi_offset(taxi)
                draw_ride(ax, taxi, lambda cell: (cell[0] + dx, cell[1] + dy))
                draw_badge(ax, taxi.pos[0] + dx + 0.45, taxi.pos[1] + dy + 0.45, len(taxi.onboard))
        return result


model = GridCityModel(seed=42)
renderer = (GridRenderer(model, backend="matplotlib")
            .setup_propertylayer(propertylayer_portrayal)
            .setup_agents(agent_portrayal))
renderer.post_process = finish_map
renderer.render()

page = city_page(model, renderer=renderer, params={
    "size": slider("Districts per side", 6, 3, 10),
    "district_size": slider("District size (cells)", 3, 2, 6),
    **simulation_params(n_taxis=10, allow_detour=False),
})
