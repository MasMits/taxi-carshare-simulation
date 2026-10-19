"""Regression checks for playback controls and model/view synchronization."""

import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from taxi_simulation.view import SimulationWindow


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.window = SimulationWindow()
        self.window.timer.stop()
        self.addCleanup(plt.close, self.window.fig)

    def test_pause_step_and_playback(self):
        window = self.window
        window.toggle_pause(None)
        window.tick()
        self.assertEqual(window.model.ticks, 0)
        window.single_step(None)
        self.assertEqual(window.model.ticks, 1)
        self.assertTrue(window.paused)
        window.speed_slider.set_val(2)
        self.assertEqual(window.timer.interval, 300)
        self.assertEqual(window.model.ticks, 1)

    def test_restart_clears_routes_and_messages(self):
        window = self.window
        for _ in range(6):
            window.model.step()
        window.render()
        self.assertGreater(len(window.pickup_line.get_xdata()), 0)
        self.assertGreater(len(window.trip_line.get_xdata()), 0)
        window.restart(None)
        self.assertEqual(window.model.ticks, 0)
        self.assertEqual(window.model.passenger.state, "ready")
        self.assertEqual(len(window.model.messages), 0)
        self.assertEqual(len(window.pickup_line.get_xdata()), 0)
        self.assertEqual(len(window.trip_line.get_xdata()), 0)

    def test_completed_trip_updates_markers_and_status(self):
        window = self.window
        for _ in range(100):
            if not window.model.running:
                break
            window.model.step()
        window.render()
        destination = window.model.passenger.destination
        self.assertEqual(tuple(window.person_marker.get_offsets()[0]), destination)
        self.assertEqual(tuple(window.taxi_marker.get_offsets()[0]), destination)
        self.assertIn("Complete", window.status.get_text())
        self.assertIn("Trip complete", window.message_text.get_text())
