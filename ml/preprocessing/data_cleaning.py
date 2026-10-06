import numpy as np
import pandas as pd


def clean_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize non-finite numeric values, remove duplicates and blank rows."""
    cleaned = frame.copy()
    cleaned = cleaned.replace([np.inf, -np.inf], np.nan)
    cleaned = cleaned.drop_duplicates()
    cleaned = cleaned.dropna(how="all")
    if cleaned.empty:
        raise ValueError("Dataset contains no usable rows after cleaning.")
    return cleaned
