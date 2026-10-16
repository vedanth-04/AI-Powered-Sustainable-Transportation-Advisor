"""Held-out permutation importance for complete fitted prediction pipelines."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.inspection import permutation_importance

from src.config import RANDOM_SEED


def save_feature_importance(model, X, y, output_dir, model_name, n_repeats=20):
    """Save MAE increases after shuffling each original input column.

    Positive values indicate reliance on that feature. Correlated inputs can
    mask each other's importance. Repetition standard deviations describe
    shuffle variation, not confidence intervals or causal effects. Do not use
    these test-set diagnostics to tune/select features on the same test set.
    """
    result = permutation_importance(
        model, X, y, scoring="neg_mean_absolute_error",
        n_repeats=n_repeats, random_state=RANDOM_SEED,
    )
    table = pd.DataFrame({
        "feature": X.columns,
        "mae_increase_mean_minutes": result.importances_mean,
        "mae_increase_std_minutes": result.importances_std,
        "n_repeats": n_repeats,
        "evaluation_samples": len(X),
    }).sort_values("mae_increase_mean_minutes", ascending=False)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{model_name}_feature_importance.csv"
    png_path = output_dir / f"{model_name}_feature_importance.png"
    table.to_csv(csv_path, index=False)
    plot_data = table.iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(plot_data["feature"], plot_data["mae_increase_mean_minutes"],
            xerr=plot_data["mae_increase_std_minutes"])
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Increase in held-out MAE after shuffling (minutes)")
    ax.set_title(f"{model_name}: permutation importance\nError bars: shuffle standard deviation")
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    return csv_path, png_path
