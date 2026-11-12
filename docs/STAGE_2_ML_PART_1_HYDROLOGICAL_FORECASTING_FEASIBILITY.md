# Stage 2 ML Part 1: Hydrological Forecasting Feasibility

- **Status:** NOT_READY
- **Profiled at (UTC):** 2026-10-28T12:15:58+00:00
- **Script:** `D:\MajorProject\disaster-management-system\ml\preprocessing\profile_hydrological_forecasting_feasibility.py`

Read-only dataset profiling and prediction-feasibility review. This is not a trained or validated water-level forecast and is not a validated flood prediction.

## Dataset profiles

### godavari

- **File:** `D:\MajorProject\disaster-management-system\ml\datasets\hydrological\raw\godavari_water_level_2021_2025.csv`
- **Rows / audit station identities:** 1055737 / 66
- **Observed timestamps:** 2021-01-01T00:00:00 to 2025-12-29T19:00:00
- **Timezone representation:** timezone-naive only; no timezone inferred
- **Sampling intervals:** 848676 exactly 60 minutes; 128070 shorter; 78803 longer
- **Missing water levels:** 10894
- **Water-level range:** -673.0 to 2583.0 (header declares metres; not verified)
- **Negative values flagged:** 5630
- **Exact duplicates:** 0
- **Repeated station/timestamp rows beyond first:** 122; conflicting rows: 18
- **Missing station identity rows:** 0; **malformed CSV rows:** 0
- **Common intervals (minutes):** `[{"minutes": 60, "count": 848676}, {"minutes": 30, "count": 124793}, {"minutes": 120, "count": 37655}, {"minutes": 180, "count": 11287}, {"minutes": 240, "count": 5269}]`
- **Minimum/maximum source rows:** 942909 / 883229
- **Largest observed station gap:** Kosagumda (Bhaskel) 2021-07-20T04:00:00 to 2024-07-22T23:00:00 (26371.0 hours)

| Column | Inferred lexical kind | Missing |
|---|---|---:|
| `SlNo` | integer-like numeric text | 0 |
| `Station` | text | 0 |
| `Agency` | text | 0 |
| `State LGD Code` | integer-like numeric text | 0 |
| `State` | text | 0 |
| `District LGD Code` | integer-like numeric text | 0 |
| `District` | text | 0 |
| `Tehsil` | text | 65089 |
| `Block` | text | 849967 |
| `Village` | text | 849967 |
| `River` | text | 0 |
| `Basin` | text | 0 |
| `Tributary` | text | 313933 |
| `Subtributary` | text | 549080 |
| `SubSubtributary` | text | 864677 |
| `Local River` | text | 0 |
| `Latitude` | numeric text | 0 |
| `Longitude` | numeric text | 0 |
| `Is_DischargeDataAvailable` | text | 0 |
| `RL_of_zeroGauge` | numeric text | 0 |
| `MeanSeaLevel` | numeric text | 0 |
| `Data Acquisition Time` | timestamp text (timezone representation reported separately) | 0 |
| `River Water Level Telemetry Hourly (meter)` | numeric text | 10894 |

### krishna

- **File:** `D:\MajorProject\disaster-management-system\ml\datasets\hydrological\raw\krishna_water_level_2021_2025.csv`
- **Rows / audit station identities:** 451445 / 30
- **Observed timestamps:** 2021-01-01T00:00:00 to 2025-12-30T05:00:00
- **Timezone representation:** timezone-naive only; no timezone inferred
- **Sampling intervals:** 368289 exactly 60 minutes; 46143 shorter; 36940 longer
- **Missing water levels:** 611
- **Water-level range:** -990.33 to 1602.237 (header declares metres; not verified)
- **Negative values flagged:** 9311
- **Exact duplicates:** 0
- **Repeated station/timestamp rows beyond first:** 43; conflicting rows: 4
- **Missing station identity rows:** 0; **malformed CSV rows:** 0
- **Common intervals (minutes):** `[{"minutes": 60, "count": 368289}, {"minutes": 30, "count": 44927}, {"minutes": 120, "count": 16306}, {"minutes": 180, "count": 5320}, {"minutes": 240, "count": 2724}]`
- **Minimum/maximum source rows:** 318148 / 49767
- **Largest observed station gap:** Shimoga 2021-11-03T08:00:00 to 2023-12-18T06:00:00 (18598.0 hours)

| Column | Inferred lexical kind | Missing |
|---|---|---:|
| `SlNo` | integer-like numeric text | 0 |
| `Station` | text | 0 |
| `Agency` | text | 0 |
| `State LGD Code` | integer-like numeric text | 0 |
| `State` | text | 0 |
| `District LGD Code` | integer-like numeric text | 0 |
| `District` | text | 0 |
| `Tehsil` | text | 0 |
| `Block` | unknown (all values missing) | 451445 |
| `Village` | unknown (all values missing) | 451445 |
| `River` | text | 8593 |
| `Basin` | text | 0 |
| `Tributary` | text | 117888 |
| `Subtributary` | text | 361375 |
| `SubSubtributary` | unknown (all values missing) | 451445 |
| `Local River` | text | 8593 |
| `Latitude` | numeric text | 0 |
| `Longitude` | numeric text | 0 |
| `Is_DischargeDataAvailable` | text | 0 |
| `RL_of_zeroGauge` | numeric text | 0 |
| `MeanSeaLevel` | numeric text | 0 |
| `Data Acquisition Time` | timestamp text (timezone representation reported separately) | 0 |
| `River Water Level Telemetry Hourly (meter)` | numeric text | 611 |

## Target feasibility

**NOT_JUSTIFIED** — For a provider-identified gauge, predict the valid measured water level at issue time + 60 minutes using only information available at issue time.

- Data Acquisition Time semantics and timezone remain unresolved; naive timestamps cannot safely define an issue instant or future horizon.
- Observed intervals include both shorter and longer than 60 minutes, so the next row is not reliably a one-hour-ahead target; interpolation/resampling would invent measurements.
- Stable physical gauge IDs, duplicate/revision rules, units, sign, datum, QC, and negative/extreme-value semantics remain unresolved.
- Observation coverage includes missing levels and large station-specific gaps; no provider coverage or operating-period evidence supports complete windows.

## Rainfall/discharge joins

The existing processed snapshot is a separate collection product. Its manifest does not establish an authoritative station crosswalk or validated temporal alignment to these historical raw files; its discharge field is entirely missing and rainfall is mostly missing. No join or feature was created.
Existing processed-manifest context: 17957 rows; rainfall missing 17234; discharge missing 17957; `training_suitable=False`.

No join, resampling, imputation, normalization, or feature generation was performed.

## Potential data leakage risks

- Do not random-split this time series: nearby observations and overlapping target windows can leak temporal information across partitions.
- Build future targets and lag/rolling predictors within an accepted stable gauge identity, after sorting by verified observation time; never use future or post-issue data in predictors.
- Do not use source row numbers, SlNo, export order, fetched_at, or fields generated after the prediction issue time as predictors without a documented availability-time review.
- Repeated station/timestamp records and revisions can leak or duplicate samples until provider resolution rules are reviewed.
- Unknown station identity, time semantics, timezone, publication delay, and data revision timing prevent establishing what information would actually have been available at forecast issue time.
- If the same gauges appear in train and test, results measure temporal generalization on known stations, not transfer to unseen stations; report a separate station-held-out evaluation after authoritative crosswalk review.

## Leakage-resistant evaluation proposal

- **Split:** After all prerequisites are accepted, use globally chronological train/validation/test periods (initial proposal 70%/15%/15% by time, with boundaries fixed before evaluation). Assign rows by prediction issue time and purge any target window crossing a split boundary.
- **Embargo:** Apply a temporal purge/embargo at least as long as the forecast horizon plus the maximum predictor lookback; establish exact duration after the feature contract is defined.
- **Station grouping:** Primary temporal evaluation may include the same verified gauges across periods and must be described as known-station generalization. Add a separate station-held-out group evaluation for unseen-station generalization only after station IDs are verified.
- Persistence: latest valid same-gauge observation available strictly before issue time, with the same target-time eligibility rules as the model.
- Seasonal naive only if authoritative cadence and matching historical horizon are established.
- Compare against persistence using MAE and RMSE; report per-station as well as pooled metrics and sample counts. Report metric units only after measurement units are verified.
- Do not use random splits or report a single metric without temporal coverage, missing-target, station composition, and baseline context.

## Interpretation

This feasibility status concerns exploratory continuous water-level forecasting only. It does not establish a validated flood prediction, emergency-warning capability, or hydraulic-modelling readiness.
