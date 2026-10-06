# Hydrological Training Data

Store authorized historical river, rainfall, reservoir and discharge observations used for model development here. Record provider, station/location identifiers, units, observation interval, timezone, quality flags and licensing.

Live telemetry should be collected by a backend service and stored in the application database, not copied into this folder on every refresh. The current flood model expects its documented feature columns, so hydrological observations require an explicit feature-engineering step before training. No sample data is included.
