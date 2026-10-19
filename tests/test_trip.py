"""Passenger/taxi communication, road routing and discrete transport."""

import unittest

from taxi_simulation.agents import PassengerAgent, TaxiAgent
from taxi_simulation.model import TaxiModel


class TaxiTripTests(unittest.TestCase):
    def finish_trip(self, model):
        initial_person = model.passenger.pos
        initial_taxi = model.taxi.pos
        pickup_seen = False
        for _ in range(200):
            previous_taxi = model.taxi.pos
            previous_person = model.passenger.pos
            previous_state = model.passenger.state
            model.step()
            taxi, person = model.taxi, model.passenger
            self.assertIn(taxi.pos, model.city.road_cells)
            self.assertIn(person.pos, model.city.road_cells)
            self.assertLessEqual(sum(abs(a - b) for a, b in zip(previous_taxi, taxi.pos)), 1)
            if previous_state in ("ready", "requesting", "waiting"):
                self.assertEqual(person.pos, initial_person)
            if person.state == "riding":
                pickup_seen = True
                self.assertEqual(person.pos, taxi.pos)
            if previous_person != person.pos:
                self.assertTrue(pickup_seen)
                self.assertEqual(person.pos, taxi.pos)
            if not model.running:
                break
        self.assertFalse(model.running)
        self.assertTrue(pickup_seen)
        self.assertEqual(model.passenger.state, "arrived")
        self.assertEqual(model.taxi.state, "done")
        self.assertEqual(model.passenger.pos, model.passenger.destination)
        self.assertEqual(model.taxi.pos, model.passenger.destination)
        self.assertEqual(len(model.agents), 2)
        expected_distance = len(model.city.find_path(initial_taxi, initial_person)) - 1
        expected_distance += len(model.passenger.trip_route) - 1
        self.assertEqual(model.taxi.distance, expected_distance)

    def test_initial_map_contains_exactly_two_agents(self):
        model = TaxiModel()
        self.assertEqual(len(model.agents), 2)
        self.assertIsInstance(model.passenger, PassengerAgent)
        self.assertIsInstance(model.taxi, TaxiAgent)
        self.assertNotEqual(model.passenger.pos, model.taxi.pos)
        self.assertEqual(model.passenger.state, "ready")
        self.assertEqual(model.taxi.state, "idle")
        self.assertEqual(model.messages, [])

    def test_request_reply_and_accept_precede_driving(self):
        model = TaxiModel()
        start = model.taxi.pos
        for kind in ("CFP", "PROPOSE", "ACCEPT"):
            model.step()
            self.assertEqual(model.messages[-1].kind, kind)
            self.assertEqual(model.taxi.pos, start)
        request = model.messages[0]
        self.assertEqual(request.route[0], model.passenger.pos)
        self.assertEqual(request.route[-1], model.passenger.destination)
        self.assertEqual(
            model.messages[1].eta,
            len(model.city.find_path(start, model.passenger.pos)) - 1,
        )
        self.finish_trip(model)
        self.assertEqual(
            [m.kind for m in model.messages],
            ["CFP", "PROPOSE", "ACCEPT", "BOARD", "BOARDED", "ARRIVED"],
        )

    def test_default_trip_stays_on_roads_and_collects_passenger(self):
        self.finish_trip(TaxiModel())

    def test_route_goes_around_blocks(self):
        model = TaxiModel()
        start, destination = (1, 3), (5, 3)
        path = model.city.find_path(start, destination)
        self.assertEqual(len(path) - 1, 8)
        self.assertTrue(all(cell in model.city.road_cells for cell in path))
        for a, b in zip(path, path[1:]):
            self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1)
        with self.assertRaises(ValueError):
            TaxiModel(passenger_start=(2, 2))

    def test_colocated_taxi_and_zero_length_trip(self):
        self.finish_trip(TaxiModel(taxi_start=(1, 1), passenger_start=(1, 1), destination=(1, 1)))

    def test_completed_trip_does_not_move_again(self):
        model = TaxiModel()
        self.finish_trip(model)
        snapshot = (model.ticks, model.taxi.distance, len(model.messages))
        model.step()
        self.assertEqual(snapshot, (model.ticks, model.taxi.distance, len(model.messages)))


if __name__ == "__main__":
    unittest.main()
