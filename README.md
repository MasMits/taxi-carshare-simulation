# Taxi carshare simulation (Mesa)

Multi-agent simulation of shared taxi rides in a city, built with [Mesa](https://mesa.readthedocs.io/).
Project of the course *Foundations of Agent-based Systems* (M1 DKAI, Université Paris-Saclay).
The development plan is in [PLAN.md](PLAN.md).

The city is a grid of square districts separated by one-cell roads. Taxis drive only on the roads,
along the shortest route; driving along one road cell takes `taxi_steps_per_cell` steps.
Passengers appear on the roads and call taxis (call for proposals); each free taxi makes an
offer, the passenger accepts the one that brings them to their destination earliest.

## Pollution

Each taxi counts the CO2 it emits:
- driving: every road cell costs `cell_km × co2_per_km` (defaults: 0.25 km, 150 g CO2/km);
- stuck in traffic: every blocked step costs `idle_co2_per_step` (default 25 g, engine running);
- parked at the curb: engine off, no emission.

The model reports `CO2 (kg)` for the whole fleet and `CO2 per passenger (g)` (fleet CO2 / served
passengers). Compare this second value for 1 seat (classic taxis) and 2+ seats (shared taxis).

### Comparing 1 seat with 2-4 seats
Passenger requests use their own random generator, so with the same seed every run gets exactly the
same passengers, whatever the taxis do. Each run stops at **Stop at step** (default 1000).
To finish faster, lower **Play Interval** or raise **Render Interval** (e.g. 10).
1. Tick **Taxis may change their route to pick someone up** (otherwise 3-4 seats behave like 2).
2. Set **Seats per taxi** to 1, press **Reset**, then **▶** and wait until the panel says *finished*.
3. Screenshot the statistics panel (CO₂ per passenger, km, passengers served...).
4. Repeat with 2, 3 and 4 seats, changing nothing else.

With the default settings (seed 42, detours on, 1000 steps, ~314 passengers) CO₂ per passenger goes
from about 1,410 g with 1 seat to 1,070 g with 2 seats and about 1,030-1,045 g with 3-4 seats.

## Waiting and traffic

New requests arrive at **0.3 passengers/step**. They expire after **60 steps** if boarding hasn't started. Assigned taxis are notified of cancellations.

**Traffic: lanes and queues** (default):
- Road cells have one slot per direction; turns only at intersections.
- Movement uses occupancy snapshots; cars wait if the lane ahead was occupied.
- Junctions admit one car at a time if the exit is clear. Longest-waiting has priority.
- Idle or boarding cars pull over and must merge back; they don't block traffic.
- Magenta borders show blocked cars; squares show parked cars. `Traffic delay` is cumulative blocked steps.

Arrival ETAs use free-flow times and heading constraints. Congestion may exceed detour limits. Turning traffic off also disables heading constraints. Gridlock can occur at very high density.

Adjust **Maximum wait**, demand, taxis, and speed, then **Reset**. For more congestion, use a smaller city or more taxis.

## Install
Python 3.12 or newer.
```
python -m pip install -r requirements.txt
```

## Run
| What | Command |
|---|---|
| Web interface (opens in the browser) | `python main.py` |
| Same, directly with Solara | `solara run taxi_simulation.app` |
| Ring-road graph demo | `solara run taxi_simulation.ring_app --port 8766` |
| Irregular graph-city demo | `solara run taxi_simulation.irregular_app --port 8767` |
| Quick text check, no interface | `python -m taxi_simulation.model` |
| Tests | `python -m unittest discover tests` |

In the interface: press **▶** to run, **Step** for one step. After moving a slider, press **Reset**.

## Ring-road graph demo

Open the separate ring demo to see the same simulation on two circular roads with radial streets.
It uses Mesa `NetworkGrid` over a NetworkX graph, rather than a rectangular grid. Junctions are
connected by road sections subdivided into traffic slots, with separate lanes in each direction.
The graph determines movement; drawing coordinates only determine the shape on screen.
The same taxi/passenger agents handle calls, sharing, queues and request cancellation.

Change **Radial streets** and press **Reset** to rebuild the city. Capacity can range from 1 to 4.
Triangles show moving taxis, squares show taxis at the curb, and a magenta border marks blocked
cars. Blue/green dots are waiting/assigned passengers; dashed lines show occupied taxi routes.
The map updates from the actual model, alongside the passenger and traffic charts.

This is a graph-city prototype: each road slot has equal free-flow travel cost (roughly 1.5
drawing units), and route planning does not yet predict congestion. The standard grid demo
and its launch command remain available for comparison.

If the page shows only the controls and no map, an incompatible `ipyvuetify` is installed:
run `python -m pip install "ipyvuetify<2"` and restart.

## Irregular city demo

The irregular demo generates scattered junctions, streets of different lengths, loops,
T-junctions and dead ends. A minimum spanning tree keeps every junction reachable; extra
roads are added without crossing existing roads. It uses the same agents, lanes, traffic
queues, cancellations, route drawing and charts as the ring demo.

Change **City layout seed** to generate another city, **Junctions** to change its size, or
**Additional road probability** for more alternative routes, then press **Reset**. The map
seed is separate from the simulation seed, so changing agent randomness does not rebuild
the street layout. Both graph demos share their road-space and rendering code.

Both launch modules only select a model and its map controls. `graph_page` in
`graph_view.py` supplies the shared controls, map and charts; `RoadGraphModel`
supplies common model defaults. The two city classes contain only map settings
and generation, forwarding simulation parameters to the shared model.

## Files
```
main.py                     entry point (starts the web interface)
taxi_simulation/model.py    CityModel: the city (environment), scheduler, statistics
taxi_simulation/agents.py   the agents: Passenger and Taxi
taxi_simulation/messages.py messages between agents (contract net protocol)
taxi_simulation/app.py      SolaraViz interface
taxi_simulation/ring_model.py Graph city: circular roads and radial streets
taxi_simulation/ring_app.py   Live ring-road demo
taxi_simulation/irregular_model.py Seeded irregular street generator
taxi_simulation/irregular_app.py Live irregular-city demo
taxi_simulation/graph_model.py Shared graph road space and directional slots
taxi_simulation/graph_view.py  Shared graph-city visualization
tests/                      unit tests
```
