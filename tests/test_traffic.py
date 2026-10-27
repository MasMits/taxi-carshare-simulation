"""Cancellation, lane safety and junction reservation regression tests."""

import unittest

from taxi_simulation.agents import ASSIGNED, CONFIRMING, DROPOFF, RIDING, WAITING, Stop
from taxi_simulation.model import CityModel


class CancellationTests(unittest.TestCase):
    def test_waiting_passenger_leaves_at_deadline(self):
        model = CityModel(n_taxis=0, demand=0, max_wait=3, seed=1)
        passenger = model.add_passenger((0, 0), (8, 0))
        for _ in range(2):
            model.step()
        self.assertIn(passenger, model.passengers())
        model.step()
        self.assertNotIn(passenger, model.passengers())
        self.assertIsNone(passenger.pos)
        self.assertEqual(model.gave_up, 1)

    def test_confirmed_passenger_does_not_cancel_at_search_deadline(self):
        model = CityModel(n_taxis=1, demand=0, max_wait=3, seed=1)
        taxi = model.taxis().to_list()[0]
        model.grid.move_agent(taxi, (0, 0))
        passenger = model.add_passenger((1, 0), (8, 0))
        model.step()
        model.step()  # confirmed by taxi, confirmation is in the mailbox
        self.assertEqual(passenger.state, CONFIRMING)
        # Unexpected congestion after commitment cannot cancel the contract.
        taxi.progress = 0
        model.taxi_steps_per_cell = 10
        model.step()
        self.assertIn(passenger, model.passengers())
        self.assertIn(passenger.state, (ASSIGNED, "boarding"))
        self.assertEqual(model.gave_up, 0)

    def test_boarding_passenger_does_not_cancel(self):
        model = CityModel(n_taxis=1, demand=0, max_wait=3, boarding_time=5, seed=1)
        taxi = model.taxis().to_list()[0]
        model.grid.move_agent(taxi, (0, 0))
        model.add_passenger((0, 0), (8, 0))
        # Boarding takes longer than the request timeout, but has already begun.
        for _ in range(30):
            model.step()
        self.assertEqual(model.gave_up, 0)
        self.assertEqual(len(model.trips), 1)

    def test_queue_is_limited_by_patience_and_everyone_is_accounted_for(self):
        model = CityModel(n_taxis=3, demand=2, max_wait=15, seed=7)
        for _ in range(300):
            model.step()
            self.assertEqual(model.spawned, len(model.trips) + model.gave_up + len(model.passengers()))
            for passenger in model.passengers():
                if passenger.state in (WAITING, CONFIRMING):
                    self.assertLess(model.steps - passenger.request_step, model.max_wait)
            for taxi in model.taxis():
                self.assertTrue(all(stop.passenger in model.passengers() for stop in taxi.plan))
        self.assertGreater(model.gave_up, 0)


class TrafficTests(unittest.TestCase):
    def setUp(self):
        self.model = CityModel(n_taxis=2, demand=0, max_wait=10000, seed=1)
        self.first, self.second = self.model.taxis().to_list()

    def drive(self, taxi, pos, goal, heading, parked=False):
        model = self.model
        model.grid.move_agent(taxi, pos)
        passenger = model.add_passenger(pos, goal)
        passenger.state = RIDING
        passenger.pickup_step = 0
        model.grid.remove_agent(passenger)
        taxi.onboard[passenger] = 0
        taxi.plan = [Stop(goal, DROPOFF, passenger, 100000)]
        taxi.heading = heading
        taxi.in_traffic = not parked

    def test_follower_cannot_pass_slow_leader(self):
        self.model.taxi_steps_per_cell = 2
        self.drive(self.first, (2, 0), (8, 0), (1, 0))
        self.drive(self.second, (1, 0), (8, 0), (1, 0))
        self.second.progress = 1
        self.model.step()
        self.assertEqual(self.second.pos, (1, 0))
        self.assertTrue(self.second.blocked)
        self.model.step()
        self.assertEqual(self.first.pos, (3, 0))
        self.assertEqual(self.second.pos, (1, 0))
        self.model.step()
        self.assertEqual(self.second.pos, (2, 0))
        self.assertEqual(self.second.traffic_delay, 2)

    def test_opposite_lanes_can_pass(self):
        self.drive(self.first, (1, 0), (8, 0), (1, 0))
        self.drive(self.second, (2, 0), (0, 0), (-1, 0))
        self.model.step()
        self.assertEqual(self.first.pos, (2, 0))
        self.assertEqual(self.second.pos, (1, 0))

    def test_junction_admits_one_car_and_then_both_clear_it(self):
        self.drive(self.first, (3, 4), (8, 4), (1, 0))
        self.drive(self.second, (4, 3), (4, 8), (0, 1))
        self.model.step()
        self.assertEqual(sum(t.pos == (4, 4) for t in self.model.taxis()), 1)
        self.assertEqual(sum(t.blocked for t in self.model.taxis()), 1)
        for _ in range(5):
            self.model.step()
        self.assertGreaterEqual(self.first.pos[0], 5)
        self.assertGreaterEqual(self.second.pos[1], 5)

    def test_blocked_exit_prevents_junction_entry(self):
        self.model.taxi_steps_per_cell = 2
        self.drive(self.first, (5, 4), (8, 4), (1, 0))
        self.drive(self.second, (3, 4), (8, 4), (1, 0))
        self.second.progress = 1
        self.model.step()
        self.assertEqual(self.second.pos, (3, 4))
        self.assertTrue(self.second.blocked)

    def test_reserved_exit_cannot_be_taken_by_a_merging_car(self):
        self.drive(self.first, (3, 4), (8, 4), (1, 0))
        self.model.step()
        self.assertEqual(self.first.junction_exit, (5, 4))
        self.drive(self.second, (5, 4), (8, 4), (1, 0), parked=True)
        self.model.step()
        self.assertEqual(self.first.pos, (5, 4))
        self.assertTrue(self.second.blocked)
        self.assertFalse(self.second.in_traffic)

    def test_reversal_waits_for_a_junction(self):
        self.drive(self.first, (2, 0), (1, 0), (1, 0))
        self.assertEqual(self.first.route_to((1, 0)), ((3, 0), (4, 0), (3, 0), (2, 0), (1, 0)))
        self.assertEqual(self.first.plan_distance(self.first.plan), 5)
        for _ in range(3):
            self.model.step()
        self.assertEqual(self.first.pos, (3, 0))
        self.assertEqual(self.first.heading, (-1, 0))

    def test_parked_taxi_does_not_block_lane(self):
        self.model.grid.move_agent(self.second, (2, 0))
        self.second.heading = (1, 0)
        self.drive(self.first, (1, 0), (8, 0), (1, 0))
        self.model.step()
        self.assertEqual(self.first.pos, (2, 0))

    def test_dense_run_has_unique_lanes_and_reproducible_results(self):
        results = []
        for _ in range(2):
            model = CityModel(size=3, district_size=2, n_taxis=30, demand=1.5,
                              max_wait=30, allow_detour=True, seed=13)
            for _ in range(250):
                before = {t: (t.pos, t.heading) for t in model.taxis()}
                model.step()
                slots = [model.lane_key(t.pos, t.heading) for t in model.taxis() if t.in_traffic]
                self.assertEqual(len(slots), len(set(slots)))
                for taxi in model.taxis():
                    pos, heading = before[taxi]
                    if taxi.pos != pos and heading is not None and not model.is_intersection(pos):
                        self.assertEqual(taxi.heading, heading)
                    self.assertLessEqual(taxi.booked(), model.capacity)
            self.assertGreater(sum(t.traffic_delay for t in model.taxis()), 0)
            results.append((model.trips, model.gave_up, sorted(t.pos for t in model.taxis())))
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
