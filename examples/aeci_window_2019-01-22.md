# Hand-built window: AECI, forecast start 2019-01-22 06:00 UTC

This is one forecasting question, built by reading rows straight from the raw files. It is the first issue day in the AECI training period. Build code must later reproduce every number here.

Sources are pinned in `SOURCE_LOG.md` (CarbonCast commit `d621c24`). "Line" means the line number in the CSV file, where line 1 is the header.

| Field | Value |
|---|---|
| Window ID | `AECI_2019-01-22T06` (draft naming) |
| Grid | AECI |
| Split | train |
| Forecast start | 2019-01-22 06:00 UTC |
| History | 504 hours, 2019-01-01 06:00 to 2019-01-22 05:00 |
| Horizon | 72 hours, 2019-01-22 06:00 to 2019-01-25 05:00 |

## 1. Past values (model input)

File: `data/AECI/AECI_direct_emissions.csv`, column `carbon_intensity`, lines 8 to 511 (504 rows).

| Line | UTC time | carbon_intensity (gCO2eq/kWh) |
|---|---|---|
| 8 | 2019-01-01 06:00 | 585.73 |
| 9 | 2019-01-01 07:00 | 593.27 |
| 10 | 2019-01-01 08:00 | 596.96 |
| ... | ... | ... |
| 509 | 2019-01-22 03:00 | 587.78 |
| 510 | 2019-01-22 04:00 | 592.09 |
| 511 | 2019-01-22 05:00 | 604.09 |

Checks on these 504 values: no missing hours, lowest 519.80, highest 702.89, no two neighbouring hours exactly equal.

## 2. Allowed text (model input)

### Fuel mix, from the 168 hours before the forecast start

File: `data/AECI/AECI_direct_emissions.csv`, lines 344 to 511 (2019-01-15 06:00 to 2019-01-22 05:00).

| Source | Sum over 168 hours (MWh) | Share |
|---|---|---|
| coal | 369,059 | 72.6% |
| nat_gas | 116,153 | 22.9% |
| wind | 22,839 | 4.5% |
| Total | 508,051 | 100% |

All three sources are at least 2%, so all three are listed.

### Weather, from the run that began 2019-01-22 00:00 UTC

File: `data/AECI/AECI_weather_forecast.csv`. This run is lines 2018 to 2113 (96 rows). The forecast days use lines 2024 to 2095.

| Forecast day | Hours (UTC) | Lines | Mean wind (m/s) | Mean solar, hours above 1 W/m2 | Temperature (C) | Any precipitation above zero |
|---|---|---|---|---|---|---|
| 1 | Jan 22 06:00 to Jan 23 05:00 | 2024 to 2047 | 4.86 | 216.84 W/m2 (12 hours) | -3.66 to 0.68 | yes (24 of 24 hours) |
| 2 | Jan 23 06:00 to Jan 24 05:00 | 2048 to 2071 | 4.95 | 248.21 W/m2 (12 hours) | -10.65 to -0.91 | yes (19 of 24 hours) |
| 3 | Jan 24 06:00 to Jan 25 05:00 | 2072 to 2095 | 3.64 | 234.40 W/m2 (12 hours) | -11.58 to -0.74 | yes (20 of 24 hours) |

Temperature is converted from kelvin by subtracting 273.15.

### The text itself (draft wording)

The guide fixes what the text reports, but not the exact wording or rounding. This wording is a draft.

> Generation mix over the past 168 hours: coal 72.6%, natural gas 22.9%, wind 4.5%. The 00:00 UTC weather run predicts, for the three forecast days: day 1, mean wind 4.9 m/s, mean daytime solar 217 W/m2, temperature -3.7 to 0.7 C, rain yes; day 2, mean wind 5.0 m/s, mean daytime solar 248 W/m2, temperature -10.7 to -0.9 C, rain yes; day 3, mean wind 3.6 m/s, mean daytime solar 234 W/m2, temperature -11.6 to -0.7 C, rain yes.

## 3. Hidden answer (not shown to the model)

File: `data/AECI/AECI_direct_emissions.csv`, column `carbon_intensity`, lines 512 to 583 (72 rows). No future value is missing, so the mask is all "observed".

Day 1, 2019-01-22 06:00 to 2019-01-23 05:00:

    608.14, 615.55, 618.57, 633.65, 642.39, 640.79, 639.19, 638.00, 648.30, 657.72, 668.48, 666.04,
    673.73, 670.00, 662.84, 651.72, 646.61, 653.38, 628.62, 651.51, 648.46, 638.59, 643.28, 646.88

Day 2, 2019-01-23 06:00 to 2019-01-24 05:00:

    633.93, 622.58, 636.49, 637.68, 635.95, 649.57, 647.59, 632.69, 629.84, 633.89, 640.16, 648.40,
    650.33, 648.93, 648.31, 641.98, 647.25, 654.60, 644.52, 631.84, 626.36, 620.83, 617.12, 623.03

Day 3, 2019-01-24 06:00 to 2019-01-25 05:00:

    621.54, 628.77, 615.62, 621.93, 620.39, 622.54, 608.91, 594.93, 593.97, 592.42, 585.50, 572.19,
    575.96, 576.59, 577.44, 576.25, 588.69, 610.57, 619.84, 610.44, 606.72, 609.90, 621.89, 631.82

## 4. Last-value baseline

The last past value is 604.09 (line 511, 2019-01-22 05:00). The baseline predicts 604.09 for all 72 hours.

- First four errors: |608.14 - 604.09| = 4.05, then 11.46, 14.48, 29.56.
- Sum of all 72 absolute errors: 2,200.57.
- MAE = 2,200.57 / 72 = **30.56 gCO2eq/kWh**.

For comparison, the daily-repeat baseline (copy the last 24 past hours three times) gives MAE 33.84 gCO2eq/kWh on this window.

## Notes and open points

- The forecast hour 2019-01-22 06:00 appears in four weather runs (Jan 19, 20, 21 and 22), with wind of 6.66, 6.50, 7.66 and 6.60 m/s. Only the Jan 22 run is used.
- Precipitation is above zero in most hours, so "rain yes" may say little. Across the training period, 2,838 of 2,949 forecast days (96.2%) come out as "rain yes". The precipitation unit isn't confirmed.
- Weather values repeat in 3-hour blocks.
- The window ID format, the text wording and the rounding are drafts.
