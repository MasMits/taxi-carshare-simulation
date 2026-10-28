"""Ring city page."""

from taxi_simulation.graph.map import GraphMap
from taxi_simulation.ring.model import RingCityModel
from taxi_simulation.ui.page import city_page, simulation_params

page = city_page(RingCityModel(seed=42), map_component=GraphMap, params={
    "arms": {"type": "Select", "value": 8, "values": [4, 6, 8, 10, 12], "label": "Radial streets"},
    **simulation_params(n_taxis=16, allow_detour=True),
})
