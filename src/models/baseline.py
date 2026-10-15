"""Heuristic baseline regressor using historical segment median travel times."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin


class HistoricalMedianRegressor(BaseEstimator, RegressorMixin):
    """Heuristic benchmark regressor that predicts the historical median travel time per segment.

    Provides the fundamental non-learning baseline against which ML ensembles are compared.
    """

    def __init__(self, segment_col: str = "segment_id", fallback_value: float = 7.0):
        self.segment_col = segment_col
        self.fallback_value = fallback_value
        self.segment_medians_: dict[str, float] = {}
        self.global_median_: float = fallback_value

    def fit(self, X: pd.DataFrame, y: np.ndarray | pd.Series) -> HistoricalMedianRegressor:
        """Fit baseline by computing the median travel time per segment from training data."""
        y_arr = np.asarray(y, dtype=np.float64)
        if len(y_arr) == 0:
            return self

        self.global_median_ = float(np.median(y_arr))

        if isinstance(X, pd.DataFrame) and self.segment_col in X.columns:
            seg_series = X[self.segment_col].astype(str)
            for seg in seg_series.unique():
                mask = (seg_series == seg).to_numpy()
                if np.any(mask):
                    self.segment_medians_[seg] = float(np.median(y_arr[mask]))
        else:
            self.segment_medians_ = {}

        return self

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict median travel time for each sample."""
        n_samples = len(X)
        preds = np.full(n_samples, self.global_median_, dtype=np.float64)

        if isinstance(X, pd.DataFrame) and self.segment_col in X.columns:
            seg_series = X[self.segment_col].astype(str).tolist()
            for i, seg in enumerate(seg_series):
                if seg in self.segment_medians_:
                    preds[i] = self.segment_medians_[seg]

        return preds
