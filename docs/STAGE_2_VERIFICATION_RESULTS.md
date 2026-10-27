# Stage 2 verification results

**Verification date:** 2026-10-27
**Scope:** supplied EM-DAT extracts, descriptive analytics, dashboard/API country ranking, and historical-data readiness.

## Result

Stage 2 meets its definition of done for the supplied snapshot. All six extracts and manifests validate; the dashboard country ranking now renders the actual API response; year counts use verified start dates and disclose exclusions; missing impacts remain distinct from zero; partial dataset validation results are explicit; and historical descriptive readiness remains independent of hydrology/model readiness.

## Reconciled dashboard claims

| Claim / metric | Verified result |
|---|---|
| Validated hazard extracts | 6 of 6 |
| Source rows across extracts | 8,810 |
| Distinct non-missing EM-DAT event IDs | 8,810 |
| Flood-classified events | 4,291 |
| Event IDs shared between extracts | 0 |
| Exact duplicate rows / repeated IDs within extracts | 0 / 0 |
| Valid coordinate pairs | 1,816 / 8,810 (20.61%) |
| Deaths / affected / damage reports | 6,492 / 7,369 / 3,157 |
| Date-eligible events in corrected yearly series | 8,363 |
| Invalid source chronology rows | 3, retained and flagged |
| Failed source manifests | 0 |

The original event, flood, overlap, coordinate, impact-sum, and per-extract coverage claims reconcile with the actual processed files. The country ranking’s prior display did not: backend `events_by_country` is an array of `{country, count}` objects, but the frontend used `Object.entries()` as if it were a mapping. Each entry therefore supplied the numeric index as a name and an object as the value; object `toLocaleString()` produced `[object Object]`. The UI now renders the object properties directly.

The previous yearly aggregation counted every row by `start_year` (8,810 events, including incomplete dates and source chronology errors). The corrected aggregation uses valid `start_date` values on/before 2026-10-27 and excludes end-before-start records. It contains 8,363 events. 444 start dates are missing, 1 date is future, and 3 end dates precede their starts; the future record is one of those 3. The unique excluded count is therefore 447, not the sum of overlapping reason counts.

Corrected top-ten country ranking: China 635; United States of America 623; Indonesia 381; Philippines 371; India 369; Viet Nam 199; Japan 169; Mexico 159; Afghanistan 152; Brazil 151. Ranking is count descending with stable case-insensitive then source-name tie-breaking.

Full six-file hashes, category counts, all corrected yearly counts, per-extract coordinate/date/impact metrics, source-level chronology anomalies, schema, and units are in [EMDAT_DATA_QUALITY_REPORT.md](./EMDAT_DATA_QUALITY_REPORT.md). Response semantics are in [HISTORICAL_ANALYTICS_API.md](./HISTORICAL_ANALYTICS_API.md).

## Implementation and files changed

- `ml/preprocessing/historical_analytics.py`
  - Added explicit missing/invalid/future date, end-before-start, ID, country, coordinate, and impact quality reporting.
  - Changed yearly grouping to eligible `start_date`; source rows remain intact.
  - Added deterministic country ranking, explicit impact denominators/units, and per-dataset `READY`/`ERROR` results so valid extracts remain visible when others fail.
  - Removed local workspace paths from public dataset inventory; upgraded transformation version to `emdat-historical-analytics-v2`.
- `backend/app/services/historical_data_readiness.py`
  - Preserves partial validated analytics while retaining `NOT_READY` for incomplete source validation and `training_status: NOT_READY`.
  - Exposes dataset/workbook basenames rather than local paths.
- `backend/tests/test_historical_data_readiness.py`, `backend/tests/test_historical_analytics_api.py`, `ml/preprocessing/test_historical_analytics.py`
  - Added coverage for partial validation, API country object arrays, country tie order, chronology/future date exclusion, impact zero/missing/invalid/negative distinctions, cross-extract overlaps, missing IDs, coordinate denominators, and empty/error datasets.
- `frontend/src/components/CountryRanking.js`, `frontend/src/pages/DashboardPage.jsx`, `frontend/tests/historical-analytics.test.js`
  - Renders the backend array of country/count objects, handles malformed/empty data, and shows date, coordinate, impact coverage, validation, and source warnings.
- `ml/datasets/historical_data/analytics/historical_analytics.json`, `ml/datasets/historical_data/analytics/historical_analytics.manifest.json`
  - Regenerated derived analytics artifacts only. The output hash is `8990fdea486b7653328a2100c28b2947851fe1e68aaf6cbfe785aa07d4b43fca`, matching its manifest; version `emdat-historical-analytics-v2`, as-of `2026-10-27`.
- Required Stage 2 docs were added/updated. The previous dataset assessment and ML pipeline report now point at the v2 snapshot.

The API response retains the existing summary keys and adds data-quality fields. It replaces path/manifest path values with basenames. Current frontend consumers do not use those paths.

## Test and build results

| Command | Result |
|---|---|
| `d:/MajorProject/.venv/Scripts/python.exe -m pytest backend/tests -q` | **155 passed, 1 skipped, 28 subtests passed** in 23.83 s |
| `d:/MajorProject/.venv/Scripts/python.exe -m pytest ml/preprocessing/test_historical_analytics.py ml/preprocessing/historical_disasters/test_clean_emdat.py ml/preprocessing/historical_disasters/test_integrated_flood_features.py -q` | **20 passed** in 4.45 s |
| `d:/MajorProject/.venv/Scripts/python.exe -m pytest ml/preprocessing/test_historical_analytics.py backend/tests/test_historical_data_readiness.py backend/tests/test_historical_analytics_api.py -q` | **23 passed** in 2.09 s |
| `npm test -- --test` in `frontend` | **20 passed, 0 failed** |
| `npm run build` in `frontend` | **Succeeded**; Vite transformed 111 modules |
| `d:/MajorProject/.venv/Scripts/python.exe -m ml.preprocessing.historical_analytics` | **Succeeded**; scanned 8,810 rows / 8,810 unique IDs |

The first full backend test collection reported a missing `httpx2` test-client dependency while collecting the GIS API tests. It was installed into the existing virtual environment only (no dependency manifest was changed), after which the full backend suite passed. No test failures remained.

## Preservation, readiness, and limitations

- The original EM-DAT workbook and six source extract CSVs were read-only and their recorded SHA-256 values still validate. Only generated analytics JSON/manifest artifacts were regenerated.
- No AI assistant files, prompts, routes, model behavior, or configuration were edited.
- No flood model was trained, and no inference/readiness guard was changed. A live repository readiness check reports descriptive analytics `READY`, model training `NOT_READY`, and source status `VALIDATED`.
- Stale hydrology is not an input to this analytics pipeline; historical summaries remain available independently.
- EM-DAT access is subject to the supplied academic/research request terms. No redistribution rights are asserted.
- Source completeness is limited: 6,994 rows lack a valid coordinate pair; 444 lack a complete start date; reported impacts are incomplete; and three source date ranges are contradictory. No missing value or source date was repaired or fabricated.
- The source-provided future/inconsistent record `1995-0275-NPL` has a future start and a 1995 end date in the original workbook. It is flagged and excluded only from the year series; the intended correction cannot be verified.

Existing unrelated user work in `README.md`, the Digital Twin pages/components/styles/tests, and `ml/datasets/flood_training/` was present before this task and was preserved. No commit or push was made.

## Next stage

Before attempting supervised prediction, establish a documented local flood target with source-backed event and non-event labels, temporal/spatial alignment rules, verified measurement units, and a validated runtime feature builder. Confirm source access and redistribution rights for every input first. Keep inference blocked until those prerequisites and a reproducible model artifact are independently validated.
