"""What every city page shares: simulation controls, charts and page layout."""

import mesa.visualization.solara_viz as solara_viz
import solara
from mesa.visualization import SolaraViz, make_plot_component

from taxi_simulation.ui.stats import PollutionStats

CHARTS = [  # on the second tab, "Graphs"
    make_plot_component({"CO2 per passenger (g)": "tab:brown"}, page=1),
    make_plot_component({"Waiting": "tab:blue", "Riding": "tab:green", "Blocked taxis": "magenta"},
                        page=1),
    make_plot_component({"Served": "tab:green", "Gave up": "tab:red"}, page=1),
]


def slider(label, value, minimum, maximum, step=1):
    return {"type": "SliderFloat" if isinstance(value, float) else "SliderInt",
            "label": label, "value": value, "min": minimum, "max": maximum, "step": step}


def checkbox(label, value):
    return {"type": "Checkbox", "label": label, "value": value}


def simulation_params(n_taxis, allow_detour):
    """Controls of the simulation itself, the same for every map."""
    return {
        "n_taxis": slider("Taxis", n_taxis, 1, 40),
        "capacity": slider("Seats per taxi (1 = no sharing)", 2, 1, 4),
        "allow_detour": checkbox("Taxis may change their route to pick someone up", allow_detour),
        "demand": slider("New passengers per step", 0.3, 0.1, 2.0, 0.1),
        "max_wait": slider("Search timeout (steps)", 60, 10, 180, 10),
        "stop_at": slider("Stop at step (0 = never)", 1000, 0, 3000, 100),
        "seed": 42,  # fixed: Reset replays the same run, with the same passengers
    }


def city_page(model, params, renderer=None, map_component=None):
    """A SolaraViz page: map and statistics on the first tab, charts on the second.

    The map is either a Mesa renderer or a component of our own.
    """
    components = [PollutionStats, *CHARTS]
    if map_component is not None:
        components.insert(0, map_component)
    return SolaraViz(model, renderer, components=components, model_params=params,
                     name="Taxi carshare simulation", play_interval=200)


# --- Two tweaks of Mesa's SolaraViz, which has no option for them ------------

def layout(count):
    """Page 0: map and statistics side by side. Page 1: the charts, two per row."""
    if count == 2:
        return [{"i": 0, "w": 7, "h": 17, "moved": False, "x": 0, "y": 0},
                {"i": 1, "w": 5, "h": 18, "moved": False, "x": 7, "y": 0}]
    return [{"i": i, "w": 6, "h": 10, "moved": False, "x": 6 * (i % 2), "y": 10 * (i // 2)}
            for i in range(count)]


solara_viz.make_initial_grid_layout = layout

# Readable names for Mesa's "Page 0", "Page 1" tabs.
PAGE_NAMES = {"Page 0": "Simulation", "Page 1": "Graphs"}
_tab = solara.v.Tab


def named_tab(**kwargs):
    kwargs["children"] = [PAGE_NAMES.get(c, c) for c in kwargs.get("children", [])]
    return _tab(**kwargs)


solara.v.Tab = named_tab
