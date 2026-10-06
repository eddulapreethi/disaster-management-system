from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "ml" / "datasets" / "historical_data" / "processed"


DISASTER_MAPPINGS = {
    "floods.csv": ["Flood", "Glacial lake outburst flood"],
    "storms_cyclones.csv": ["Storm"],
    "landslides.csv": ["Mass movement (wet)", "Mass movement (dry)"],
    "wildfires.csv": ["Wildfire"],
    "earthquakes.csv": ["Earthquake"],
}


def generate_disaster_specific_datasets(cleaned_csv: str | Path | None = None, output_dir: str | Path | None = None) -> dict[str, pd.DataFrame]:
    source = Path(cleaned_csv) if cleaned_csv else PROCESSED_DIR / "emdat_cleaned.csv"
    destination = Path(output_dir) if output_dir else PROCESSED_DIR
    destination.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(source)
    results: dict[str, pd.DataFrame] = {}
    for file_name, disaster_types in DISASTER_MAPPINGS.items():
        subset = frame[frame["disaster_type"].isin(disaster_types)].copy()
        if subset.empty:
            subset = frame.iloc[0:0].copy()
        subset = subset.sort_values(["start_year", "country"], ascending=[True, True]).reset_index(drop=True)
        subset.to_csv(destination / file_name, index=False)
        results[file_name] = subset
    return results


def main() -> None:
    results = generate_disaster_specific_datasets()
    print({name: int(frame.shape[0]) for name, frame in results.items()})


if __name__ == "__main__":
    main()
