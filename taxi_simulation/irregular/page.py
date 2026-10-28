"""Irregular city page."""

from taxi_simulation.graph.map import GraphMap
from taxi_simulation.irregular.model import IrregularCityModel
from taxi_simulation.ui.page import city_page, simulation_params, slider

page = city_page(IrregularCityModel(seed=42), map_component=GraphMap, params={
    "map_seed": slider("City layout seed", 7, 1, 50),
    "junction_count": slider("Junctions", 28, 12, 40),
    "extra_roads": slider("Additional road probability", 0.65, 0.0, 1.0, 0.05),
    **simulation_params(n_taxis=16, allow_detour=True),
})
