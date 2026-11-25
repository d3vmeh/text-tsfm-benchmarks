"""Build the DE CarbonCast pilot and full windows.

All the build code is in aeci_pilot.py. This file only runs it with DE's settings (source files, split
dates, pilot days and fuel list), which are set in aeci_pilot.configure_grid().

Run from the repo root:  python3 scripts/de_pilot.py
"""
from aeci_pilot import main


if __name__ == "__main__":
    main(grid="DE")
