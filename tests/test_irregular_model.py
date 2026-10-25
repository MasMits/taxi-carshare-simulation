"""Check generated streets, independent seeds and real traffic on irregular maps."""

import unittest

import networkx as nx

from taxi_simulation.irregular_model import IrregularCityModel, streets_cross


class IrregularCityTests(unittest.TestCase):
    def test_layouts_are_connected_and_have_no_unmodeled_crossings(self):
        for seed in (1, 7, 19, 50):
            for junctions in (12, 28, 40):
                with self.subTest(seed=seed, junctions=junctions):
                    model = IrregularCityModel(map_seed=seed, junction_count=junctions,
                                               n_taxis=0, demand=0)
                    self.assertTrue(nx.is_connected(model.network))
                    self.assertEqual(len(model.junctions), junctions)
                    streets = model.street_graph
                    self.assertTrue(any(degree == 1 for _, degree in streets.degree))
                    for a, b in streets.edges:
                        for c, d in streets.edges:
                            if {a, b} & {c, d}:
                                continue
                            coords = [model.coordinates[(-1, i)] for i in (a, b, c, d)]
                            self.assertFalse(streets_cross(*coords))

    def test_map_seed_is_independent_of_simulation_seed(self):
        first = IrregularCityModel(map_seed=7, seed=1, n_taxis=0)
        second = IrregularCityModel(map_seed=7, seed=99, n_taxis=20)
        different = IrregularCityModel(map_seed=8, seed=1, n_taxis=0)
        self.assertEqual(first.coordinates, second.coordinates)
        self.assertEqual(first.sections, second.sections)
        self.assertNotEqual(first.coordinates, different.coordinates)

    def test_more_connections_preserve_layout_and_add_loops(self):
        sparse = IrregularCityModel(extra_roads=0, n_taxis=0)
        dense = IrregularCityModel(extra_roads=1, n_taxis=0)
        for node in sparse.junctions:
            self.assertEqual(sparse.coordinates[node], dense.coordinates[node])
        self.assertEqual(sparse.street_graph.number_of_edges(), sparse.junction_count - 1)
        self.assertGreater(dense.street_graph.number_of_edges(), sparse.street_graph.number_of_edges())
        self.assertTrue(set(sparse.street_graph.edges) <= set(dense.street_graph.edges))

    def test_irregular_city_serves_people_without_lane_collisions(self):
        model = IrregularCityModel(seed=42, demand=0.8, max_wait=30, capacity=4)
        for _ in range(400):
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
        self.assertGreater(model.gave_up, 0)
        self.assertGreater(sum(t.traffic_delay for t in model.taxis()), 0)

    def test_invalid_generator_settings_fail_explicitly(self):
        for params in ({"junction_count": 1}, {"junction_count": 50}, {"extra_roads": -0.1}):
            with self.assertRaises(ValueError):
                IrregularCityModel(**params)


if __name__ == "__main__":
    unittest.main()
