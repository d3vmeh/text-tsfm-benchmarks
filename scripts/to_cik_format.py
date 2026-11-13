"""Convert the AECI windows to the Context is Key (CiK) record format.

Reads the files written by scripts/aeci_pilot.py and writes:
  outputs/cik_format/AECI_<split>.jsonl          every window in the split, one CiK-style record per line
  outputs/pilot/AECI_pilot_cik_format.jsonl      the five pilot windows in the same format

Run from the repo root, after aeci_pilot.py:  python3 scripts/to_cik_format.py

The 17 fields, their order and their types follow the CiK dataset
(https://huggingface.co/datasets/ServiceNow/context-is-key), as built by
notebooks/create_hf_dataset.ipynb in the CiK code. Unlike the two-file layout, a CiK record holds the
hidden answers too, inside future_time. Whoever runs a model must show it only the timestamps.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL, PILOT, OUT = ROOT / "outputs/full", ROOT / "outputs/pilot", ROOT / "outputs/cik_format"
GRID = "AECI"
SPLITS = ["train", "validation", "test"]
TASK_NAME = f"CarbonCast{GRID}"
SERIES_COLUMN = "carbon_intensity"
# CiK context-source codes: c_i intemporal, c_h historical, c_cov covariate, c_f future.
CONTEXT_SOURCES = ["c_i", "c_h", "c_cov", "c_f"]
SKILLS = ["forecasting", "natural language processing"]  # CiK's default skills
DESCRIPTION = f"This is the hourly direct carbon intensity of electricity in the {GRID} grid region, in gCO2eq/kWh."
SCENARIO_MARK = "The same-day 00:00 UTC weather run"


def read_jsonl(path):
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


def to_cik(inputs, scoring, scaling):
    assert inputs["window_id"] == scoring["window_id"] and inputs["future_timestamps"] == scoring["future_timestamps"]
    assert all(scoring["target_mask"]), "CiK has no mask field, so every answer must be observed"
    cut = inputs["context"].index(SCENARIO_MARK)
    fuel_mix, weather = inputs["context"][:cut].strip(), inputs["context"][cut:].strip()
    return {
        "name": TASK_NAME,
        "seed": int(inputs["forecast_start"][:10].replace("-", "")),  # the issue day, as YYYYMMDD
        "weight": "1",
        "context_sources": CONTEXT_SOURCES,
        "skills": SKILLS,
        "background": f"{DESCRIPTION} {fuel_mix}",
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
    scaling = metric_scaling(read_jsonl(FULL / f"{GRID}_train_scoring_only.jsonl"))
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"metric_scaling = {scaling!r} (mean training answer range {1 / scaling:.2f} gCO2eq/kWh)")
    for split in SPLITS:
        ins = read_jsonl(FULL / f"{GRID}_{split}_model_inputs.jsonl"); sco = read_jsonl(FULL / f"{GRID}_{split}_scoring_only.jsonl")
        with open(OUT / f"{GRID}_{split}.jsonl", "w") as f:
            for a, b in zip(ins, sco):
                f.write(json.dumps(to_cik(a, b, scaling)) + "\n")
        print(f"{split}: {len(ins)} records -> {OUT.name}/{GRID}_{split}.jsonl")
    ins = read_jsonl(PILOT / f"{GRID}_model_inputs.jsonl"); sco = read_jsonl(PILOT / f"{GRID}_scoring_only.jsonl")
    with open(PILOT / f"{GRID}_pilot_cik_format.jsonl", "w") as f:
        for a, b in zip(ins, sco):
            f.write(json.dumps(to_cik(a, b, scaling)) + "\n")
    print(f"pilot: {len(ins)} records -> pilot/{GRID}_pilot_cik_format.jsonl")


if __name__ == "__main__":
    main()
