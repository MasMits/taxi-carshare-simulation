"""Shared map, controls and charts for both graph-city demos."""

from html import escape
from math import atan2, degrees

import mesa.visualization.solara_viz as solara_viz
import solara
from mesa.visualization import SolaraViz, make_plot_component
from mesa.visualization.utils import update_counter

from .agents import DROPOFF, WAITING
from .stats_view import PollutionStats


def svg(tag, content="", **attributes):
    """A small SVG element; callers supply markup as content and plain attributes."""
    attrs = " ".join(f'{key.replace("_", "-")}="{escape(str(value), quote=True)}"'
                     for key, value in attributes.items())
    return f"<{tag} {attrs}>{content}</{tag}>"


def render_map(model):
    def points(nodes):
        return " ".join(f"{model.coordinates[n][0]:.3f},{-model.coordinates[n][1]:.3f}" for n in nodes)

    def position(node, heading, offset):
        x, y = model.coordinates[node]
        dx, dy = model.lane_vector(node, heading)
        return x + dy * offset, -y + dx * offset, degrees(atan2(-dy, dx))

    parts = []
    for section in model.sections:
        parts.append(svg("polyline", points=points(section), stroke="#69717b", stroke_width=.95))
        parts.append(svg("polyline", points=points(section), stroke="#edf0f3",
                         stroke_width=.04, stroke_dasharray=".2 .22"))
    for node in model.junctions:
        x, y = model.coordinates[node]
        parts.append(svg("circle", cx=x, cy=-y, r=.14, fill="#edf0f3"))
    for taxi in model.taxis():
        if not taxi.onboard:
            continue
        last = max(i for i, s in enumerate(taxi.plan) if s.kind == DROPOFF and s.passenger in taxi.onboard)
        route, cell, heading = [taxi.pos], taxi.pos, taxi.heading
        for i, stop in enumerate(taxi.plan[:last + 1]):
            leg = taxi.route_to(stop.cell, cell, heading, first=i == 0)
            if leg:
                heading = model.direction(leg[-2] if len(leg) > 1 else cell, leg[-1])
            route.extend(leg)
            cell = stop.cell
            if stop.kind == DROPOFF and stop.passenger in taxi.onboard:
                x, y = model.coordinates[cell]
                parts.append(svg("path", d=f"M{x-.2},{-y-.2}l.4,.4m-.4,0l.4,-.4",
                                 stroke="#bd4c28", stroke_width=.13))
        parts.append(svg("polyline", points=points(route), stroke="#bd4c28",
                         stroke_width=.11, stroke_dasharray=".27 .2"))
    for passenger in model.passengers():
        if passenger.pos is None:
            continue
        heading = model.direction(passenger.pos, next(model.road_neighbours(passenger.pos)))
        x, y, _ = position(passenger.pos, heading, .65 + .15 * (passenger.unique_id % 3))
        parts.append(svg("circle", svg("title", f"Passenger {passenger.unique_id}: {passenger.state}"),
                         cx=x, cy=y, r=.17, fill="#1465ce" if passenger.state == WAITING else "#098756",
                         stroke="white", stroke_width=.05))
    for taxi in model.taxis():
        x, y, angle = position(taxi.pos, taxi.heading, .22 if taxi.in_traffic else .65)
        shape = svg("path", d="M.38,0 L-.28,-.25 L-.28,.25 Z") if taxi.in_traffic else (
            svg("rect", x=-.23, y=-.23, width=.46, height=.46))
        title = svg("title", f"Taxi {taxi.unique_id}: {len(taxi.onboard)} on board, "
                    f"{taxi.traffic_delay} blocked steps" + ("" if taxi.in_traffic else " (at curb)"))
        parts.append(svg("g", title + shape, transform=f"translate({x},{y}) rotate({angle if taxi.in_traffic else 0})",
                         fill="#f08c28" if taxi.onboard else "#f4ca33",
                         stroke="#d81bce" if taxi.blocked else "#353535",
                         stroke_width=.14 if taxi.blocked else .06))
        if taxi.onboard:  # badge with the number of passengers inside
            parts.append(svg("circle", cx=x + .5, cy=y - .5, r=.38, fill="white",
                             stroke="#353535", stroke_width=.06))
            parts.append(svg("text", str(len(taxi.onboard)), x=x + .5, y=y - .35,
                             text_anchor="middle", font_size=.46, font_weight="bold",
                             fill="#202020", stroke="none"))
    for x, y, text in model.map_labels:
        parts.append(svg("text", escape(text), x=x, y=-y, text_anchor="middle", font_size=.65, fill="#354335"))
    return svg("svg", svg("title", escape(model.map_title)) + "".join(parts),
               xmlns="http://www.w3.org/2000/svg", viewBox="-18.5 -18.5 37 37", fill="none",
               stroke_linecap="round", stroke_linejoin="round", role="img", aria_label=model.map_title,
               style="display:block;width:100%;height:auto;background:#e7f0e2;border-radius:8px")


@solara.component
def GraphMap(model):
    update_counter.get()
    solara.Markdown(f"**Step {model.steps}** · Waiting: **{model.count('waiting', 'assigned')}** · "
                    f"Served: **{len(model.trips)}** · Cancelled: **{model.gave_up}** · "
                    f"Blocked taxis: **{sum(t.blocked for t in model.taxis())}**")
    solara.HTML(tag="div", unsafe_innerHTML=render_map(model))
    solara.Markdown("Yellow: empty · Orange: busy · (n): passengers inside · Magenta border: blocked  \n"
                    "Blue / green dots: passengers · Dashed line: ride route · ×: drop-off  \n"
                    "Two directional lanes per road; squares wait at the curb.")


def slider(label, value, minimum, maximum, step=1):
    return {"type": "SliderFloat" if isinstance(value, float) else "SliderInt",
            "label": label, "value": value, "min": minimum, "max": maximum, "step": step}


def graph_page(model_class, name, map_params):
    """Only the map controls differ between the two launch modules."""
    def layout(count):
        """Page 0: map and statistics side by side. Page 1: the charts, two per row."""
        if count == 2:
            return [{"i": 0, "w": 7, "h": 17, "moved": False, "x": 0, "y": 0},
                    {"i": 1, "w": 5, "h": 11, "moved": False, "x": 7, "y": 0}]
        return [{"i": i, "w": 6, "h": 10, "moved": False, "x": 6 * (i % 2), "y": 10 * (i // 2)}
                for i in range(count)]

    solara_viz.make_initial_grid_layout = layout
    params = {**map_params, "n_taxis": slider("Taxis", 16, 2, 40),
              "capacity": slider("Seats per taxi", 2, 1, 4),
              "allow_detour": {"type": "Checkbox", "value": True, "label": "Allow detours for sharing"},
              "demand": slider("New passengers per step", .3, .1, 2., .1),
              "taxi_steps_per_cell": slider("Steps per road slot", 1, 1, 5),
              "max_wait": slider("Max wait (steps)", 60, 10, 180, 10),
              "traffic": {"type": "Checkbox", "value": True, "label": "Traffic: lanes and queues"},
              "stop_at": slider("Stop at step (0 = never)", 1000, 0, 3000, 100), "seed": 42}
    return SolaraViz(model_class(seed=42), model_params=params, name=name, play_interval=200,
                     components=[GraphMap, PollutionStats,
                                 make_plot_component({"CO2 per passenger (g)": "tab:brown"}, page=1),
                                 make_plot_component({"Waiting": "tab:blue", "Riding": "tab:green",
                                                      "Blocked taxis": "magenta"}, page=1),
                                 make_plot_component({"Served": "tab:green", "Gave up": "tab:red"},
                                                     page=1)])
