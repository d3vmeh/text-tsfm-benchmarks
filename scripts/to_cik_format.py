"""Convert CarbonCast windows to the Context is Key (CiK) record format.

The build script writes each window as two lines in two files: what a model may see, and the hidden
answers. CiK keeps a whole forecasting question in one record with 17 fields. This script joins the two
and fills those fields, so code written for the CiK benchmark can read this dataset unchanged.

Where each part of a window goes:
  context text, fuel-mix sentence   -> background  (after a one-line description of the series)
  context text, weather sentence    -> scenario
  past timestamps and values        -> past_time
  future timestamps and answers     -> future_time  (the answers are in the record; see the note below)
  nothing                           -> constraints  (empty: this dataset states no constraints)

Reads the files written by scripts/aeci_pilot.py and writes:
  outputs/cik_format/AECI_<split>.jsonl          every window in the split, one CiK-style record per line
  outputs/pilot/AECI_pilot_cik_format.jsonl      the five pilot windows in the same format

Run from the repo root, after aeci_pilot.py:  python3 scripts/to_cik_format.py
For the one_day_later weather build:          python3 scripts/to_cik_format.py --variant wx1d
(reads outputs/full_wx1d and outputs/pilot_wx1d, writes outputs/cik_format_wx1d)
For the DE guide build after de_pilot.py:      python3 scripts/to_cik_format.py --grid DE

The 17 fields, their order and their types follow the CiK dataset
(https://huggingface.co/datasets/ServiceNow/context-is-key), as built by
notebooks/create_hf_dataset.ipynb in the CiK code. Unlike the two-file layout, a CiK record holds the
hidden answers too, inside future_time. Whoever runs a model must show it only the timestamps.
"""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL, PILOT, OUT = ROOT / "outputs/full", ROOT / "outputs/pilot", ROOT / "outputs/cik_format"
GRID = "AECI"
SPLITS = ["train", "validation", "test"]
SERIES_COLUMN = "carbon_intensity"
# CiK context-source codes: c_i intemporal, c_h historical, c_cov covariate, c_f future.
CONTEXT_SOURCES = ["c_i", "c_h", "c_cov", "c_f"]
SKILLS = ["forecasting", "natural language processing"]  # CiK's default skills
# The words that begin the weather sentence in each build. They mark where the context text is cut in two:
# everything before is the fuel-mix sentence (background), everything from here on is the weather (scenario).
SCENARIO_MARKS = ("The same-day 00:00 UTC weather run", "The weather forecast available at forecast start",
                  "Weather forecast issued ")


def read_jsonl(path):
    """Read a file with one JSON record per line into a list."""
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def series_json(timestamps, values):
    """Same text layout as pandas DataFrame.to_json(date_format="iso"): {"column": {"timestamp": value}}."""
    stamps = [t.replace("Z", ".000") for t in timestamps]
    return json.dumps({SERIES_COLUMN: dict(zip(stamps, values))}, separators=(",", ":"))


def metric_scaling(train_scoring):
    """CiK's rule: 1 / (mean over reference instances of max(answer) - min(answer)).
    The reference instances here are the training windows, so no validation or test answer is used."""
    widths = [max(r["future_target"]) - min(r["future_target"]) for r in train_scoring]
    return 1 / (sum(widths) / len(widths))


def to_cik(inputs, scoring, scaling, grid=GRID):
    """Join one window's model inputs and hidden answers into one CiK record (a dict with 17 fields).
    `scaling` is the number from metric_scaling(); it is the same for every record of a grid."""
    assert inputs["window_id"] == scoring["window_id"] and inputs["future_timestamps"] == scoring["future_timestamps"]
    assert all(scoring["target_mask"]), "CiK has no mask field, so every answer must be observed"
    marker = next((mark for mark in SCENARIO_MARKS if mark in inputs["context"]), None)
    if marker is None:
        raise ValueError(f"Missing weather section for {inputs['window_id']}")
    cut = inputs["context"].index(marker)
    fuel_mix, weather = inputs["context"][:cut].strip(), inputs["context"][cut:].strip()
    return {
        "name": f"CarbonCast{grid}",
        "seed": int(inputs["forecast_start"][:10].replace("-", "")),  # the issue day, as YYYYMMDD
        "weight": "1",
        "context_sources": CONTEXT_SOURCES,
        "skills": SKILLS,
        "background": (f"This is the hourly direct carbon intensity of electricity in the {grid} grid region, "
                       f"in gCO2eq/kWh. {fuel_mix}"),
        "scenario": weather,
        "constraints": "",
        "seasonal_period": 24,
        "past_time": series_json(inputs["past_timestamps"], inputs["past_target"]),
        "future_time": series_json(scoring["future_timestamps"], scoring["future_target"]),
        "metric_scaling": scaling,
        "region_of_interest": [],
        "constraint_min": None,   # no constraint (CiK's own code uses -inf, shown as null in its dataset viewer)
        "constraint_max": None,
        "constraint_variable_max_index": [],
        "constraint_variable_max_values": [],
    }


def main():
    global FULL, PILOT, OUT
    ap = argparse.ArgumentParser(description="Convert CarbonCast windows to Context is Key style records")
    ap.add_argument("--grid", choices=["AECI", "DE"], default=GRID)
    ap.add_argument("--variant", default="", help="wx1d for the one_day_later weather build")
    args = ap.parse_args()
    if args.variant:
        FULL, PILOT, OUT = ROOT / f"outputs/full_{args.variant}", ROOT / f"outputs/pilot_{args.variant}", ROOT / f"outputs/cik_format_{args.variant}"
    grid = args.grid
    # The scaling number comes from training answers only.
    train_scoring = read_jsonl(FULL / f"{grid}_train_scoring_only.jsonl")
    if grid == "DE":
        validation = read_jsonl(FULL / f"{grid}_validation_scoring_only.jsonl")
        first_validation = min(row["forecast_start"] for row in validation)
        train_scoring = [row for row in train_scoring if row["future_timestamps"][-1] < first_validation]
    scaling = metric_scaling(train_scoring)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"metric_scaling = {scaling!r} (mean training answer range {1 / scaling:.2f} gCO2eq/kWh)")
    # One output file per split, then the five pilot windows.
    for split in SPLITS:
        ins = read_jsonl(FULL / f"{grid}_{split}_model_inputs.jsonl")
        sco = read_jsonl(FULL / f"{grid}_{split}_scoring_only.jsonl")
        with open(OUT / f"{grid}_{split}.jsonl", "w") as f:
            for a, b in zip(ins, sco, strict=True):
                f.write(json.dumps(to_cik(a, b, scaling, grid)) + "\n")
        print(f"{split}: {len(ins)} records -> {OUT.name}/{grid}_{split}.jsonl")
    ins = read_jsonl(PILOT / f"{grid}_model_inputs.jsonl")
    sco = read_jsonl(PILOT / f"{grid}_scoring_only.jsonl")
    with open(PILOT / f"{grid}_pilot_cik_format.jsonl", "w") as f:
        for a, b in zip(ins, sco, strict=True):
            f.write(json.dumps(to_cik(a, b, scaling, grid)) + "\n")
    print(f"pilot: {len(ins)} records -> {PILOT.name}/{grid}_pilot_cik_format.jsonl")


if __name__ == "__main__":
    main()
