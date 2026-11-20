# Source log

Raw files live in `data/raw/` and are never edited. Git doesn't track that folder, so this log is the record of how to get the same files again.

## CarbonCast, US branch

| Field | Value |
|---|---|
| URL | https://github.com/carbonfirst/CarbonCast |
| Branch | `v3.0_real_time_service` |
| Commit | `d621c24452f9c9a50ab6224d0d455a9d1507c643` (committed 2023-09-25) |
| Download date | 2026-11-10 |
| Local path | `data/raw/CarbonCast/` |
| Terms of use | Apache-2.0, per the repo's `LICENSE.md` |
| Requested citation | Maji, Shenoy and Sitaraman, "CarbonCast: multi-day forecasting of grid carbon intensity", BuildSys 2022, pages 198-207. BibTeX is in the repo's `README.md`. |
| Upstream data, per the repo's README | Generation: EIA hourly grid monitor. Weather: GFS forecast archive (https://rda.ucar.edu/datasets/ds084.1/). |

Only part of the repo was downloaded (a sparse checkout), because the full repo is about 4.4 GB. To get the same files:

```bash
git clone --no-checkout --depth 1 --single-branch --branch v3.0_real_time_service --filter=blob:none https://github.com/carbonfirst/CarbonCast.git data/raw/CarbonCast
cd data/raw/CarbonCast
git sparse-checkout set --no-cone '/LICENSE.md' '/README.md' '/data/AECI/AECI_direct_emissions.csv' '/data/AECI/AECI_weather_forecast.csv'
git checkout v3.0_real_time_service
git rev-parse HEAD   # must print the commit above
```

### Files used

| File | Size (bytes) | SHA-256 |
|---|---|---|
| `data/AECI/AECI_direct_emissions.csv` | 1,803,909 | `5bf7b151c92a23289877cad3ec985efb42c657ab6099d4fd20337db2fd078b24` |
| `data/AECI/AECI_weather_forecast.csv` | 14,842,104 | `243c74bd45581777275e959d12e1d2c386f5441792282257b69a3d0f9dabc36a` |

### Column mapping, AECI

`AECI_direct_emissions.csv`: 35,136 hourly rows, 2019-01-01 00:00 to 2023-01-03 23:00 UTC, no missing hours.

| Column | Meaning | Unit | Used as |
|---|---|---|---|
| (unnamed) | Row index, 0 to 35135 | none | Ignored |
| `UTC time` | Hour of the measurement | UTC | Timestamp |
| `carbon_intensity` | Direct carbon intensity | gCO2eq/kWh | Past or future target |
| `coal`, `nat_gas`, `wind` | Generation by source | MWh | Fuel-mix text |

`AECI_weather_forecast.csv`: 140,256 rows, which is 1,461 runs of 96 hourly rows. Every run starts at 00:00 UTC.

| Column | Meaning | Unit | Used as |
|---|---|---|---|
| `datetime` | The hour being forecast, not the issue time | UTC | Groups rows into runs |
| `forecast_avg_wind_speed_wMean` | Wind speed | m/s (per the project guide) | Weather text |
| `forecast_avg_temperature_wMean` | Temperature | K (per the project guide) | Weather text, converted to C |
| `forecast_avg_dewpoint_wMean` | Dew point | K (assumed, values are near the temperature column) | Not used |
| `forecast_avg_dswrf_wMean` | Solar radiation reaching the ground | W/m2 (per the project guide) | Weather text |
| `forecast_avg_precipitation_wMean` | Precipitation | Not confirmed | Weather text, rain yes/no |

### Things found in the weather file

- Run days 2022-04-06 and 2022-06-14 each appear twice. Run days 2022-04-07 and 2022-06-15 are missing.
- The run for 2022-12-31 is all zeros.
- Values repeat in 3-hour blocks within a run.
- The same forecast hour appears in up to four runs, with different values in each.

## CarbonCast, main branch (DE)

| Field | Value |
|---|---|
| URL | https://github.com/carbonfirst/CarbonCast |
| Branch | `main` |
| Commit | `12d6989beb30d2d1a48ea8ef8c0c83745d4dac9d` |
| Download date | 2026-11-14 |
| Local path | `data/raw/CarbonCast-main/` |
| Terms of use and citation | Same as the US branch above |

Sparse checkout of `data/DE/DE_direct_emissions.csv` and `data/DE/DE_weather_forecast.csv`, fetched the same way as the US branch with `--branch main`.

| File | SHA-256 |
|---|---|
| `data/DE/DE_direct_emissions.csv` | `67bbba0161419b9a23d3f79b8f4bffe629263ded822da2b1940e0f8c77d2e0b9` |
| `data/DE/DE_weather_forecast.csv` | `03db383e4351a42fdcb7ae183d4497bf8d8d52bbbaaf837b964d0b914369d369` |

The two DE CSVs used for the window build matched both SHA-256 values above. Place them under `data/raw/CarbonCast-main/data/DE/`.

### Column mapping, DE

| File | Column | Meaning and use |
|---|---|---|
| Emissions | (unnamed) | Exported index, ignored |
| Emissions | `UTC time` | Hour of the measurement, with an explicit `+00:00` offset |
| Emissions | `carbon_intensity` | Direct carbon intensity in gCO2eq/kWh, used as the past and future target |
| Emissions | `biomass`, `coal`, `nat_gas`, `geothermal`, `hydro`, `nuclear`, `oil`, `solar`, `wind`, `unknown` | Hourly generation in MWh, used for historical fuel-mix text |
| Weather | `UTC time` | Forecast valid hour in UTC. Group rows by source order. The guide uses the same-day midnight block. |
| Weather | `forecast_avg_wind_speed_wMean` | Wind speed in m/s |
| Weather | `forecast_avg_temperature_wMean` | Air temperature in K, converted to °C |
| Weather | `forecast_avg_dewpoint_wMean` | Dew-point temperature in K per GFS metadata, unused in the text |
| Weather | `forecast_avg_dswrf_wMean` | Downward shortwave radiation flux in W/m² |
| Weather | `forecast_avg_precipitation_wMean` | Precipitation, used for a positive-value yes/no flag. The exact GFS field and accumulation interval are unconfirmed. |

The DE emissions file contains 17,544 hourly rows from January 1, 2020 through December 31, 2021 UTC. The weather file contains 105,216 rows in 1,096 blocks. December 4, 2021 appears twice, December 5 is missing, and December 31 is all zero. These facts are recorded in `outputs/pilot/DE_file_check.json`.

The upstream sources identified by CarbonCast are [ENTSO-E](https://transparency.entsoe.eu/) for grid data and the [NCEP GFS forecast archive](https://gdex.ucar.edu/datasets/d084001/detailed_metadata/?view=level) for weather. The [CarbonCast weather documentation](https://github.com/carbonfirst/CarbonCast#51-getting-weather-data) describes how the forecasts were collected.

## Not downloaded yet

- Intel Lab data.
- ALFA dataset.
- Context is Key record for the example note.
