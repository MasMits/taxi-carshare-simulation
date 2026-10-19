"""Small Matplotlib view; all simulation rules stay in the Mesa model."""

import textwrap

import matplotlib.pyplot as plt
from matplotlib.widgets import Button, Slider

from .model import TaxiModel
from .plotting import draw_map

TICK_INTERVAL_MS = 600


class SimulationWindow:
    def __init__(self, **options):
        self.model, self.paused = TaxiModel(**options), False
        self.fig, self.ax = plt.subplots(figsize=(11, 7))
        self.fig.subplots_adjust(left=0.08, right=0.64, bottom=0.24, top=0.84)
        self.fig.canvas.manager.set_window_title("Mesa: passenger and taxi")
        self.pickup_line, self.trip_line, self.taxi_marker, self.person_marker = draw_map(self.ax, self.model)
        self.status = self.ax.set_title("")
        self.message_text = self.fig.text(0.68, 0.83, "", va="top", fontsize=10)
        self.buttons = []
        for x, label, callback in zip(
            (0.12, 0.38, 0.64),
            ("Pause", "Restart", "Step"),
            (self.toggle_pause, self.restart, self.single_step),
        ):
            button = Button(self.fig.add_axes([x, 0.10, 0.22, 0.05]), label)
            button.on_clicked(callback)
            self.buttons.append(button)
        self.speed_slider = Slider(self.fig.add_axes([0.25, 0.04, 0.5, 0.025]), "Playback", 0.5, 3, valinit=1)
        self.speed_slider.on_changed(self.change_speed)
        self.timer = self.fig.canvas.new_timer(interval=TICK_INTERVAL_MS)
        self.timer.add_callback(self.tick)
        self.fig.canvas.mpl_connect("close_event", lambda event: self.timer.stop())
        self.render()
        self.timer.start()

    def render(self):
        taxi, person = self.model.taxi, self.model.passenger
        self.taxi_marker.set_offsets([taxi.pos])
        self.person_marker.set_offsets([person.pos])
        for line, route in ((self.pickup_line, taxi.pickup_route), (self.trip_line, person.trip_route)):
            line.set_data(*zip(*route)) if route else line.set_data([], [])
        state = "Complete" if not self.model.running else "Paused" if self.paused else "Running"
        self.status.set_text(
            f"{state} · tick {self.model.ticks} · {taxi.distance} road moves\n"
            f"Passenger: {person.state} | Taxi: {taxi.state.replace('_', ' ')}"
        )
        events = [textwrap.fill(f"[{tick}] {text}", 34) for tick, text in self.model.events[-5:]]
        self.message_text.set_text("Agent messages\n\n" + "\n\n".join(events))
        self.buttons[0].label.set_text("Resume" if self.paused else "Pause")
        self.fig.canvas.draw_idle()

    def tick(self):
        if not self.paused and self.model.running:
            self.model.step()
            self.render()

    def toggle_pause(self, _event):
        self.paused = not self.paused
        self.render()

    def restart(self, _event):
        self.model, self.paused = TaxiModel(**self.model.config), False
        self.render()

    def single_step(self, _event):
        self.paused = True
        if self.model.running:
            self.model.step()
        self.render()

    def change_speed(self, value):
        self.timer.interval = round(TICK_INTERVAL_MS / value)
