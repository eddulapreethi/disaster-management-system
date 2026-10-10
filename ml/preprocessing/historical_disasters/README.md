# Historical EM-DAT preprocessing

This package processes the raw EM-DAT workbook located under the repository at `ml/datasets/historical_disasters/EM-DAT/`.

## Outputs

- `inspect_emdat.py`: reads the raw workbook and writes an inspection summary JSON to `ml/datasets/historical_data/processed/emdat_inspection_report.json`
- `validate_emdat.py`: validates raw-data issues without mutating the source workbook
- `clean_emdat.py`: creates the cleaned master dataset at `ml/datasets/historical_data/processed/emdat_cleaned.csv`
- `filter_disasters.py`: derives disaster-specific datasets in the same processed folder
- `ml/preprocessing/flood_feature_integration.py`: validates a real, pre-joined flood training dataset before copying it into the model schema. It does not derive features or labels from EM-DAT impacts.

## Example commands

From the project root:

```powershell
python -m ml.preprocessing.historical_disasters.inspect_emdat
python -m ml.preprocessing.historical_disasters.validate_emdat
python -m ml.preprocessing.historical_disasters.clean_emdat
python -m ml.preprocessing.historical_disasters.filter_disasters
```

The modules read the Excel workbook in-place and write processed CSV files only under `ml/datasets/historical_data/processed/`.
Date components that are missing remain missing; a complete end date is not substituted for an unknown event start date.

To validate a real, independently labeled, time/location-aligned dataset with all model features, run:

```powershell
python -m ml.preprocessing.flood_feature_integration --input path\to\verified_flood_training_data.csv
```

The current EM-DAT-derived `floods.csv` does not contain this schema or verified probability labels, so the default command reports `NOT READY` and writes no training matrix. Historical event impact variables must not be repurposed as environmental predictors or flood-probability labels. Use separately sourced observations, documented units and CRS, spatial/temporal matching rules, and a defensible label definition before training. The raw EM-DAT workbook remains unchanged.

## Mapping used for disaster-specific outputs

- Flood records: `Disaster Type` in `{Flood, Glacial lake outburst flood}`
- Storm/cyclone records: `Disaster Type` = `Storm`
- Landslide records: `Disaster Type` in `{Mass movement (wet), Mass movement (dry)}`
- Wildfire records: `Disaster Type` = `Wildfire`
- Earthquake records: `Disaster Type` = `Earthquake`

The subtype is retained in the derived dataset so that later analysts can distinguish `Flood (General)`, `Flash flood`, `Coastal flood`, and similar events without losing the original EM-DAT classification.
