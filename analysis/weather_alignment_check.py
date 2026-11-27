"""Is the weather file's timestamp the hour being forecast?

Compares each weather block's forecast with what the grid actually generated (wind power, and solar where
the grid has it), shifting the actual series by different numbers of hours and days. Training period only.

Found on 2026-11-14 for AECI: no relationship on the stamped day, a strong one 24 hours later.
The day-to-day change in the wind forecast against the day-to-day change in wind generation: -0.03 on the same
day, +0.72 one day later.

Usage (from the repo root):
  python3 analysis/weather_alignment_check.py data/raw/CarbonCast/data/AECI/AECI_direct_emissions.csv data/raw/CarbonCast/data/AECI/AECI_weather_forecast.csv "UTC time" datetime 2019-01-22 2021-09-30 forecast_avg_wind_speed_wMean:wind
Arguments: emissions file, weather file, emissions time column, weather time column, first and last training
day, then weather_column:generation_column pairs. Needs numpy.
"""
# Timing check for any grid: compare the weather run's forecast with what the grid actually generated,
# shifting the actual series by different numbers of hours. Training period only.
import csv, sys
from datetime import datetime, timedelta
import numpy as np
em_path, wx_path, em_tcol, wx_tcol, first, last = sys.argv[1:7]
pairs = [p.split(":") for p in sys.argv[7:]]               # weather_column:generation_column
F = "%Y-%m-%d %H:%M:%S"
P = lambda s: datetime.strptime(s[:19], F)
em = {P(r[em_tcol]): r for r in csv.DictReader(open(em_path))}
w = list(csv.DictReader(open(wx_path)))
runs = [w[i:i+96] for i in range(0, len(w), 96)]
assert all(P(r[0][wx_tcol]).hour == 0 for r in runs)
runs = [r for r in runs if first <= r[0][wx_tcol][:10] <= last]
print(f"runs in the training period: {len(runs)}")
lags = list(range(-24, 49, 6))
for wcol, gcol in pairs:
    def corr_at(lag, lo=0, hi=96, anomaly=False):
        a, b = [], []
        for r in runs:
            for k in range(lo, hi):
                t0 = P(r[k][wx_tcol]); t = t0 + timedelta(hours=lag)
                if t in em and em[t][gcol] not in ("", "nan"):
                    a.append(float(r[k][wcol])); b.append(float(em[t][gcol]))
        return np.corrcoef(a, b)[0, 1]
    print(f"\n{wcol.replace('forecast_avg_','').replace('_wMean','')} forecast vs actual '{gcol}' generation, by hours added to the weather timestamp:")
    print("             " + "  ".join(f"{l:+4d}" for l in lags))
    for name, lo, hi in (("rows  0-23 ", 0, 24), ("rows 24-47 ", 24, 48), ("rows 48-71 ", 48, 72), ("rows 72-95 ", 72, 96)):
        cs = [corr_at(l, lo, hi) for l in lags]
        print(f"{name}  " + "  ".join(f"{c:+.2f}" for c in cs) + f"   best {lags[int(np.argmax(cs))]:+d} h")
    # Day level, on day-to-day CHANGES, which removes the season: does a rise in the forecast go with a rise in output the same day?
    by_day_fc, by_day_act = {}, {}
    for r in runs:
        d0 = P(r[0][wx_tcol])
        for d in range(3):                                   # forecast days starting 06:00, as in the dataset text
            st = d0 + timedelta(hours=6 + 24 * d)
            by_day_fc[(d0, d)] = np.mean([float(r[6 + 24 * d + k][wcol]) for k in range(24)])
    def act(st):
        v = [float(em[st + timedelta(hours=k)][gcol]) for k in range(24) if st + timedelta(hours=k) in em]
        return np.mean(v) if len(v) == 24 else np.nan
    out = []
    for shift in (-2, -1, 0, 1, 2):
        a, b = [], []
        for (d0, d), fc in by_day_fc.items():
            if d == 0: continue
            st = d0 + timedelta(hours=6 + 24 * d)
            x = fc - by_day_fc[(d0, d - 1)]                  # change in the forecast from one forecast day to the next, same run
            y = act(st + timedelta(days=shift)) - act(st + timedelta(days=shift - 1))
            if not np.isnan(y): a.append(x); b.append(y)
        out.append(np.corrcoef(a, b)[0, 1])
    print("day-to-day change in forecast vs change in actual output, actual shifted by days:  " + "  ".join(f"{s:+d}d {c:+.2f}" for s, c in zip((-2, -1, 0, 1, 2), out)))
