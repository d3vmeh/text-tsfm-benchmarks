"""Hourly weather series for CarbonCast windows, for models that take numeric covariates.

The window text gives the weather as daily summaries. This gives the same weather information hour by hour,
for the 504 past hours and the 72 future hours of each window, so a forecasting model can be handed it as
numbers. Nothing here is a measurement of what happened: every value is a forecast, taken only from blocks
of the weather file that were available at the window's forecast start.

AECI builds both readings of the weather file's timestamps (see aeci_pilot.py).
DE builds the guide alignment.
  guide          a row forecasts the hour on its own timestamp
  one_day_later  a row forecasts the hour 24 hours after its timestamp

For a window with issue day D and forecast start D 06:00:
  future hours   come from the one block the window text uses (labeled D for guide, D-1 for one_day_later)
  past hours     each comes from the block that starts on that row's own date, which is never later than
                 the block used for the future hours

Writes outputs/covariates/AECI_<split>_covariates_<alignment>.jsonl, one line per window:
  {"window_id", "name", "seed", "alignment", "variables", "past_covariates": {var: [504]}, "future_covariates": {var: [72]}}

Run from the repo root:  python3 scripts/aeci_covariates.py [--splits validation]
For DE: python3 scripts/aeci_covariates.py --grid DE [--splits validation,test]
"""
import argparse, json
from datetime import datetime, timedelta
from pathlib import Path

import aeci_pilot as ap

OUT = ap.ROOT / "outputs/covariates"
VARIABLES = {  # name in the output -> (weather column, conversion)
    "wind_speed_m_s": (ap.WX["wind"], lambda v: v),
    "solar_w_m2": (ap.WX["solar"], lambda v: v),
    "temperature_c": (ap.WX["temp"], lambda v: v - 273.15),
    "precipitation": (ap.WX["precip"], lambda v: v),
}
SHIFT = {"guide": 0, "one_day_later": 1}


class BlockUnavailable(Exception):
    """Raised when a weather block a window needs is missing, duplicated or incomplete."""
    pass


def block_rows(runs, start):
    """The 96 rows of the block that starts at `start`, as {timestamp: row}. Raises if it is missing, duplicated or short."""
    try:
        copies = runs[start]
    except KeyError:
        raise BlockUnavailable(f"no block starts at {start}")
    if len(copies) != 1 or len(copies[0]) != ap.RUN_ROWS:
        raise BlockUnavailable(f"block at {start} is duplicated or incomplete")
    return {t: r for t, r in copies[0]}


def build_covariates(runs, day, alignment, cache=None):
    """Returns (past, future): {variable: [values]} for the 504 past and 72 future hours of the window.

    `runs` is what aeci_pilot.load_weather_runs() returned, `day` is the issue day, and `alignment` is
    "guide" or "one_day_later". `cache` may be shared between calls to avoid re-reading the same block.
    Raises BlockUnavailable if any block the window needs cannot be used."""
    shift = timedelta(days=SHIFT[alignment])
    start = datetime(day.year, day.month, day.day, 6)
    latest_block = datetime(day.year, day.month, day.day) - shift          # the block the window text uses
    cache = {} if cache is None else cache
    def value_rows(t):
        """The weather row that forecasts hour t, taken from the newest block allowed for that hour."""
        label = t - shift                                                  # the row whose forecast is for hour t
        block = min(datetime(label.year, label.month, label.day), latest_block)
        if block not in cache:
            cache[block] = block_rows(runs, block)
        return cache[block][label]
    past = {v: [] for v in VARIABLES}
    future = {v: [] for v in VARIABLES}
    for k in range(-ap.HIST, ap.HORIZON):                                   # k < 0 is a past hour, k >= 0 a future hour
        row = value_rows(start + timedelta(hours=k))
        for name, (col, conv) in VARIABLES.items():
            (past if k < 0 else future)[name].append(conv(float(row[col])))
    return past, future


def main():
    # For each reading of the weather file and each split: go through the issue days, keep the ones that pass
    # the same filters as the window build, build their covariates, leak-test them, and write one line each.
    ap_ = argparse.ArgumentParser(description="Hourly weather covariates for CarbonCast windows")
    ap_.add_argument("--grid", choices=["AECI", "DE"], default="AECI")
    ap_.add_argument("--splits", default="validation", help="comma-separated: train,validation,test (default validation)")
    args = ap_.parse_args()
    ap.configure_grid(args.grid)
    em, runs = ap.load_emissions(), ap.load_weather_runs()
    OUT.mkdir(parents=True, exist_ok=True)
    alignments = SHIFT if args.grid == "AECI" else ("guide",)
    for alignment in alignments:
        ap.WX_SHIFT_DAYS = SHIFT[alignment]                                 # so the window filter matches this reading
        for split in args.splits.split(","):
            a, b = ap.SPLITS[split]
            n = skipped = leaks = 0
            with open(OUT / f"{ap.GRID}_{split}_covariates_{alignment}.jsonl", "w") as f:
                d = a
                while d <= b:
                    if ap.check_window(em, runs, d, split) is None:
                        try:
                            past, future = build_covariates(runs, d, alignment)
                            # Leak test: every block labeled after the one the window text uses is replaced with a marker value.
                            latest = datetime(d.year, d.month, d.day) - timedelta(days=SHIFT[alignment])
                            if build_covariates(ap.LaterRunsScrambled(runs, latest), d, alignment) != (past, future):
                                leaks += 1
                            f.write(json.dumps({"window_id": f"{ap.GRID}-{d.isoformat()}", "name": f"CarbonCast{ap.GRID}", "seed": int(d.strftime("%Y%m%d")),
                                                "alignment": alignment, "variables": list(VARIABLES), "past_covariates": past, "future_covariates": future}) + "\n")
                            n += 1
                        except BlockUnavailable:
                            skipped += 1                                    # an earlier block the history needs is missing or duplicated
                    d += timedelta(days=1)
            print(f"{alignment:<14} {split:<11} windows written {n}, skipped for a missing earlier block {skipped}, leak-test failures {leaks}")
    ap.WX_SHIFT_DAYS = 0


if __name__ == "__main__":
    main()
