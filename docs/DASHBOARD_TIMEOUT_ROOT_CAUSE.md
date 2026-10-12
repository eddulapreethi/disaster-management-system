# Dashboard timeout root cause

## Summary
The dashboard timed out because the backend computed the readiness summary and historical analytics on every request. Both responses are expensive: `get_data_readiness()` repeatedly validates historical datasets, recomputes dataset hashes, and rebuilds the historical analytics summary, while the page also triggers the same work again via a separate `/historical-data/analytics` request.

## Evidence
Baseline timings from the project code before the fix:

- `get_data_readiness(...)`: approximately 22.6s
- `get_historical_analytics(...)`: approximately 4.8s
- Frontend request timeout: 8s (`AbortSignal.timeout(8000)` in `frontend/src/services/api.js`)

The root cause was therefore not a broken weather collector or a generic backend outage. The page was repeatedly doing expensive dataset scans and manifest validation in the same dashboard refresh cycle.

## Fix
A small in-memory cache now keeps the historical analytics result and data readiness result for 30 seconds, keyed to the relevant dataset, manifest, and model fingerprints. Expensive work is recomputed only when those files change. The dashboard also avoids overlapping in-flight requests.
