# text-tsfm-benchmarks

Two forecasting benchmarks, CarbonCast and IoBT, for testing whether text improves a time-series foundation model's forecasts.

Status: AECI is built. `scripts/aeci_pilot.py` checks every issue day, builds all 1,432 kept windows into `outputs/full/`, and leak-tests each one. `scripts/to_cik_format.py` converts them to the Context is Key record format in `outputs/cik_format/`. DE is not done yet.

- `SOURCE_LOG.md`: where every raw file came from, with commit IDs and checksums.
- `examples/`: hand-built windows. Build code must reproduce these exactly.
- `scripts/`: build code. Run `python3 scripts/aeci_pilot.py` from the repo root.
- `outputs/pilot/`: five pilot windows and the whole-file check.
- `outputs/full/`: every kept window, by split. Not tracked by git, since it can be rebuilt.
- `outputs/cik_format/`: **the full AECI dataset**, as Context is Key style records, one file per split: `AECI_train.jsonl` (983 windows), `AECI_validation.jsonl` (89) and `AECI_test.jsonl` (360). Tracked by git. Each record holds the hidden answers in `future_time`, so a model must be shown only the timestamps. `python3 scripts/to_cik_format.py` rebuilds these files exactly from the build.
- `outputs/pilot_wx1d/`, `outputs/full_wx1d/`, `outputs/cik_format_wx1d/`: a second copy built with `--weather-alignment one_day_later`, where each weather row is read as describing the weather 24 hours after its timestamp. `outputs/cik_format_wx1d/` is tracked by git too (983, 89 and 361 windows). Only the weather sentence differs between the two copies. See the note at the top of `scripts/aeci_pilot.py`. Which reading is right is an open question.
- `outputs/covariates/`: hourly weather series for each window, for models that take numeric covariates. Built by `python3 scripts/aeci_covariates.py`, under both readings of the weather file. Not tracked by git.
- `data/raw/`: raw downloads. Not tracked by git and never edited.
