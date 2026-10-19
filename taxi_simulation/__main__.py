"""Start the simulation in a native interactive window."""

import sys


def main():
    import matplotlib

    # Select the backend before importing pyplot to bypass PyCharm's plot pane.
    matplotlib.use("MacOSX" if sys.platform == "darwin" else "TkAgg", force=True)
    import matplotlib.pyplot as plt

    from .view import SimulationWindow

    window = SimulationWindow()
    plt.show(block=True)
    return window


if __name__ == "__main__":
    main()
