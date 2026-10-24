"""Checks of the road map, routing and taxi movement."""

import unittest

from taxi_simulation.model import CityModel


class CityTests(unittest.TestCase):
    def test_roads_surround_every_district(self):
        model = CityModel(size=3, district_size=2, seed=1)
        self.assertEqual(model.grid.width, 3 * 3 + 1)
        self.assertIsNone(model.district_at((0, 5)))   # border = road
        self.assertIsNone(model.district_at((3, 1)))   # road between D0 and D1
        self.assertEqual(model.district_at((1, 1)), 0)
        self.assertEqual(model.district_at((4, 1)), 1)

    def test_route_goes_around_districts(self):
        model = CityModel(size=3, district_size=2, seed=1)
        start, goal = (0, 1), (3, 1)        # straight line would cross district D0
        self.assertEqual(model.distance(start, goal), 5)   # up to y=0 or y=3, across, back
        cell, route = start, [start]
        while cell != goal:
            cell = model.next_cell(cell, goal)
            route.append(cell)
        self.assertEqual(len(route) - 1, 5)
        self.assertTrue(all(c in model.is_road for c in route))

    def test_travel_time_is_taxi_steps_per_cell_per_road_cell(self):
        model = CityModel(size=3, district_size=2, taxi_steps_per_cell=3, seed=1)
        self.assertEqual(model.travel_time((0, 0), (3, 3)), 18)


class TaxiTests(unittest.TestCase):
    def test_taxi_moves_one_road_cell_every_taxi_steps_per_cell_steps(self):
        model = CityModel(n_taxis=1, taxi_steps_per_cell=3, seed=1)
        taxi = model.taxis().to_list()[0]
        steps_on_cell = 0
        for _ in range(300):
            before = taxi.pos
            model.step()
            steps_on_cell += 1
            if taxi.pos != before:
                self.assertEqual(abs(before[0] - taxi.pos[0]) + abs(before[1] - taxi.pos[1]), 1)
                self.assertGreaterEqual(steps_on_cell, 3)
                steps_on_cell = 0
        self.assertGreater(taxi.km, 0)

    def test_taxis_never_leave_the_roads(self):
        model = CityModel(n_taxis=20, seed=2)
        for _ in range(200):
            model.step()
            for taxi in model.taxis():
                self.assertIn(taxi.pos, model.is_road)

    def test_same_seed_same_run(self):
        runs = []
        for _ in range(2):
            model = CityModel(seed=7)
            for _ in range(50):
                model.step()
            runs.append(sorted(taxi.pos for taxi in model.taxis()))
        self.assertEqual(runs[0], runs[1])


class PassengerTests(unittest.TestCase):
    def run_model(self, steps=300, **params):
        model = CityModel(seed=3, **params)
        for _ in range(steps):
            model.step()
        return model

    def test_one_trip_timing(self):
        # step 1: call and proposal, step 2: accept and the taxi starts driving
        model = CityModel(n_taxis=1, demand=0, seed=1)
        taxi = model.taxis().to_list()[0]
        origin, destination = model.roads[0], model.roads[-1]
        model.add_passenger(origin, destination)
        expected_wait = 1 + model.travel_time(taxi.pos, origin) + model.boarding_time
        for _ in range(200):
            model.step()
        self.assertEqual(len(model.trips), 1)
        trip = model.trips[0]
        self.assertEqual(trip["wait"], expected_wait)
        self.assertEqual(trip["ride"], model.travel_time(origin, destination))
        self.assertEqual(len(model.passengers()), 0)

    def test_single_rides_have_no_detour(self):
        model = self.run_model()
        self.assertGreater(len(model.trips), 0)
        for trip in model.trips:
            self.assertEqual(trip["detour"], 1.0)
            self.assertFalse(trip["shared"])

    def test_every_passenger_is_accounted_for(self):
        model = self.run_model()
        self.assertEqual(model.spawned,
                         len(model.trips) + len(model.passengers()))

    def test_taxi_carries_one_passenger_at_a_time(self):
        model = CityModel(seed=4, demand=1.5)
        for _ in range(200):
            model.step()
            for taxi in model.taxis():
                self.assertLessEqual(len(taxi.onboard), 1)


if __name__ == "__main__":
    unittest.main()
