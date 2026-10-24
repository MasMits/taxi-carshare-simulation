"""Start the web interface: python main.py  (same as: solara run taxi_simulation.app)."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "solara", "run", "taxi_simulation.app"],
                   cwd=Path(__file__).resolve().parent, check=False)
