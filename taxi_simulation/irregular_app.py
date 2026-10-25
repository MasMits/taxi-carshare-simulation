"""Run: solara run taxi_simulation.irregular_app --port 8767."""

from .graph_view import graph_page, slider
from .irregular_model import IrregularCityModel

page = graph_page(IrregularCityModel, "Irregular city: graph simulation", {
    "map_seed": slider("City layout seed", 7, 1, 50),
    "junction_count": slider("Junctions", 28, 12, 40),
    "extra_roads": slider("Additional road probability", .65, 0., 1., .05),
})
