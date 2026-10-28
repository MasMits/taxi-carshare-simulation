"""Web interface of the simulation: one tab per city map."""

import solara

from taxi_simulation.grid.page import page as grid_page
from taxi_simulation.irregular.page import page as irregular_page
from taxi_simulation.ring.page import page as ring_page


@solara.component
def Layout(children=[]):
    """One tab per city map in the top bar."""
    current, _ = solara.use_route()
    with solara.AppLayout() as main:
        with solara.AppBar():
            with solara.lab.Tabs(align="center", color="white"):
                for route in routes:
                    solara.lab.Tab(route.label, path_or_route=route)
        # a new key per city: Solara builds a fresh page instead of reusing the previous one
        solara.Div(children=children).key(f"city {current.path}")
    return main


routes = [
    solara.Route("/", component=grid_page, label="Grid city", layout=Layout),
    solara.Route("ring", component=ring_page, label="Ring city"),
    solara.Route("irregular", component=irregular_page, label="Irregular city"),
]
