"""Summary panel to compare runs with 1 to 4 seats per taxi.

Run the simulation with the same seed until it stops, once per number of seats,
and compare the panels: every run gets the same passengers.
"""

import mesa.visualization.solara_viz as solara_viz
import solara
from mesa.visualization.utils import update_counter

REFUSAL_LABELS = {
    "capacity": "no seats available",
    "pickup_in_progress": "already heading to a confirmed pickup",
    "route_constraints": "incompatible route or pickup deadline",
    "commitment_conflict": "conflicts with existing commitments",
    "changed_ride": "offered ride time no longer available",
    "expired_or_unknown_offer": "offer expired or unavailable",
    "stale_or_foreign_offer": "offer identity mismatch",
    "search_timeout": "search deadline reached",
}


def layout(count):
    """Page 0: map and statistics side by side. Page 1: the charts, two per row."""
    if count == 2:
        return [{"i": 0, "w": 7, "h": 17, "moved": False, "x": 0, "y": 0},
                {"i": 1, "w": 5, "h": 18, "moved": False, "x": 7, "y": 0}]
    return [{"i": i, "w": 6, "h": 10, "moved": False, "x": 6 * (i % 2), "y": 10 * (i // 2)}
            for i in range(count)]


solara_viz.make_initial_grid_layout = layout  # shared by every city page

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

    reasons = ", ".join(f"{REFUSAL_LABELS.get(reason, reason)}: {count}" for reason, count in sorted(model.refusal_reasons.items())) or "none"
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
| Waiting for taxi confirmation | {model.count('confirming')} |
| Confirmed orders | {model.confirmed_orders} |
| Repeat searches / alternative attempts | {model.repeat_searches} / {model.alternative_attempts} |
| Missed pickup promises | {model.pickup_violations} |
| Average wait / ride | {model.average('wait'):.1f} / {model.average('ride'):.1f} steps |

Refusals and search cancellations: {reasons}
""")
