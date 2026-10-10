from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ml.preprocessing.feature_engineering import FLOOD_FEATURES
from ml.preprocessing.data_validation import validate_training_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "datasets" / "historical_data" / "processed"
TARGET_COLUMN = "FloodProbability"


def build_integrated_historical_flood_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate an already joined real-data table without deriving proxy values."""
    required_columns = [*FLOOD_FEATURES, TARGET_COLUMN]
    missing_columns = [name for name in required_columns if name not in frame.columns]
    if missing_columns:
        raise ValueError(
            "NOT READY — EM-DAT event records do not contain the verified environmental "
            "features and flood-probability labels required for training. Missing columns: "
            f"{', '.join(missing_columns)}. Join licensed, time/location-aligned observations "
            "and independently defined labels before creating a model dataset."
        )

    validated = frame.loc[:, required_columns].copy()
    for name in required_columns:
        validated[name] = pd.to_numeric(validated[name], errors="raise")
    validate_training_data(validated)
    return validated


def integrate_historical_flood_dataset(
    flood_csv: str | Path | None = None,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Validate and copy a real, pre-joined flood dataset into the model schema."""
    source_path = Path(flood_csv) if flood_csv else PROCESSED_DIR / "floods.csv"
    output = Path(output_path) if output_path else PROCESSED_DIR / "flood_feature_matrix.csv"
    frame = pd.read_csv(source_path)
    validated = build_integrated_historical_flood_features(frame)
    output.parent.mkdir(parents=True, exist_ok=True)
    validated.to_csv(output, index=False)
    return validated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a real, pre-joined flood training dataset; does not infer missing values."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PROCESSED_DIR / "floods.csv",
        help="CSV with the exact real feature schema and FloodProbability labels",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROCESSED_DIR / "flood_feature_matrix.csv",
        help="Output path for a validated copy",
    )
    arguments = parser.parse_args()
    try:
        result = integrate_historical_flood_dataset(arguments.input, arguments.output)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        parser.error(str(error))
    print({"rows": int(result.shape[0]), "columns": int(result.shape[1]), "output": str(arguments.output)})


if __name__ == "__main__":
    main()
