"""Model evaluation, regression metrics, and stratified error breakdown module."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score

from src.config import OUTPUTS_DIR

logger = logging.getLogger(__name__)


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Compute standard regression metrics in minutes."""
    y_true_arr = np.asarray(y_true, dtype=np.float64)
    y_pred_arr = np.asarray(y_pred, dtype=np.float64)

    mae = float(mean_absolute_error(y_true_arr, y_pred_arr))
    rmse = float(np.sqrt(mean_squared_error(y_true_arr, y_pred_arr)))
    mape = float(mean_absolute_percentage_error(y_true_arr, y_pred_arr)) * 100.0
    r2 = float(r2_score(y_true_arr, y_pred_arr))

    return {
        "mae_minutes": mae,
        "rmse_minutes": rmse,
        "mape_percent": mape,
        "r2_score": r2,
    }


def compute_stratified_breakdown(
    df_eval: pd.DataFrame,
    group_col: str,
    y_true_col: str = "y_true",
    y_pred_col: str = "y_pred",
) -> pd.DataFrame:
    """Compute error metrics grouped by a specific operational slice (segment, direction, rush hour)."""
    rows = []
    for val, grp in df_eval.groupby(group_col):
        metrics = compute_regression_metrics(grp[y_true_col].to_numpy(), grp[y_pred_col].to_numpy())
        rows.append({
            group_col: str(val),
            "sample_count": len(grp),
            "mae_minutes": metrics["mae_minutes"],
            "rmse_minutes": metrics["rmse_minutes"],
            "mape_percent": metrics["mape_percent"],
        })
    return pd.DataFrame(rows)


def plot_model_evaluations(
    eval_dict: Dict[str, Dict[str, Any]],
    output_dir: Path = OUTPUTS_DIR,
) -> Dict[str, Path]:
    """Generate and save publication-quality evaluation comparison figures."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plots_saved = {}

    sns.set_theme(style="whitegrid", font_scale=1.1)

    # 1. Actual vs Predicted Scatter Plot
    fig, axes = plt.subplots(1, len(eval_dict), figsize=(6 * len(eval_dict), 5), sharey=True)
    if len(eval_dict) == 1:
        axes = [axes]

    colors = ["#4C72B0", "#55A868", "#C44E52"]
    for ax, (model_name, res), color in zip(axes, eval_dict.items(), colors):
        y_true = res["y_true"]
        y_pred = res["y_pred"]
        metrics = res["metrics"]

        ax.scatter(y_true, y_pred, alpha=0.7, color=color, edgecolors="none", s=40)
        lims = [min(y_true.min(), y_pred.min()) - 0.5, max(y_true.max(), y_pred.max()) + 0.5]
        ax.plot(lims, lims, "k--", alpha=0.7, label="1:1 Perfect Prediction")

        ax.set_title(f"{model_name}\nMAE: {metrics['mae_minutes']:.2f}m | RMSE: {metrics['rmse_minutes']:.2f}m")
        ax.set_xlabel("Actual Travel Time (minutes)")
        ax.set_ylabel("Predicted Travel Time (minutes)")
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.legend(loc="upper left")

    plt.tight_layout()
    scatter_path = output_dir / "actual_vs_predicted.png"
    plt.savefig(scatter_path, dpi=200)
    plt.close()
    plots_saved["actual_vs_predicted"] = scatter_path

    # 2. Residual Distribution Plot
    plt.figure(figsize=(9, 5))
    for (model_name, res), color in zip(eval_dict.items(), colors):
        residuals = res["y_true"] - res["y_pred"]
        sns.kdeplot(residuals, label=f"{model_name} (Mean: {residuals.mean():.2f})", color=color, linewidth=2)

    plt.axvline(0, color="gray", linestyle="--", alpha=0.7)
    plt.title("Error Distribution (Residuals: Actual - Predicted in Minutes)")
    plt.xlabel("Prediction Error (minutes)")
    plt.ylabel("Density")
    plt.legend()
    plt.tight_layout()
    resid_path = output_dir / "error_distributions.png"
    plt.savefig(resid_path, dpi=200)
    plt.close()
    plots_saved["error_distributions"] = resid_path

    return plots_saved
