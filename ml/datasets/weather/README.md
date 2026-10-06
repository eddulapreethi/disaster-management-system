# Weather Training Data

Store authorized historical weather data used for model development here, such as time, location, temperature, precipitation, humidity, wind speed and pressure. Live or near-real-time observations must be fetched by a backend data-collection service and stored as application records; they do not belong in this training-data directory.

The current model training pipeline does not ingest raw weather columns directly. Convert and validate them into the model's documented flood features before training, and record source, license, units, timezone, spatial resolution and preprocessing steps. No sample dataset is included.
