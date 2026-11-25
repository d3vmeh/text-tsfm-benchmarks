# text-tsfm-benchmarks

Forecasting datasets for testing whether text helps a time-series model forecast better. The first dataset is built from [CarbonCast](https://github.com/carbonfirst/CarbonCast): hourly carbon intensity of electricity for two grids, AECI (United States) and DE (Germany). IoBT is planned and not built yet.

This repo holds the code that builds the datasets and the built AECI dataset. The code that runs models on it is in a separate repo, `text-tsfm-eval`.

## Contents

- [What one record is](#what-one-record-is)
- [The dataset at a glance](#the-dataset-at-a-glance)
- [Load it in Python](#load-it-in-python)
- [How a window is built](#how-a-window-is-built)
- [How the text is made](#how-the-text-is-made)
- [Which days are left out](#which-days-are-left-out)
- [How the build guards against mistakes](#how-the-build-guards-against-mistakes)
- [Two readings of the weather file](#two-readings-of-the-weather-file)
- [Rebuild from the raw files](#rebuild-from-the-raw-files)
- [What is in each folder](#what-is-in-each-folder)
- [Build and evaluate DE](#build-and-evaluate-de)
- [Sources](#sources)

## What one record is

Each record is one forecasting question, called a window.

```
        504 past hours (21 days)            forecast start        72 hours to forecast (3 days)
|------------------------------------------|  06:00 UTC  |------------------------------|
                      |-- fuel mix: last 168 hours --|    |-- weather forecast: 3 days --|
```

A model is given the past values and, optionally, a short text. It must forecast the next 72 hourly values. The text has two parts:

- **Fuel mix:** how the grid generated its electricity over the past week.
- **Weather forecast:** wind, solar, temperature and rain for the three days being forecast.

Here is the first AECI training window, with the long lists shortened:

| Field | Content |
|---|---|
| `background` | "This is the hourly direct carbon intensity of electricity in the AECI grid region, in gCO2eq/kWh. AECI generation over the 168 hours before forecast start: coal 72.6%, natural gas 22.9%, wind 4.5%." |
| `scenario` | "The same-day 00:00 UTC weather run predicts the following for three days starting at 06:00 UTC. Jan 22: mean wind 4.9 m/s, daylight solar 216.8 W/m², -3.7 to 0.7 °C, rain yes. Jan 23: …" |
| `past_time` | 504 hourly values, 2019-01-01 06:00 to 2019-01-22 05:00 UTC |
| `future_time` | 72 hourly values, 2019-01-22 06:00 to 2019-01-25 05:00 UTC. **These are the answers.** |

Records use the 17 fields of the [Context is Key](https://huggingface.co/datasets/ServiceNow/context-is-key) (CiK) benchmark, so code written for CiK can read them. `future_time` holds the true values. Show a model only its timestamps, and keep the values for scoring.

The same window is worked out by hand, row by row, in [examples/aeci_window_2019-01-22.md](examples/aeci_window_2019-01-22.md).

## The dataset at a glance

One window per day. Every window starts at 06:00 UTC.

| Grid | Split | Forecast starts | Windows | File |
|---|---|---|---:|---|
| AECI | train | 2019-01-22 to 2021-09-30 | 983 | `outputs/cik_format/AECI_train.jsonl` |
| AECI | validation | 2021-10-01 to 2021-12-28 | 89 | `outputs/cik_format/AECI_validation.jsonl` |
| AECI | test | 2022-01-01 to 2022-12-30 | 360 | `outputs/cik_format/AECI_test.jsonl` |
| DE | train | 2020-01-22 to 2021-04-30 | 465 | built locally, see [Build and evaluate DE](#build-and-evaluate-de) |
| DE | validation | 2021-05-01 to 2021-06-27 | 58 | built locally |
| DE | test | 2021-07-01 to 2021-12-28 | 179 | built locally |

The AECI files are in this repo. A second copy of AECI, with the weather read one day later, is in `outputs/cik_format_wx1d/` (983, 89 and 361 windows). See [Two readings of the weather file](#two-readings-of-the-weather-file).

Use validation for every experiment. Keep test for the final result.

## Load it in Python

No packages are needed.

```python
import json

with open("outputs/cik_format/AECI_validation.jsonl") as f:
    records = [json.loads(line) for line in f]

r = records[0]
print(r["background"])     # what the series is, and the fuel mix of the past week
print(r["scenario"])       # the weather forecast for the three days to predict

past = json.loads(r["past_time"])["carbon_intensity"]       # {timestamp: value}, 504 entries
future = json.loads(r["future_time"])["carbon_intensity"]   # {timestamp: answer}, 72 entries

timestamps_to_forecast = list(future)    # give these to the model
answers = list(future.values())          # keep these for scoring
```

## How a window is built

All of this is in [scripts/aeci_pilot.py](scripts/aeci_pilot.py). There is no randomness and no model in the build: the same raw files always give the same dataset. A step-by-step guide to the code is in [docs/CODE_GUIDE.md](docs/CODE_GUIDE.md).

1. **Load the two raw files.** One has the hourly carbon intensity and the generation by fuel. The other has the weather forecast, as one block of 96 hourly rows per day.
2. **Go through every day in the split's date range.** The day is called the issue day. Its forecast starts at 06:00 UTC.
3. **Check the day against the filters.** A day that fails is left out, with the reason recorded.
4. **Take the numbers.** The 504 hours before the forecast start are the past values. The 72 hours from the forecast start onward are the answers.
5. **Write the text** from the past week's generation and the day's weather forecast block.
6. **Leak-test the window.** See [How the build guards against mistakes](#how-the-build-guards-against-mistakes).
7. **Convert to the CiK format** with [scripts/to_cik_format.py](scripts/to_cik_format.py).

The window sizes (504 and 72 hours), the 06:00 UTC start, the split dates and the filters come from the project guide.

## How the text is made

The text is filled into a fixed sentence by code. Every number in it can be traced to rows of the raw files.

**Fuel mix.** Add up each source's generation over the 168 hours before the forecast start. Report each source's share of the total, largest first, for sources with at least 2%, up to five sources.

**Weather.** Take the weather block for the issue day. For each of the three forecast days (06:00 to 05:00 the next morning), report:

| Number | How it is computed |
|---|---|
| Mean wind | Average of the 24 hourly wind speeds, in m/s |
| Daylight solar | Average solar radiation over the hours above 1 W/m², so night hours are not counted |
| Temperature range | Lowest and highest of the 24 hourly temperatures, converted from Kelvin to °C |
| Rain | "yes" if any hour forecasts precipitation above zero |

The weather values are forecasts that were made before the forecast start. They are not the weather that was later observed.

## Which days are left out

A day is left out if, across its 504 past hours and 72 answer hours:

- any hour is missing,
- any carbon intensity is zero, negative or not a number,
- 24 or more hours in a row are exactly equal, which means a stuck reading,

or if its weather block is missing, appears twice, is incomplete, or is all zeros.

For AECI the emissions data passes every check. Five test days are left out because of the weather file:

| Issue day | Reason |
|---|---|
| 2022-04-06, 2022-06-14 | The weather block for this day appears twice |
| 2022-04-07, 2022-06-15 | The weather block for this day is missing |
| 2022-12-31 | The weather block is all zeros |

The full list for each grid, with counts, is written to `outputs/pilot/<GRID>_file_check.json`.

One thing to know: the last two AECI training windows (2021-09-29 and 2021-09-30) have answers that run past the first validation forecast start. They are kept because the guide's date ranges include them. Leave them out when fitting a model that will be scored on validation.

## How the build guards against mistakes

- **Leak test, on every window.** A forecast may only use information that existed at the forecast start. To check this, the build makes each window a second time from data in which everything from the forecast start onward is replaced by a marker value. If the model inputs differ between the two, the window used future data and the build stops with an error. AECI: 1,432 windows tested, 0 failures. DE: 702 tested, 0 failures.
- **Inputs and answers are written to separate files** (`*_model_inputs.jsonl` and `*_scoring_only.jsonl`), so a model run cannot read the answers by accident. The CiK files combine them, as CiK does.
- **A hand-built example.** [examples/](examples/) holds windows worked out by hand from the raw files. The build must reproduce them exactly.
- **Pinned sources.** [SOURCE_LOG.md](SOURCE_LOG.md) records the commit and checksum of every raw file. Raw files are never edited.

## Two readings of the weather file

The weather file gives each row a timestamp. The project guide reads that timestamp as the hour the row forecasts. A comparison with the wind power AECI actually generated suggests each row describes the weather 24 hours after its timestamp. The cause is not known, so both readings are built:

| Copy | How the weather file is read | Block used for issue day D | Folder |
|---|---|---|---|
| Default | As the guide says | The block that starts at D 00:00 | `outputs/cik_format/` |
| `one_day_later` | Each row is 24 hours later than its timestamp | The block that starts at D-1 00:00 | `outputs/cik_format_wx1d/` |

Only the weather sentence differs between the two copies. The past values, the answers and the fuel-mix sentence are the same. Which reading the dataset should use is an open decision.

## Rebuild from the raw files

The raw files are not in this repo. [SOURCE_LOG.md](SOURCE_LOG.md) gives the exact commands to download them and the checksums to confirm them. Then, from the repo root, with Python 3.10 or later and no extra packages:

```bash
python3 scripts/aeci_pilot.py                                    # AECI windows, default reading
python3 scripts/aeci_pilot.py --weather-alignment one_day_later  # AECI windows, second reading
python3 scripts/to_cik_format.py                                 # CiK files, default reading
python3 scripts/to_cik_format.py --variant wx1d                  # CiK files, second reading
python3 scripts/aeci_covariates.py                               # optional: hourly weather as numbers
```

The AECI build takes a few seconds. It prints the counts for each split and the leak-test result. The rebuilt files in `outputs/cik_format/` match the ones in this repo byte for byte.

## What is in each folder

| Path | What it holds | In git? |
|---|---|---|
| [scripts/aeci_pilot.py](scripts/aeci_pilot.py) | Builds the windows for a grid. The name is historical: it builds everything, not only a pilot. | Yes |
| [scripts/de_pilot.py](scripts/de_pilot.py) | Runs the same build with DE's settings. | Yes |
| [scripts/to_cik_format.py](scripts/to_cik_format.py) | Converts the windows to CiK records. | Yes |
| [scripts/aeci_covariates.py](scripts/aeci_covariates.py) | Writes the weather forecast hour by hour, for models that take numeric inputs. | Yes |
| [docs/CODE_GUIDE.md](docs/CODE_GUIDE.md) | A walk through the code, function by function. | Yes |
| [SOURCE_LOG.md](SOURCE_LOG.md) | Where every raw file came from, with commits, checksums and column meanings. | Yes |
| [examples/](examples/) | Windows built by hand, with the raw file rows they come from. | Yes |
| `outputs/cik_format/` | **The AECI dataset**, default reading, one file per split. | Yes |
| `outputs/cik_format_wx1d/` | The AECI dataset, `one_day_later` reading. | Yes |
| `outputs/pilot/`, `outputs/pilot_wx1d/` | Five sample windows per grid and the file check. | Yes |
| `outputs/full/`, `outputs/full_wx1d/` | Every window as separate inputs and answers files, plus the build report. | No, rebuilt by the scripts |
| `outputs/covariates/` | Hourly weather series for each window. | No, rebuilt by the scripts |
| `data/raw/` | The raw downloads. Never edited. | No |

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

The DE text is worded a little differently from the AECI text: it gives each forecast day's start and end hour and lists more fuel sources. Both are made by the same function.

## Sources

- **Raw data:** [CarbonCast](https://github.com/carbonfirst/CarbonCast), Apache-2.0. Maji, Shenoy and Sitaraman, "CarbonCast: multi-day forecasting of grid carbon intensity", BuildSys 2022. Per its README, generation comes from the EIA hourly grid monitor and weather from the GFS forecast archive.
- **Record format:** [Context is Key](https://huggingface.co/datasets/ServiceNow/context-is-key).
- **Commits and checksums:** [SOURCE_LOG.md](SOURCE_LOG.md).
