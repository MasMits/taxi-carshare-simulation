"""Summary panel to compare runs with 1 to 4 seats per taxi.

Run the simulation with the same seed until it stops, once per number of seats,
and compare the panels: every run gets the same passengers.
"""

import solara
from mesa.visualization.utils import update_counter

# Readable names for Mesa's "Page 0", "Page 1" tabs.
PAGE_NAMES = {"Page 0": "Simulation", "Page 1": "Graphs"}
_tab = solara.v.Tab


def named_tab(**kwargs):
    kwargs["children"] = [PAGE_NAMES.get(c, c) for c in kwargs.get("children", [])]
    return _tab(**kwargs)


solara.v.Tab = named_tab


def PollutionStats(model):
    update_counter.get()
    served = len(model.trips)
    taxis = model.taxis()
    co2_per_passenger = model.co2() / max(1, served)
    km_per_passenger = model.driven_km() / max(1, served)
    empty_km = 100 * sum(t.km_empty for t in taxis) / max(1, model.vehicle_km())
    seats = f"{model.capacity} seat{'s' if model.capacity > 1 else ''} per taxi"
    progress = f"step {model.steps} / {model.stop_at}" if model.stop_at else f"step {model.steps}"
    if not model.running:
        progress += " (finished)"

    solara.Markdown(f"""
### {seats} · {progress}
{len(taxis)} taxis · {model.demand} new passengers per step · detours {'on' if model.allow_detour else 'off'}

## CO₂ per passenger: {co2_per_passenger:,.0f} g

| | |
|---|---|
| CO₂ emitted by all taxis | {model.co2() / 1000:.1f} kg |
| Taxi km per passenger | {km_per_passenger:.1f} km |
| Km driven empty | {empty_km:.0f} % |
| Passengers served | {served} of {model.spawned} |
| Rides shared with someone | {100 * model.average('shared'):.0f} % |
| Average wait / ride | {model.average('wait'):.1f} / {model.average('ride'):.1f} steps |
""")
