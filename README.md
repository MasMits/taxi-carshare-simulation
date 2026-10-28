# Taxi carshare simulation (Mesa)

Multi-agent simulation of shared taxi rides in a city, built with [Mesa](https://mesa.readthedocs.io/).
Project of the course _Foundations of Agent-based Systems_ (M1 DKAI, Université Paris-Saclay).
The development plan is in [PLAN.md](PLAN.md).

The city is a grid of square districts separated by one-cell roads. Taxis drive only on the roads,
along the shortest route; driving along one road cell takes `taxi_steps_per_cell` steps.
Passengers appear on the roads and call taxis (call for proposals). Taxis with available seats
can offer a direct or shared ride. The passenger tries the offer with the earliest predicted
arrival and waits for an explicit taxi confirmation before the booking becomes binding.

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
2. Set **Seats per taxi** to 1, press **Reset**, then **▶** and wait until the panel says _finished_.
3. Screenshot the statistics panel (CO₂ per passenger, km, passengers served...).
4. Repeat with 2, 3 and 4 seats, changing nothing else.

Re-run comparisons after changing the allocation policy: pickup promises and
waiting priority affect both service rates and emissions. Compare the fraction served alongside
CO₂ per passenger, including passengers still waiting or riding when the run stops.

## Waiting and traffic

New requests arrive at **0.3 passengers/step**. An unconfirmed search expires after **60 steps**.
After explicit taxi confirmation, the passenger keeps the booking even if traffic delays pickup.
A confirmed taxi does not abandon that passenger to pursue a more attractive request.
A green passenger is the taxi's **next stop**, not a booking queued behind other pickups or
drop-offs. Each taxi can have at most one confirmed passenger awaiting pickup; it may
already be carrying other riders. Once that pickup starts boarding, it may accept a new
compatible pickup as its next stop. New requests cannot displace a confirmed pickup.

### Negotiation and allocation

Passenger states are `waiting` (searching), `confirming` (acceptance sent), `assigned`
(taxi confirmed), `boarding`, `riding`, and `arrived`.

1. A passenger broadcasts a CFP with a new round ID, origin, destination, ride tolerance,
   original request time and search deadline.
2. A taxi replies with a unique offer ID, expiry, predicted pickup/ride times and an absolute
   latest pickup time. Offers are provisional, not seat reservations.
3. The passenger accepts one offer and retains the others until confirmation or expiry.
4. A taxi ranks competing acceptances, rechecks the offered conditions against its current route,
   and replies with CONFIRM or FAILURE and a reason. Confirmation is allowed only when the
   new pickup can be the next stop and no confirmed pickup is still pending. A duplicate
   acceptance cannot book twice.
5. A refused passenger tries a saved alternative in the same round. A fresh broadcast is needed
   only after acceptable alternatives are exhausted. Confirmation releases unused offers.

An empty taxi ranks requests by predicted time to reach pickup; a busy taxi uses added driving
time along its current route. Both subtract `wait_priority * waiting_age` from that cost.
Lower cost wins; original request time, then passenger ID break ties, so mailbox order does not
choose the winner. Priorities are recalculated after each accepted booking. There is no central
dispatcher, and individual taxis still make their own decisions.

Pickup routes account for the direction needed after boarding. If the shortest approach would
leave a taxi facing the wrong way, it can pass the pickup, turn legally at a junction and
return before boarding. That empty approach time is included in the offer; passengers are
not refused merely because a shortest approach would add an avoidable turnaround to their ride.
The same route is used for planning, movement and junction-exit reservations.
Yellow taxis have no bookings; orange taxis are assigned or carrying passengers.

Every new insertion must preserve the pickup deadlines and ride tolerances of all confirmed
passengers. Pickup promises refer to **boarding starting**, not boarding finishing. Newcomers
cannot push an existing promise back. Predictions use free-flow travel: congestion can still
cause a missed promise; each affected booking is counted once and remains active.

The controls are shared by grid, ring and irregular demos:

| Parameter / control                          | Default | Meaning                                                                                     |
| -------------------------------------------- | ------: | ------------------------------------------------------------------------------------------- |
| `max_wait` / Search timeout                  |      60 | Maximum search duration before confirmation; does not limit future pickup time              |
| `offer_ttl` / Offer validity                 |       6 | Number of steps a saved offer remains eligible for acceptance                               |
| `pickup_slack` / Pickup promise margin       |       3 | Allowed margin over the pickup forecast when confirming; never extends the offered deadline |
| `wait_priority` / Waiting passenger priority |     0.5 | Pickup/route time cost removed per step already waited; 0 disables aging                    |

The provisional offer allows up to `offer_ttl` steps of negotiation beyond its initial approach
forecast. Confirmation tightens that bound to the current forecast plus `pickup_slack`.
The search deadline only limits when a taxi can confirm, not when boarding must start.
There is no maximum approach distance or time: even a distant taxi can accept before the
search expires. Nearer and on-route requests still receive preference in the ranking.

Round ID, offer ID and sender must match before an acceptance, confirmation or trip event can
change state. Expired offers and superseded rounds cannot create a new booking. Once confirmed,
contract identity remains valid through arrival, independently of the proposal's expiry.

The statistics panel shows pending confirmations, confirmed bookings, repeated broadcasts,
attempts using saved alternatives, missed pickup promises and refusal reasons. These are event
counts, not counts of distinct passengers: one passenger can receive several taxi refusals.

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

| What                                 | Command                          |
| ------------------------------------ | -------------------------------- |
| Web interface (opens in the browser) | `python main.py`                 |
| Same, directly with Solara           | `solara run taxi_simulation.app` |
| Quick text check, no interface       | `python -m                       |

In the interface: choose the map with the tabs at the top (**Grid city**, **Ring city**,
**Irregular city**), press **▶** to run, **Step** for one step. After moving a slider, press **Reset**.

## Ring-road graph demo

Open the **Ring city** tab to see the same simulation on two circular roads with radial streets.
It uses Mesa `NetworkGrid` over a NetworkX graph, rather than a rectangular grid. Junctions are
connected by road sections subdivided into traffic slots, with separate lanes in each direction.
The graph determines movement; drawing coordinates only determine the shape on screen.
The same taxi/passenger agents handle calls, sharing, queues and request cancellation.

Change **Radial streets** and press **Reset** to rebuild the city. Capacity can range from 1 to 4.
Triangles show moving taxis, squares show taxis at the curb, and a magenta border marks blocked
cars. Blue/purple/green dots are searching/confirming/assigned passengers; dashed lines show occupied taxi routes.
The map updates from the actual model, alongside the passenger and traffic charts.

This is a graph-city prototype: each road slot has equal free-flow travel cost (roughly 1.5
drawing units), and route planning does not yet predict congestion. The standard grid demo
remains available in the **Grid city** tab for comparison.

If the page shows only the controls and no map, an incompatible `ipyvuetify` is installed:
run `python -m pip install "ipyvuetify<2"` and restart.

## Irregular city demo

The **Irregular city** tab generates scattered junctions, streets of different lengths, loops,
T-junctions and dead ends. A minimum spanning tree keeps every junction reachable; extra
roads are added without crossing existing roads. It uses the same agents, lanes, traffic
queues, cancellations, route drawing and charts as the ring demo.

Change **City layout seed** to generate another city, **Junctions** to change its size, or
**Additional road probability** for more alternative routes, then press **Reset**. The map
seed is separate from the simulation seed, so changing agent randomness does not rebuild
the street layout. Both graph demos share their road-space and rendering code.

## Files

Folders follow the features: the simulation core, one folder per map, and the shared interface.
Every map is a subclass of `CityModel` that only builds its roads (`build_map`) and says how
they connect (`road_neighbours`, `is_intersection`, `direction`); agents, messages, traffic and
statistics are the same for every map.

```
main.py                       entry point (starts the web interface)
taxi_simulation/
  app.py                      web interface: one tab per city map
  core/
    model.py                  CityModel: environment, scheduler, statistics
    roads.py                  what each map defines, and the routes taxis drive
    traffic.py                lanes, junctions, moving all taxis at once
    passenger.py              Passenger agent (calls taxis, picks an offer)
    taxi.py                   Taxi agent (answers calls, drives, boards)
    planning.py               taxi plan: routes to stops, where a new trip fits
    messages.py               messages between agents (contract net protocol)
  grid/   model.py, page.py   grid city: square districts on a Mesa MultiGrid
  graph/  model.py, map.py    road-graph city on a Mesa NetworkGrid, and its map
  ring/   model.py, page.py   ring city: two circular roads and radial streets
  irregular/ model.py, page.py  irregular city: seeded random streets
  ui/
    page.py                   controls, charts and layout shared by every page
    stats.py                  statistics panel (CO2 per passenger...)
    drawing.py                colours and drawing helpers shared by every map
```
