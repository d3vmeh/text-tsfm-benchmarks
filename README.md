# text-tsfm-benchmarks

Two forecasting benchmarks, CarbonCast and IoBT, for testing whether text improves a time-series foundation model's forecasts.

Status: AECI is built. `scripts/aeci_pilot.py` checks every issue day, builds all 1,432 kept windows into `outputs/full/`, and leak-tests each one. `scripts/to_cik_format.py` converts them to the Context is Key record format in `outputs/cik_format/`. DE is not done yet.

- `SOURCE_LOG.md`: where every raw file came from, with commit IDs and checksums.
- `examples/`: hand-built windows. Build code must reproduce these exactly.
- `scripts/`: build code. Run `python3 scripts/aeci_pilot.py` from the repo root.
- `outputs/pilot/`: five pilot windows and the whole-file check.
- `outputs/full/`: every kept window, by split. Not tracked by git, since it can be rebuilt.
- `outputs/cik_format/`: the same windows as Context is Key style records. Not tracked by git. Run `python3 scripts/to_cik_format.py` after the build.
- `data/raw/`: raw downloads. Not tracked by git and never edited.
