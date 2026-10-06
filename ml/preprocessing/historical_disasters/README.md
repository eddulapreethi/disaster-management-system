# Historical EM-DAT preprocessing

This package processes the raw EM-DAT workbook located under the repository at `ml/datasets/historical_disasters/EM-DAT/`.

## Outputs

- `inspect_emdat.py`: reads the raw workbook and writes an inspection summary JSON to `ml/datasets/historical_data/processed/emdat_inspection_report.json`
- `validate_emdat.py`: validates raw-data issues without mutating the source workbook
- `clean_emdat.py`: creates the cleaned master dataset at `ml/datasets/historical_data/processed/emdat_cleaned.csv`
- `filter_disasters.py`: derives disaster-specific datasets in the same processed folder
- `ml/preprocessing/flood_feature_integration.py`: converts the flood subset into the model schema and writes `ml/datasets/historical_data/processed/flood_feature_matrix.csv`

## Example commands

From the project root:

```powershell
python -m ml.preprocessing.historical_disasters.inspect_emdat
python -m ml.preprocessing.historical_disasters.validate_emdat
python -m ml.preprocessing.historical_disasters.clean_emdat
python -m ml.preprocessing.historical_disasters.filter_disasters
```

The modules read the Excel workbook in-place and write processed CSV files only under `ml/datasets/historical_data/processed/`.

To bridge from historical floods into the project’s flood-risk schema, run:

```powershell
python -m ml.preprocessing.flood_feature_integration
```

This produces a 20-feature matrix aligned with `ml/preprocessing/feature_engineering.py` for the flood model, while keeping the raw EM-DAT file unchanged. The mapping combines historical flood impact variables with hydrology, weather, and GIS-relevant context indicators such as rainfall proxy signals, river-basin presence, coastal risk, watershed, and infrastructure severity.

## Mapping used for disaster-specific outputs

- Flood records: `Disaster Type` in `{Flood, Glacial lake outburst flood}`
- Storm/cyclone records: `Disaster Type` = `Storm`
- Landslide records: `Disaster Type` in `{Mass movement (wet), Mass movement (dry)}`
- Wildfire records: `Disaster Type` = `Wildfire`
- Earthquake records: `Disaster Type` = `Earthquake`

The subtype is retained in the derived dataset so that later analysts can distinguish `Flood (General)`, `Flash flood`, `Coastal flood`, and similar events without losing the original EM-DAT classification.
