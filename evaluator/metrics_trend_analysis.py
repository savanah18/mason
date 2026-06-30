#!/usr/bin/env python3
"""Plot metric trends over time from aggregate_score_deployer.csv.

Time is derived from the timestamp embedded in latest_reference.
Run with: conda run -n aiops-py312 python metrics_trend_analysis.py
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


REFERENCE_TIMESTAMP_RE = re.compile(r"(\d{8}T\d{6}Z)")


def extract_timestamp(reference: str) -> datetime | None:
    if pd.isna(reference) or reference == "":
        return None

    match = REFERENCE_TIMESTAMP_RE.search(str(reference))
    if not match:
        return None

    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def load_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["timestamp"] = df["latest_reference"].apply(extract_timestamp)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    return df


def metric_columns(df: pd.DataFrame) -> list[str]:
    excluded = {
        "batch_file",
        "latest_reference",
        "timestamp",
        "total_records",
        "parsed_records",
        "parse_errors",
        "redis_records_fetched",
    }
    return [
        column
        for column in df.columns
        if column not in excluded and pd.api.types.is_numeric_dtype(df[column])
    ]


def plot_trends(df: pd.DataFrame, output_path: Path) -> None:
    sns.set_theme(style="whitegrid")

    metrics = metric_columns(df)
    if not metrics:
        raise ValueError("No numeric metric columns found to plot")

    fig, axes = plt.subplots(len(metrics), 1, figsize=(14, 3.2 * len(metrics)), sharex=True)
    if len(metrics) == 1:
        axes = [axes]

    for axis, metric in zip(axes, metrics):
        sns.lineplot(data=df, x="timestamp", y=metric, marker="o", ax=axis)
        axis.set_title(metric)
        axis.set_xlabel("")
        axis.tick_params(axis="x", rotation=45)

    axes[-1].set_xlabel("Time")
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    csv_path = Path(__file__).parent / "aggregate_score_deployer.csv"
    output_path = Path(__file__).parent / "metrics_trends_over_time.png"

    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    df = load_data(csv_path)
    plot_trends(df, output_path)
    print(f"Saved {output_path}")


if __name__ == "__main__":
    main()
