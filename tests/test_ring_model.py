"""Ensure the graph demo reuses real passenger and traffic behaviour."""

import unittest

import networkx as nx
from mesa.space import NetworkGrid

from taxi_simulation.ring_model import RingCityModel


class RingCityTests(unittest.TestCase):
    def test_mesa_reset_preserves_shared_parameters(self):
        from mesa.visualization.solara_viz import _build_model_init_kwargs

        from taxi_simulation.irregular_model import IrregularCityModel

        for model_class in (RingCityModel, IrregularCityModel):
            params = {"seed": 42, "n_taxis": 3, "capacity": 4, "traffic": True,
                      "offer_ttl": 4, "pickup_slack": 2, "wait_priority": 0.8}
            original = model_class(**params)
            reset_params = _build_model_init_kwargs(original, params, add_scenario_when_empty=True,
                                                    require_model_accepts_scenario=True)
            reset = model_class(**reset_params)
            for _ in range(10):
                original.step()
                reset.step()
            self.assertEqual(reset.capacity, 4)
            for key in ("offer_ttl", "pickup_slack", "wait_priority"):
                self.assertEqual(getattr(reset, key), params[key])
            self.assertEqual([t.pos for t in original.taxis()], [t.pos for t in reset.taxis()])
            self.assertTrue(original.datacollector.get_model_vars_dataframe().equals(
                reset.datacollector.get_model_vars_dataframe()))

    def test_connected_graph_with_real_road_slots_for_each_layout(self):
        for arms in (4, 6, 8, 10, 12):
            with self.subTest(arms=arms):
                model = RingCityModel(arms=arms, n_taxis=0, demand=0)
                self.assertIsInstance(model.grid, NetworkGrid)
                self.assertTrue(nx.is_connected(model.network))
                self.assertEqual(len(model.junctions), 2 * arms + 1)
                self.assertEqual(len(model.sections), 4 * arms)
                for section in model.sections:
                    self.assertGreaterEqual(len(section), 3)
                    for a, b in zip(section, section[1:]):
                        self.assertTrue(model.network.has_edge(a, b))

    def test_curved_road_keeps_heading_until_junction(self):
        model = RingCityModel(n_taxis=0, demand=0)
        section = model.sections[0]
        start, target = section[1], section[0]
        heading = model.direction(section[0], start)
        route = model.route(start, target, heading)
        # A passenger behind the car cannot cause an immediate mid-road reversal.
        self.assertEqual(route[0], section[2])
        self.assertIn(section[-1], route)
        for a, b in zip((start,) + route, route):
            self.assertTrue(model.network.has_edge(a, b))
        cell = start
        current_heading = heading
        for nxt in route:
            next_heading = model.direction(cell, nxt)
            if not model.is_intersection(cell):
                self.assertEqual(next_heading, current_heading)
            cell, current_heading = nxt, next_heading

    def test_drawing_coordinates_do_not_change_routes(self):
        model = RingCityModel(n_taxis=0, demand=0)
        start, target = model.sections[0][1], model.sections[5][-2]
        expected = model.route(start, target)
        model.coordinates = {node: (x * 2 + 100, y * 3 - 50)
                             for node, (x, y) in model.coordinates.items()}
        model._routes.clear()
        self.assertEqual(model.route(start, target), expected)

    def test_unconfirmed_graph_passenger_still_leaves_at_search_deadline(self):
        model = RingCityModel(n_taxis=0, demand=0, max_wait=3, seed=1)
        passenger = model.add_passenger(model.roads[0], model.roads[-1])
        model.step()
        model.step()
        self.assertIn(passenger, model.passengers())
        model.step()
        self.assertNotIn(passenger, model.passengers())
        self.assertEqual(model.gave_up, 1)

    def test_graph_runs_traffic_sharing_and_cancellation_reproducibly(self):
        runs = []
        for _ in range(2):
            model = RingCityModel(arms=4, n_taxis=24, capacity=4, demand=1,
                                  max_wait=30, seed=9)
            for _ in range(300):
                before = {taxi: (taxi.pos, taxi.heading) for taxi in model.taxis()}
                model.step()
                slots = [model.lane_key(t.pos, t.heading) for t in model.taxis() if t.in_traffic]
                self.assertEqual(len(slots), len(set(slots)))
                self.assertEqual(model.spawned, len(model.trips) + model.gave_up + len(model.passengers()))
                for taxi in model.taxis():
                    old, heading = before[taxi]
                    if old != taxi.pos:
                        self.assertTrue(model.network.has_edge(old, taxi.pos))
                        if heading is not None and not model.is_intersection(old):
                            self.assertEqual(taxi.heading, heading)
                    self.assertLessEqual(taxi.booked(), model.capacity)
            self.assertGreater(len(model.trips), 0)
            self.assertTrue(any(t['shared'] for t in model.trips))
            # Cancellations are not required when every search is confirmed in time.
            self.assertGreater(model.confirmed_orders, 0)
            for passenger in model.passengers():
                if passenger.state in ('waiting', 'confirming'):
                    self.assertLess(model.steps - passenger.request_step, model.max_wait)
            self.assertGreater(sum(t.traffic_delay for t in model.taxis()), 0)
            runs.append((model.trips, model.gave_up, [t.pos for t in model.taxis()]))
        self.assertEqual(runs[0], runs[1])


if __name__ == "__main__":
    unittest.main()
