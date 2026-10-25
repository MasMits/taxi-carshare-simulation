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
        model = self.run_model(capacity=1, traffic=False)
        self.assertGreater(len(model.trips), 0)
        for trip in model.trips:
            self.assertEqual(trip["detour"], 1.0)
            self.assertFalse(trip["shared"])

    def test_every_passenger_is_accounted_for(self):
        model = self.run_model()
        self.assertEqual(model.spawned,
                         len(model.trips) + model.gave_up + len(model.passengers()))

    def test_taxi_carries_one_passenger_at_a_time(self):
        model = CityModel(seed=4, demand=1.5, capacity=1)
        for _ in range(200):
            model.step()
            for taxi in model.taxis():
                self.assertLessEqual(len(taxi.onboard), 1)


class SharingTests(unittest.TestCase):
    def run_model(self, steps=200, **params):
        model = CityModel(seed=5, demand=1.5, capacity=2, allow_detour=False, **params)
        for _ in range(steps):
            model.step()
            for taxi in model.taxis():
                self.assertLessEqual(taxi.booked(), 2)  # never overbooked
        return model

    def test_two_seats_without_detours_share_some_trips(self):
        model = self.run_model()
        self.assertTrue(any(trip["shared"] for trip in model.trips))

    def test_shared_rides_stay_within_tolerance(self):
        # Free-flow planning guarantees a tolerance; actual queues can add delay.
        model = self.run_model(traffic=False)
        for trip in model.trips:
            self.assertLessEqual(trip["detour"], model.max_detour + 1e-9)

    def taxi_on_bottom_road(self, allow_detour):
        """One taxi at (0, 0) driving a passenger to (24, 0), along the bottom road."""
        model = CityModel(n_taxis=1, demand=0, capacity=2, allow_detour=allow_detour, seed=1)
        taxi = model.taxis().to_list()[0]
        model.grid.move_agent(taxi, (0, 0))
        first = model.add_passenger((0, 0), (24, 0))
        taxi.plan = taxi.best_insertion(first.trip(), first)[1]
        return model, taxi

    def test_passenger_on_the_route_can_join(self):
        model, taxi = self.taxi_on_bottom_road(allow_detour=False)
        second = model.add_passenger((4, 0), (12, 0))
        self.assertIsNotNone(taxi.best_insertion(second.trip(), second))

    def test_passenger_off_the_route_needs_a_detour(self):
        model, taxi = self.taxi_on_bottom_road(allow_detour=False)
        second = model.add_passenger((0, 4), (12, 0))
        self.assertIsNone(taxi.best_insertion(second.trip(), second))
        model, taxi = self.taxi_on_bottom_road(allow_detour=True)
        second = model.add_passenger((0, 4), (12, 0))
        self.assertIsNotNone(taxi.best_insertion(second.trip(), second))

class PollutionTests(unittest.TestCase):
    def test_driving_emits_co2_per_km(self):
        model = CityModel(n_taxis=1, demand=0, cell_km=0.5, co2_per_km=100, seed=1)
        taxi = model.taxis().to_list()[0]
        taxi.count_km()
        taxi.count_km()
        self.assertEqual(taxi.co2, 2 * 0.5 * 100)

    def test_stuck_in_traffic_emits_co2(self):
        model = CityModel(n_taxis=1, demand=0, idle_co2_per_step=30, seed=1)
        taxi = model.taxis().to_list()[0]
        taxi.count_idle()
        self.assertEqual(taxi.co2, 30)

    def test_fleet_co2_matches_km_and_traffic_delay(self):
        model = CityModel(seed=2, demand=1.0)
        for _ in range(200):
            model.step()
        expected = (model.vehicle_km() * model.cell_km * model.co2_per_km
                    + sum(t.traffic_delay for t in model.taxis()) * model.idle_co2_per_step)
        self.assertAlmostEqual(model.co2(), expected)

    def test_parked_taxis_do_not_emit(self):
        model = CityModel(n_taxis=3, demand=0, seed=1)
        for _ in range(20):
            model.step()
        self.assertEqual(model.co2(), 0)


if __name__ == "__main__":
    unittest.main()
