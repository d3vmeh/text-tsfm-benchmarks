# text-tsfm-benchmarks

Two forecasting benchmarks, CarbonCast and IoBT, for testing whether text improves a time-series foundation model's forecasts.

AECI and DE are built. The builders check each issue day, separate model inputs from scoring answers, and check for leakage in each retained window. The CiK converter defaults to AECI and accepts `--grid DE`.

- `SOURCE_LOG.md`: where every raw file came from, with commit IDs and checksums.
- `examples/`: hand-built windows. Build code must reproduce these exactly.
- `scripts/`: build code. Run `python3 scripts/aeci_pilot.py` for AECI or `python3 scripts/de_pilot.py` for DE from the repo root.
- `outputs/pilot/`: five pilot windows and the whole-file check.
- `outputs/full/`: every kept window, by split. Not tracked by git, since it can be rebuilt.
- `outputs/cik_format/`: **the full AECI dataset**, as Context is Key style records, one file per split: `AECI_train.jsonl` (983 windows), `AECI_validation.jsonl` (89) and `AECI_test.jsonl` (360). Tracked by git. Each record holds the hidden answers in `future_time`, so a model must be shown only the timestamps. `python3 scripts/to_cik_format.py` rebuilds these files exactly from the build.
- `outputs/pilot_wx1d/`, `outputs/full_wx1d/`, `outputs/cik_format_wx1d/`: a second copy built with `--weather-alignment one_day_later`, where each weather row is read as describing the weather 24 hours after its timestamp. `outputs/cik_format_wx1d/` is tracked by git too (983, 89 and 361 windows). Only the weather sentence differs between the two copies. See the note at the top of `scripts/aeci_pilot.py`. Which reading is right is an open question.
- `outputs/covariates/`: hourly weather series for each window, for models that take numeric covariates. Built by `python3 scripts/aeci_covariates.py`, under both readings of the weather file. Not tracked by git.
- `data/raw/`: raw downloads. Not tracked by git and never edited.

## Build and evaluate DE

Put the two checksummed DE CSVs in `data/raw/CarbonCast-main/data/DE/`. See [the source log](SOURCE_LOG.md#carboncast-main-branch-de). Run from the repo root with Python 3.10 or later.

```bash
python scripts/de_pilot.py
python scripts/to_cik_format.py --grid DE
python scripts/aeci_covariates.py --grid DE --splits validation,test
```

The build retains 465 training, 58 validation, and 179 test windows. The test split excludes December 4, 2021 (duplicate weather run) and December 5, 2021 (missing weather run). See [the first DE example](examples/de_window_2020-01-22.md) and [the whole-file check](outputs/pilot/DE_file_check.json).

For inference, read the `DE_*_model_inputs.jsonl` files under `outputs/full/`. Use the matching `scoring_only` files for evaluation. When reading the CiK export, pass the future timestamps to the model and keep the values in `future_time` for scoring.

| Split | Windows | Last-value MAE | Daily-repeat MAE |
|---|---:|---:|---:|
| Validation | 58 | 78.64 | 68.88 |
| Test | 179 | 75.49 | 70.58 |

MAE is in gCO2e/kWh. The build report in `outputs/full/DE_build_report.json` contains the exact scores. The April 29–30, 2021 training windows share 48 target timestamps with validation. The dataset preserves the guide's split dates. Exclude those two training windows before fitting a model for validation. The DE CiK converter also leaves them out of metric scaling.

DE uses the guide's same-day weather alignment. The numeric covariate builder covers all 58 validation windows and 158 test windows. December 6–26 have usable same-day forecasts but lack a complete set of historical forecasts because of the December 4–5 source issues. For a numeric-wind comparison, score all methods on the same 158 test IDs. The full 179-window test set supports the history-only and text experiments.
