# Taxi carshare simulation (Mesa)

Multi-agent simulation of shared taxi rides in a city, built with [Mesa](https://mesa.readthedocs.io/).
Project of the course *Foundations of Agent-based Systems* (M1 DKAI, Université Paris-Saclay).
The development plan is in [PLAN.md](PLAN.md).

The city is a grid of square districts separated by one-cell roads. Taxis drive only on the roads,
along the shortest route; driving along one road cell takes `taxi_steps_per_cell` steps.
Passengers appear on the roads and call taxis (call for proposals); each free taxi makes an
offer, the passenger accepts the one that brings them to their destination earliest.

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
| Quick text check, no interface | `python -m taxi_simulation.model` |
| Tests | `python -m unittest discover tests` |

In the interface: press **▶** to run, **Step** for one step. After moving a slider, press **Reset**.

If the page shows only the controls and no map, an incompatible `ipyvuetify` is installed:
run `python -m pip install "ipyvuetify<2"` and restart.

## Files
```
main.py                     entry point (starts the web interface)
taxi_simulation/model.py    CityModel: the city (environment), scheduler, statistics
taxi_simulation/agents.py   the agents: Passenger and Taxi
taxi_simulation/messages.py messages between agents (contract net protocol)
taxi_simulation/app.py      SolaraViz interface
tests/                      unit tests
```
