"""AECI: whole-file check, five pilot windows, and the full set of windows.

Reads the two raw AECI files (never modifies them) and writes:
  outputs/pilot/AECI_file_check.json     counts of kept and rejected issue days, with reasons
  outputs/pilot/AECI_model_inputs.jsonl  what a forecaster may see, one window per line (five pilot windows)
  outputs/pilot/AECI_scoring_only.jsonl  the hidden answers and masks, for the evaluator only
  outputs/full/AECI_<split>_model_inputs.jsonl   every kept window in the split
  outputs/full/AECI_<split>_scoring_only.jsonl   its hidden answers
  outputs/full/AECI_window_summary.jsonl         one line of numbers per window
  outputs/full/AECI_build_report.json            counts, baselines by split, leak-test result

Run from the repo root:  python3 scripts/aeci_pilot.py
Rules follow the CarbonCast and IoBT Project Guide, Dataset A.
"""
import csv, json, math
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/CarbonCast/data/AECI"
OUT = ROOT / "outputs/pilot"
FULL = ROOT / "outputs/full"
SENTINEL = "-99999.0"  # stands in for "data from the future" in the leak test
GRID = "AECI"
FMT = "%Y-%m-%d %H:%M:%S"
HIST, HORIZON, MIX_HOURS, RUN_ROWS = 504, 72, 168, 96
SPLITS = OrderedDict([  # issue-day ranges from the guide
    ("train", (date(2019, 1, 22), date(2021, 9, 30))),
    ("validation", (date(2021, 10, 1), date(2021, 12, 28))),
    ("test", (date(2022, 1, 1), date(2022, 12, 31))),
])
PILOT_DAYS = ["2019-01-22", "2019-07-16", "2020-04-08", "2020-10-21", "2021-08-03"]
FUELS = [("coal", "coal"), ("nat_gas", "natural gas"), ("wind", "wind")]  # CSV column, name used in text
WX = {"wind": "forecast_avg_wind_speed_wMean", "temp": "forecast_avg_temperature_wMean",
      "dew": "forecast_avg_dewpoint_wMean", "solar": "forecast_avg_dswrf_wMean", "precip": "forecast_avg_precipitation_wMean"}
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load_emissions():
    """Return {hour: row dict}. The unnamed index column is ignored."""
    em = {}
    with open(RAW / f"{GRID}_direct_emissions.csv") as f:
        for r in csv.DictReader(f):
            t = datetime.strptime(r["UTC time"], FMT)
            assert t not in em, f"duplicate hour {t}"
            em[t] = r
    return em


def load_weather_runs():
    """Group the weather file into runs. A new run starts wherever time does not advance by one hour.
    Returns {issue day: [run, ...]} so that a day that appears twice keeps both copies."""
    runs, cur, prev = {}, [], None
    with open(RAW / f"{GRID}_weather_forecast.csv") as f:
        for r in csv.DictReader(f):
            t = datetime.strptime(r["datetime"], FMT)
            if prev is not None and t - prev != timedelta(hours=1):
                runs.setdefault(cur[0][0], []).append(cur); cur = []
            cur.append((t, r)); prev = t
    runs.setdefault(cur[0][0], []).append(cur)
    return runs


def num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def weather_problem(runs, day):
    """Return a reject reason for the run issued at 00:00 UTC on `day`, or None if it is usable."""
    copies = runs.get(datetime(day.year, day.month, day.day))
    if not copies:
        return "weather run missing"
    if len(copies) > 1:
        return "weather run day appears twice"
    run = copies[0]
    if len(run) != RUN_ROWS:
        return "weather run incomplete"
    vals = [num(r[c]) for _, r in run for c in WX.values()]
    if any(v is None for v in vals):
        return "weather run has invalid numbers"
    if all(v == 0 for v in vals):
        return "weather run all zeros"
    return None


def check_window(em, runs, day, split):
    """Apply the guide's filters to one issue day. Returns a reject reason or None."""
    start = datetime(day.year, day.month, day.day, 6)
    hours = [start + timedelta(hours=k) for k in range(-HIST, HORIZON)]
    if any(h not in em for h in hours):
        return "missing hours"
    ci = [num(em[h]["carbon_intensity"]) for h in hours]
    if any(v is None for v in ci):
        return "invalid carbon intensity"
    if any(v <= 0 for v in ci):
        return "nonpositive carbon intensity"
    longest = run_len = 1
    for a, b in zip(ci, ci[1:]):
        run_len = run_len + 1 if a == b else 1
        longest = max(longest, run_len)
    if longest >= 24:
        return "24 or more exactly constant hours"
    return weather_problem(runs, day)


def overlaps_next_split(day, split):
    """True if this window's answers run into the next split's first forecast start.
    This rule is NOT in the guide. It matches the DE pilot and is reported separately."""
    names = list(SPLITS)
    i = names.index(split)
    if i + 1 == len(names):
        return False
    nxt = SPLITS[names[i + 1]][0]
    last_answer = datetime(day.year, day.month, day.day, 6) + timedelta(hours=HORIZON - 1)
    return last_answer >= datetime(nxt.year, nxt.month, nxt.day, 6)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_window(em, runs, day, window_id):
    start = datetime(day.year, day.month, day.day, 6)
    past_h = [start + timedelta(hours=k) for k in range(-HIST, 0)]
    fut_h = [start + timedelta(hours=k) for k in range(HORIZON)]
    past = [float(em[h]["carbon_intensity"]) for h in past_h]
    fut = [float(em[h]["carbon_intensity"]) for h in fut_h]
    # Fuel mix: last 168 hours, negatives count as zero, up to five sources with at least 2%.
    sums = {col: sum(max(float(em[h][col]), 0.0) for h in past_h[-MIX_HOURS:]) for col, _ in FUELS}
    total = sum(sums.values())
    shares = sorted(((100 * sums[col] / total, name) for col, name in FUELS), reverse=True)
    mix = ", ".join(f"{name} {s:.1f}%" for s, name in [x for x in shares if x[0] >= 2][:5])
    # Weather: only the run issued at 00:00 UTC on the forecast day.
    issue = datetime(day.year, day.month, day.day)
    first_hour = runs[issue][0][0][0]
    assert first_hour == issue, f"run for {day} starts at {first_hour}"
    run = {t: r for t, r in runs[issue][0]}
    parts, days = [], []
    for d in range(3):
        rows = [run[start + timedelta(hours=24 * d + k)] for k in range(24)]
        wind = sum(float(r[WX["wind"]]) for r in rows) / 24
        sol = [float(r[WX["solar"]]) for r in rows if float(r[WX["solar"]]) > 1]
        solar = sum(sol) / len(sol) if sol else 0.0
        temps = [float(r[WX["temp"]]) - 273.15 for r in rows]
        rain = any(float(r[WX["precip"]]) > 0 for r in rows)
        label = (start + timedelta(days=d))
        parts.append(f"{MON[label.month - 1]} {label.day:02d}: mean wind {wind:.1f} m/s, daylight solar {solar:.1f} W/m², "
                     f"{min(temps):.1f} to {max(temps):.1f} °C, rain {'yes' if rain else 'no'}.")
        days.append({"mean_wind": wind, "daylight_solar": solar, "solar_hours": len(sol), "temp_min_c": min(temps), "temp_max_c": max(temps), "rain": rain})
    context = (f"{GRID} generation over the 168 hours before forecast start: {mix}. The same-day 00:00 UTC weather run predicts "
               f"the following for three days starting at 06:00 UTC. " + " ".join(parts))
    last = past[-1]
    daily = [past[-24 + (k % 24)] for k in range(HORIZON)]
    inputs = {"window_id": window_id, "forecast_start": iso(start), "past_timestamps": [iso(h) for h in past_h],
              "past_target": past, "context": context, "future_timestamps": [iso(h) for h in fut_h]}
    scoring = {"window_id": window_id, "forecast_start": iso(start), "future_timestamps": [iso(h) for h in fut_h],
               "future_target": fut, "target_mask": [True] * HORIZON}
    summary = {"window_id": window_id, "issue_day": day.isoformat(), "last_value": last, "fuel_sums_mwh": sums, "weather_days": days,
               "mae_last_value": sum(abs(x - last) for x in fut) / HORIZON, "mae_daily_repeat": sum(abs(x - y) for x, y in zip(fut, daily)) / HORIZON}
    return inputs, scoring, summary


class FutureScrambledEmissions:
    """Looks like the emissions table, but every row at or after `start` holds the sentinel."""
    def __init__(self, em, start):
        self.em, self.start = em, start
    def __getitem__(self, t):
        r = self.em[t]
        if t < self.start:
            return r
        return {k: (v if k in ("", "UTC time") else SENTINEL) for k, v in r.items()}


class LaterRunsScrambled:
    """Looks like the weather runs, but every run issued after `issue` holds the sentinel."""
    def __init__(self, runs, issue):
        self.runs, self.issue = runs, issue
    def __getitem__(self, d):
        copies = self.runs[d]
        if d <= self.issue:
            return copies
        return [[(t, {k: (v if k == "datetime" else SENTINEL) for k, v in r.items()}) for t, r in run] for run in copies]


def build_full(em, runs, kept_by_split):
    """Build every kept window, one set of files per split, and leak-test each one."""
    FULL.mkdir(parents=True, exist_ok=True)
    report = {"grid": GRID, "window_id_format": f"{GRID}-<issue day>", "splits": {}, "leak_test": {"windows_tested": 0, "failures": []}}
    with open(FULL / f"{GRID}_window_summary.jsonl", "w") as fsum:
        for split, days in kept_by_split.items():
            n = 0; mae_last = 0.0; mae_daily = 0.0
            with open(FULL / f"{GRID}_{split}_model_inputs.jsonl", "w") as fi, open(FULL / f"{GRID}_{split}_scoring_only.jsonl", "w") as fs:
                for day in days:
                    wid = f"{GRID}-{day.isoformat()}"
                    inputs, scoring, summary = build_window(em, runs, day, wid)
                    # Leak test: replace everything from the forecast start onward, rebuild, compare.
                    start = datetime(day.year, day.month, day.day, 6)
                    i2, s2, _ = build_window(FutureScrambledEmissions(em, start), LaterRunsScrambled(runs, datetime(day.year, day.month, day.day)), day, wid)
                    report["leak_test"]["windows_tested"] += 1
                    if i2 != inputs or s2["future_target"] == scoring["future_target"]:
                        report["leak_test"]["failures"].append(wid)
                    summary["split"] = split
                    fi.write(json.dumps(inputs) + "\n"); fs.write(json.dumps(scoring) + "\n"); fsum.write(json.dumps(summary) + "\n")
                    n += 1; mae_last += summary["mae_last_value"]; mae_daily += summary["mae_daily_repeat"]
            report["splits"][split] = {"windows": n, "first_issue_day": days[0].isoformat(), "last_issue_day": days[-1].isoformat(),
                                       "mae_last_value": mae_last / n, "mae_daily_repeat": mae_daily / n}
    (FULL / f"{GRID}_build_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    em, runs = load_emissions(), load_weather_runs()
    hours = sorted(em)
    file_facts = {
        "emissions_rows": len(em), "emissions_first": iso(hours[0]), "emissions_last": iso(hours[-1]),
        "emissions_missing_hours": sum(1 for a, b in zip(hours, hours[1:]) if b - a != timedelta(hours=1)),
        "emissions_nonpositive": sum(1 for h in hours if float(em[h]["carbon_intensity"]) <= 0),
        "weather_rows": sum(len(r) for c in runs.values() for r in c), "weather_runs": sum(len(c) for c in runs.values()),
        "weather_run_days_twice": sorted(d.date().isoformat() for d, c in runs.items() if len(c) > 1),
        "weather_runs_all_zero": sorted(d.date().isoformat() for d, c in runs.items() for r in c if all(num(x[k]) == 0 for _, x in r for k in WX.values())),
    }
    report = {"grid": GRID, "file_facts": file_facts, "splits": {}}
    kept_by_split = OrderedDict()
    for split, (a, b) in SPLITS.items():
        kept, reasons, rejected, overlap = 0, Counter(), [], []
        kept_by_split[split] = []
        d = a
        while d <= b:
            why = check_window(em, runs, d, split)
            if why:
                reasons[why] += 1; rejected.append({"issue_day": d.isoformat(), "reason": why})
            else:
                kept += 1
                kept_by_split[split].append(d)
                if overlaps_next_split(d, split):
                    overlap.append(d.isoformat())
            d += timedelta(days=1)
        report["splits"][split] = {"issue_days": (b - a).days + 1, "kept_by_guide_rules": kept, "rejected": rejected,
                                   "reject_reasons": dict(reasons), "answers_overlap_next_split": overlap,
                                   "kept_if_overlap_also_excluded": kept - len(overlap)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{GRID}_file_check.json").write_text(json.dumps(report, indent=2) + "\n")
    summaries = []
    with open(OUT / f"{GRID}_model_inputs.jsonl", "w") as fi, open(OUT / f"{GRID}_scoring_only.jsonl", "w") as fs:
        for n, ds in enumerate(PILOT_DAYS, 1):
            day = date.fromisoformat(ds)
            split = next(s for s, (a, b) in SPLITS.items() if a <= day <= b)
            assert check_window(em, runs, day, split) is None, f"{ds} fails the filters"
            inputs, scoring, summary = build_window(em, runs, day, f"{GRID}-{n:02d}")
            summary["split"] = split
            fi.write(json.dumps(inputs) + "\n"); fs.write(json.dumps(scoring) + "\n"); summaries.append(summary)
    (OUT / f"{GRID}_pilot_summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(file_facts, indent=1))
    for s, v in report["splits"].items():
        print(f"{s}: {v['issue_days']} issue days, {v['kept_by_guide_rules']} kept by guide rules, rejected {v['reject_reasons']}, "
              f"overlap {v['answers_overlap_next_split']}, kept if overlap excluded {v['kept_if_overlap_also_excluded']}")
        for r in v["rejected"]:
            print("   ", r["issue_day"], r["reason"])
    for s in summaries:
        print(s["window_id"], s["issue_day"], f"last {s['last_value']} MAE {s['mae_last_value']:.2f} daily {s['mae_daily_repeat']:.2f}")
    full = build_full(em, runs, kept_by_split)
    for split, v in full["splits"].items():
        print(f"full {split}: {v['windows']} windows, {v['first_issue_day']} to {v['last_issue_day']}, "
              f"MAE last-value {v['mae_last_value']:.2f}, MAE daily-repeat {v['mae_daily_repeat']:.2f}")
    lt = full["leak_test"]
    print(f"leak test: {lt['windows_tested']} windows tested, {len(lt['failures'])} failures")


if __name__ == "__main__":
    main()
