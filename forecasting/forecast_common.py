"""Shared helpers for Section 8: dataset access, features, metrics.

The dataset is the one prepared by 00_prepare_dataset.py:
    data/forecast_dataset.parquet
with one row per (region, CAT hour) and features lag1d, lag2d,
prev_day_mean plus calendar features hour, day_of_week, is_weekend,
day_index and the region key.

MISSING VALUES
    The dataset is complete: no absent region-hours and no missing lag values
    were found in 8.1, so no imputation is applied. The assignment's
    single-missing-reading gaps never produced an empty hour bucket.

PREPROCESSING FITTED ON TRAIN ONLY
    All model configurations share one ColumnTransformer fitted on the usable
    training rows: StandardScaler on the numeric features and OneHotEncoder
    on region. Scikit-learn pipelines are used so the selected configuration
    carries its own fitted preprocessing.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

FEATURES = ["lag1d", "lag2d", "prev_day_mean", "hour", "day_of_week",
            "is_weekend", "day_index"]


def load_dataset(path=None):
    if path is None:
        path = Path(PROJECT_ROOT) / "data" / "forecast_dataset.parquet"
    return pd.read_parquet(path)


def splits(rows):
    train = rows[(rows["split"] == "train")
                 & (rows["hour_start"] >= rows["hour_start"].min())].copy()
    val = rows[rows["split"] == "validation"].copy()
    test = rows[rows["split"] == "test"].copy()
    return train, val, test


def maes(actual, predicted):
    """Column-wise Mean Absolute Error, preserving alignment."""
    return float(np.mean(np.abs(np.asarray(predicted, dtype=float)
                                - np.asarray(actual, dtype=float))))


def rmses(actual, predicted):
    return float(np.sqrt(np.mean(
        (np.asarray(predicted, dtype=float)
         - np.asarray(actual, dtype=float)) ** 2)))


def metrics(actual, predicted):
    return {"MAE": maes(actual, predicted), "RMSE": rmses(actual, predicted)}