"""Run: solara run taxi_simulation.ring_app --port 8766."""

from .graph_view import graph_page
from .ring_model import RingCityModel

page = graph_page(RingCityModel, "Ring city: graph simulation", {
    "arms": {"type": "Select", "value": 8, "values": [4, 6, 8, 10, 12], "label": "Radial streets"},
})
