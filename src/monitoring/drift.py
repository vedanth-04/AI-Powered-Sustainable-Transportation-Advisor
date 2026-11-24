"""Drift statistics with thresholds calibrated on the in-control reference.

Small monitoring windows make textbook thresholds (for example PSI > 0.25) unreliable:
a window of 20 requests can exceed them by chance. Every alert threshold here is
therefore calibrated by resampling the reference at the same sample size, so a
threshold means "this would happen by chance in fewer than 1% of in-control windows".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
from scipy import stats

SMOOTHING = 0.5  # Jeffreys-style pseudo-count so empty bins do not produce infinite PSI.


def _as_float(values: Iterable) -> np.ndarray:
    array = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype=float)
    return array[np.isfinite(array)]


def _as_str(values: Iterable) -> np.ndarray:
    return np.asarray([str(value) for value in values], dtype=object)


def numeric_bin_edges(reference: Sequence[float], bins: int = 5) -> np.ndarray:
    """Interior quantile edges from the reference; duplicate edges are merged."""
    ref = _as_float(reference)
    if ref.size == 0:
        raise ValueError("The reference sample is empty.")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)[1:-1]))
    return edges


def _proportions(counts: np.ndarray) -> np.ndarray:
    smoothed = counts.astype(float) + SMOOTHING
    return smoothed / smoothed.sum()


def psi_from_counts(reference_counts: np.ndarray, current_counts: np.ndarray) -> float:
    """Population Stability Index between two count vectors over the same bins."""
    ref, cur = _proportions(np.asarray(reference_counts)), _proportions(np.asarray(current_counts))
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def numeric_counts(values: Sequence[float], edges: np.ndarray) -> np.ndarray:
    data = _as_float(values)
    return np.bincount(np.searchsorted(edges, data, side="right"), minlength=len(edges) + 1)


def categorical_counts(values: Sequence, categories: Sequence[str]) -> np.ndarray:
    index = {category: position for position, category in enumerate(categories)}
    counts = np.zeros(len(categories), dtype=int)
    for value in _as_str(values):
        counts[index[value]] += 1
    return counts


def psi(reference: Sequence, current: Sequence, *, kind: str, bins: int = 5) -> float:
    """PSI for a numeric or categorical feature (bins come from the reference only)."""
    if kind == "numeric":
        edges = numeric_bin_edges(reference, bins)
        return psi_from_counts(numeric_counts(reference, edges), numeric_counts(current, edges))
    if kind == "categorical":
        categories = sorted(set(_as_str(reference)) | set(_as_str(current)))
        return psi_from_counts(categorical_counts(reference, categories), categorical_counts(current, categories))
    raise ValueError(f"Unknown feature kind: {kind}")


def block_indices(n_reference: int, size: int, block_length: int, rng: np.random.Generator) -> np.ndarray:
    """Circular block bootstrap indices: keeps runs of consecutive (correlated) observations together."""
    if block_length <= 1:
        return rng.integers(0, n_reference, size)
    starts = rng.integers(0, n_reference, int(np.ceil(size / block_length)))
    return ((starts[:, None] + np.arange(block_length)[None, :]) % n_reference).ravel()[:size]


def bootstrap_null(
    reference: Sequence, sample_size: int, statistic, *, iterations: int = 1000, seed: int = 42,
    block_length: int = 1,
) -> np.ndarray:
    """Distribution of `statistic(sample)` for in-control samples drawn from the reference.

    With block_length > 1 the reference must be in time order; blocks preserve the way
    errors cluster when consecutive buses share the same congestion.
    """
    ref = np.asarray(list(reference), dtype=object)
    if ref.size == 0 or sample_size < 1:
        raise ValueError("Bootstrap needs a non-empty reference and a positive sample size.")
    rng = np.random.default_rng(seed)
    return np.asarray([statistic(ref[block_indices(ref.size, sample_size, block_length, rng)])
                       for _ in range(iterations)])


@dataclass(frozen=True)
class DriftResult:
    statistic: float
    warn_threshold: float
    alert_threshold: float
    null_exceedance: float  # Share of in-control resamples at least this extreme (an empirical p-value).
    status: str  # OK, WARN or ALERT
    ks_pvalue: float | None = None


def classify(value: float, warn: float, alert: float) -> str:
    if value > alert:
        return "ALERT"
    if value > warn:
        return "WARN"
    return "OK"


def calibrated_psi(
    reference: Sequence, current: Sequence, *, kind: str, bins: int = 5, iterations: int = 1000,
    warn_quantile: float = 0.95, alert_quantile: float = 0.99, seed: int = 42,
) -> DriftResult:
    """PSI of the current window with thresholds from same-sized reference resamples."""
    current = list(current)
    if kind == "numeric":
        edges = numeric_bin_edges(reference, bins)
        ref_counts = numeric_counts(reference, edges)

        def statistic(sample):
            return psi_from_counts(ref_counts, numeric_counts(sample, edges))
    else:
        categories = sorted(set(_as_str(reference)) | set(_as_str(current)))
        ref_counts = categorical_counts(reference, categories)

        def statistic(sample):
            return psi_from_counts(ref_counts, categorical_counts(sample, categories))

    observed = statistic(np.asarray(current, dtype=object))
    null = bootstrap_null(reference, len(current), statistic, iterations=iterations, seed=seed)
    warn, alert = (float(np.quantile(null, q)) for q in (warn_quantile, alert_quantile))
    ks = None
    if kind == "numeric":
        ks = float(stats.ks_2samp(_as_float(reference), _as_float(current)).pvalue)
    return DriftResult(float(observed), warn, alert, float(np.mean(null >= observed)),
                       classify(observed, warn, alert), ks)


def calibrated_mean_shift(
    reference: Sequence[float], current: Sequence[float], *, iterations: int = 1000,
    warn_quantile: float = 0.95, alert_quantile: float = 0.99, seed: int = 42, block_length: int = 1,
) -> DriftResult:
    """Is the current mean (for example of normalized errors) higher than chance allows?"""
    ref, cur = _as_float(reference), _as_float(current)
    observed = float(cur.mean())
    null = bootstrap_null(ref, cur.size, lambda sample: float(np.mean(sample.astype(float))),
                          iterations=iterations, seed=seed, block_length=block_length)
    warn, alert = (float(np.quantile(null, q)) for q in (warn_quantile, alert_quantile))
    return DriftResult(observed, warn, alert, float(np.mean(null >= observed)), classify(observed, warn, alert))


@dataclass
class Cusum:
    """One-sided CUSUM (Page's test) for an increase in the mean of a monitored signal.

    S_t = max(0, S_{t-1} + x_t - target - slack); an alarm is raised when S_t > threshold.
    With normalized errors the in-control target is 1.0, and slack 0.5 means the detector
    ignores shifts smaller than a 50% error increase.
    """

    target: float
    slack: float
    threshold: float
    value: float = 0.0
    alarm_index: int | None = None
    history: list[float] = field(default_factory=list)

    def update(self, x: float) -> bool:
        self.value = max(0.0, self.value + float(x) - self.target - self.slack)
        self.history.append(self.value)
        if self.alarm_index is None and self.value > self.threshold:
            self.alarm_index = len(self.history) - 1
            return True
        return False


def cusum_path(values: Sequence[float], target: float, slack: float) -> np.ndarray:
    detector = Cusum(target=target, slack=slack, threshold=np.inf)
    for value in values:
        detector.update(value)
    return np.asarray(detector.history)


def calibrate_cusum_threshold(
    reference: Sequence[float], stream_length: int, *, target: float, slack: float,
    false_alarm_rate: float = 0.05, iterations: int = 2000, seed: int = 42, block_length: int = 1,
) -> float:
    """Threshold giving the requested false-alarm rate over an in-control stream of this length.

    `reference` must be in label-arrival order when block_length > 1.
    """
    ref = _as_float(reference)
    if ref.size == 0 or stream_length < 1:
        raise ValueError("Calibration needs reference values and a positive stream length.")
    rng = np.random.default_rng(seed)
    maxima = [cusum_path(ref[block_indices(ref.size, stream_length, block_length, rng)], target, slack).max()
              for _ in range(iterations)]
    return float(np.quantile(maxima, 1.0 - false_alarm_rate))
