import pandas as pd


def impute_missing_values(frame: pd.DataFrame) -> pd.DataFrame:
    """Impute numeric columns with medians and categorical columns with modes."""
    result = frame.copy()
    for column in result.columns:
        if result[column].isna().all():
            raise ValueError(f"Column {column!r} contains no usable values.")
        if pd.api.types.is_numeric_dtype(result[column]):
            result[column] = result[column].fillna(result[column].median())
        else:
            mode = result[column].mode(dropna=True)
            if not mode.empty:
                result[column] = result[column].fillna(mode.iloc[0])
    return result
