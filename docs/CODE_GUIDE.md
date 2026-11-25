# Code guide

A walk through the build code, in the order it runs. Read the [README](../README.md) first for what a window is.

There are four scripts in `scripts/`. One does the building. The other three are small.

| Script | Job | Reads | Writes |
|---|---|---|---|
| `aeci_pilot.py` | Builds the windows for a grid | The two raw CSV files | `outputs/pilot/`, `outputs/full/` |
| `de_pilot.py` | Runs `aeci_pilot.py` with DE's settings | The same | The same, with `DE_` file names |
| `to_cik_format.py` | Converts windows to Context is Key records | `outputs/full/`, `outputs/pilot/` | `outputs/cik_format/` |
| `aeci_covariates.py` | Writes the weather forecast hour by hour | The raw weather file | `outputs/covariates/` |

The code uses only the Python standard library.

## Words used in the code

| Word | Meaning |
|---|---|
| issue day, `day`, `D` | The calendar day a forecast is made. Its forecast starts at 06:00 UTC. |
| `start` | The forecast start: 06:00 UTC on the issue day. |
| window | One forecasting question: past values, text, and answers. |
| run, block | One day's weather forecast: 96 hourly rows that start at 00:00 UTC. The code says "run"; the README says "block". They are the same thing. |
| `em` | The emissions table in memory. See below. |
| `runs` | The weather blocks in memory. See below. |
| split | `train`, `validation` or `test`. |
| alignment | Which reading of the weather timestamps is in use: `guide` or `one_day_later`. |

## The two tables everything works on

`aeci_pilot.py` reads each raw file once and keeps it in memory.

**`em`**, from `load_emissions()`, maps each hour to its row of the emissions file:

```python
em[datetime(2019, 1, 22, 5)]
# {"UTC time": "2019-01-22 05:00:00", "carbon_intensity": "604.09", "coal": "...", "nat_gas": "...", "wind": "..."}
```

Values are still text here, exactly as in the CSV. They are turned into numbers where they are used.

**`runs`**, from `load_weather_runs()`, maps the first timestamp of each weather block to a list of blocks. A block is a list of 96 `(timestamp, row)` pairs:

```python
runs[datetime(2019, 1, 22, 0)]
# [ [ (datetime(2019, 1, 22, 0), {...weather row...}), (datetime(2019, 1, 22, 1), {...}), ... 96 pairs ] ]
```

The outer list normally holds one block. It holds two when the same day appears twice in the file, which is how a duplicated day is detected and rejected.

## `aeci_pilot.py`, step by step

The file has a settings section at the top, then four numbered steps, then `main()`, which runs the steps in order.

### Settings

Everything that defines the dataset is a named constant at the top of the file:

| Constant | Value | Meaning |
|---|---|---|
| `HIST` | 504 | Past hours shown to the model |
| `HORIZON` | 72 | Hours to forecast |
| `MIX_HOURS` | 168 | Hours the fuel-mix sentence looks back |
| `RUN_ROWS` | 96 | Rows in a complete weather block |
| `SPLITS` | date ranges | First and last issue day of each split |
| `PILOT_DAYS` | five dates | The pilot windows |
| `FUELS` | list | Generation columns, and the names used for them in the text |
| `WX` | dict | Weather columns |
| `WX_SHIFT_DAYS` | 0 or 1 | 0 for the guide's reading of the weather file, 1 for `one_day_later` |

`configure_grid("DE")` replaces the file locations, split dates, pilot days and fuel list with DE's. For AECI it changes nothing.

### Step 1. Load the raw files

- `load_emissions()` reads the emissions CSV into `em`. It stops if an hour appears twice.
- `load_weather_runs()` reads the weather CSV into `runs`. It starts a new block wherever the time does not advance by exactly one hour.

### Step 2. Decide which issue days are usable

- `check_window(em, runs, day, split)` returns a reject reason as text, or `None` if the day is kept. It looks at the day's 576 hours (504 past and 72 answers) and rejects for a missing hour, a carbon intensity that is not a positive number, or 24 or more exactly equal hours in a row. Then it calls `weather_problem`.
- `weather_problem(runs, day)` checks the day's weather block: present, present once, 96 rows, all valid numbers, and not all zeros.
- `num(x)` turns a CSV cell into a number, or `None` if it is not a usable number.
- `overlaps_next_split(day, split)` reports whether a window's answers run into the next split. It is only reported, never used to reject, because the guide does not ask for it.

### Step 3. Build one window

`build_window(em, runs, day, window_id)` is the centre of the code. It returns three dicts.

| Returned | Holds | Who may see it |
|---|---|---|
| `inputs` | Past timestamps and values, the context text, the timestamps to forecast | A model |
| `scoring` | The answers for those timestamps | The evaluator only |
| `summary` | The numbers behind the text, and the error of two simple baselines | Anyone checking the build |

Inside, in order:

1. **Past values and answers.** It lists the 504 hours before `start` and the 72 hours from `start`, and reads their carbon intensity from `em`.
2. **Fuel-mix sentence.** It sums each fuel's generation over the last 168 past hours, counts negative values as zero, turns the sums into shares, and keeps up to five sources with at least 2%.
3. **Weather sentences.** It takes the weather block for the day (`weather_block_start(day)` says which one) and, for each of the three forecast days, takes 24 rows and computes mean wind, mean solar over hours above 1 W/m², the lowest and highest temperature in °C, and whether any rain is forecast.
4. **Context text.** It joins the fuel-mix sentence and the three weather sentences.
5. **Baselines.** It scores two simple forecasts against the answers, for reference: repeating the last value, and repeating the last 24 hours.

The AECI and DE sentences are worded differently. Where the code says `if GRID == "DE":`, the first branch is DE's wording and the other is AECI's.

### Step 4. The leak test, and building every window

`build_full(em, runs, kept_by_split)` builds every kept window and writes the files. For each window it calls `build_window` twice:

1. once with the real data, and
2. once with two look-alike objects that hide the future.

| Look-alike | Behaves like | What it changes |
|---|---|---|
| `FutureScrambledEmissions(em, start)` | `em` | Every row at or after the forecast start returns the marker value `-99999.0` |
| `LaterRunsScrambled(runs, issue)` | `runs` | Every weather block later than the one this window uses returns the marker value |

A window fails if its `inputs` differ between the two builds, because that means an input was computed from future data. It also fails if its answers are the same in both builds, because that means the scrambling did not reach the answers and the test proved nothing. `main()` stops with an error if any window fails.

### `main()`

1. Reads the command-line option and sets the alignment.
2. Loads the two tables and records basic facts about the raw files.
3. Checks every issue day of every split and writes `<GRID>_file_check.json`.
4. Builds the five pilot windows.
5. Calls `build_full` and prints the counts and the leak-test result.

## `to_cik_format.py`

Turns the two-file layout into one record per window, in the 17-field format of the Context is Key dataset.

- `to_cik(inputs, scoring, scaling, grid)` builds one record. It cuts the context text in two at the start of the weather sentence: the first part goes to `background`, the second to `scenario`.
- `series_json(timestamps, values)` writes a series the way CiK stores it: `{"carbon_intensity": {"timestamp": value, ...}}` as text.
- `metric_scaling(train_scoring)` computes the scaling number CiK's score uses: one divided by the average range (highest minus lowest) of the answers. It uses training windows only.
- `main()` writes one file per split, then the pilot windows.

Fields this dataset does not use (`constraints`, `region_of_interest` and the `constraint_*` fields) are left empty, as CiK does for tasks without them.

## `aeci_covariates.py`

Some models take numbers, not text. This script gives them the same weather forecast, hour by hour, for the 504 past hours and the 72 future hours of each window.

- `build_covariates(runs, day, alignment)` returns two dicts, `past` and `future`, each mapping a variable name to a list of hourly values.
- Future hours come from the same block the window's text uses.
- Past hours each come from the block of their own date, which is never later than that block.
- It has its own leak test, with the same `LaterRunsScrambled` look-alike.

## Where to change things

| To change | Edit |
|---|---|
| The window sizes | `HIST`, `HORIZON` in `aeci_pilot.py` |
| The split dates | `SPLITS` in `aeci_pilot.py`, or `configure_grid` for DE |
| The wording of the text | `build_window` in `aeci_pilot.py`. Also update `SCENARIO_MARKS` in `to_cik_format.py` if the weather sentence starts differently. |
| What the weather sentence reports | The `for d in range(3)` loop in `build_window` |
| A filter | `check_window` or `weather_problem` |
| A new grid | `configure_grid`, plus a three-line script like `de_pilot.py` |

After any change, run the build again and read the last lines it prints. The leak-test line must say `0 failures`.
