"""Web interface of the simulation: one tab per city map."""

import solara

from taxi_simulation import grid_app, irregular_app, ring_app


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
    solara.Route("/", component=grid_app.page, label="Grid city", layout=Layout),
    solara.Route("ring", component=ring_app.page, label="Ring city"),
    solara.Route("irregular", component=irregular_app.page, label="Irregular city"),
]
