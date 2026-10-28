"""Map of a road-graph city (ring or irregular), drawn with matplotlib."""

import math

import solara
from matplotlib.figure import Figure
from mesa.visualization.utils import update_counter

from taxi_simulation.ui.drawing import (draw_badge, draw_ride, finish_map, passenger_color,
                                        taxi_border, taxi_color)

ROAD_COLOR = "#69717b"
LANE_MARKING = "#edf0f3"
BACKGROUND = "#e7f0e2"
VIEW = 18.5  # the map spans -VIEW..VIEW on both axes


def road_direction(model, node, heading):
    """Unit vector of the road at node in the driving direction (east if unknown)."""
    for neighbour in model.network[node]:
        if model.direction(node, neighbour) == heading:
            a, b = model.coordinates[node], model.coordinates[neighbour]
            break
        if model.direction(neighbour, node) == heading:
            a, b = model.coordinates[neighbour], model.coordinates[node]
            break
    else:
        return 1.0, 0.0
    length = math.dist(a, b)
    return (b[0] - a[0]) / length, (b[1] - a[1]) / length


def lane_position(model, node, heading, offset):
    """Point `offset` to the right of the road centre, and the driving angle in degrees."""
    x, y = model.coordinates[node]
    dx, dy = road_direction(model, node, heading)
    return x + dy * offset, y - dx * offset, math.degrees(math.atan2(dy, dx))


def draw_city(ax, model):
    for section in model.sections:
        xs, ys = zip(*(model.coordinates[node] for node in section))
        ax.plot(xs, ys, color=ROAD_COLOR, linewidth=13, solid_capstyle="round", zorder=1)
        ax.plot(xs, ys, color=LANE_MARKING, linewidth=0.6, dashes=(3, 3), zorder=1.1)
    for x, y, text in model.map_labels:
        ax.text(x, y, text, ha="center", fontsize=9, color="#354335")

    for taxi in model.taxis():
        if taxi.onboard:
            draw_ride(ax, taxi, lambda node: model.coordinates[node])

    for passenger in model.passengers():
        if passenger.pos is None:  # in a taxi
            continue
        heading = model.direction(passenger.pos, next(model.road_neighbours(passenger.pos)))
        x, y, _ = lane_position(model, passenger.pos, heading, 0.65 + 0.15 * (passenger.unique_id % 3))
        ax.scatter(x, y, s=45, color=passenger_color(passenger),
                   edgecolors="white", linewidths=0.5, zorder=2)

    for taxi in model.taxis():
        x, y, angle = lane_position(model, taxi.pos, taxi.heading, 0.22 if taxi.in_traffic else 0.65)
        marker = (3, 0, angle - 90) if taxi.in_traffic else "s"  # triangle pointing where it drives
        border, width = taxi_border(taxi)
        ax.scatter(x, y, s=80, marker=marker, color=taxi_color(taxi),
                   edgecolors=border, linewidths=width, zorder=3)
        if taxi.onboard:
            draw_badge(ax, x + 0.6, y + 0.6, len(taxi.onboard))


@solara.component
def GraphMap(model):
    update_counter.get()  # redraw at every step
    fig = Figure()
    ax = fig.subplots()
    draw_city(ax, model)
    ax.set_xlim(-VIEW, VIEW)
    ax.set_ylim(-VIEW, VIEW)
    ax.set_facecolor(BACKGROUND)
    finish_map(ax)
    solara.FigureMatplotlib(fig, format="png")
