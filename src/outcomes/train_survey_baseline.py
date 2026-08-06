#!/usr/bin/env python3
"""Train and evaluate an interpretable calibrated baseline on governed real labels."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .survey_dataset import (
    DEFAULT_CONFIG,
    DEFAULT_DATASET,
    DEFAULT_REPORT,
    PROJECT_ROOT,
    load_config,
    read_csv,
)


DEFAULT_MODEL = PROJECT_ROOT / "models" / "survey_prediction" / "logistic_calibrated_v1.joblib"
DEFAULT_EVALUATION = PROJECT_ROOT / "data" / "validation" / "survey_prediction_evaluation.json"


class TrainingGateError(RuntimeError):
    """Raised when real-label readiness does not authorize model training."""


def base_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "logistic",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    solver="liblinear",
                    random_state=42,
                ),
            ),
        ]
    )


def metric_payload(y_true: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    prediction = (probability >= 0.5).astype(int)
    return {
        "roc_auc": round(float(roc_auc_score(y_true, probability)), 6),
        "average_precision": round(float(average_precision_score(y_true, probability)), 6),
        "brier_score": round(float(brier_score_loss(y_true, probability)), 6),
        "log_loss": round(float(log_loss(y_true, probability, labels=[0, 1])), 6),
        "accuracy_at_0_5": round(float(accuracy_score(y_true, prediction)), 6),
        "precision_at_0_5": round(float(precision_score(y_true, prediction, zero_division=0)), 6),
        "recall_at_0_5": round(float(recall_score(y_true, prediction, zero_division=0)), 6),
    }


def train_baseline(
    dataset_path: Path = DEFAULT_DATASET,
    config_path: Path = DEFAULT_CONFIG,
    readiness_path: Path = DEFAULT_REPORT,
    model_path: Path = DEFAULT_MODEL,
    evaluation_path: Path = DEFAULT_EVALUATION,
) -> dict[str, Any]:
    if not readiness_path.exists():
        raise TrainingGateError("Readiness report is missing; validate real outcomes first.")
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    if readiness.get("status") != "ready":
        codes = [item["code"] for item in readiness.get("issues", []) if item["severity"] == "blocking"]
        raise TrainingGateError(f"Training is disabled by readiness gates: {', '.join(codes) or 'unknown gate'}")
    if not dataset_path.exists():
        raise TrainingGateError("Governed modeling dataset is missing despite a ready report.")

    config = load_config(config_path)
    rows = read_csv(dataset_path)
    features = config["feature_columns"]
    required = {"call_id", "agent_id", "survey_positive", *features}
    missing = sorted(required - set(rows[0] if rows else []))
    if missing:
        raise TrainingGateError(f"Modeling dataset is missing columns: {', '.join(missing)}")

    X = np.asarray([[float(row[field]) for field in features] for row in rows], dtype=float)
    y = np.asarray([int(row["survey_positive"]) for row in rows], dtype=int)
    groups = np.asarray([row["agent_id"] for row in rows])
    if not np.isfinite(X).all():
        raise TrainingGateError("Modeling features contain non-finite values.")
    if set(np.unique(y)) != {0, 1}:
        raise TrainingGateError("Both positive and negative real survey labels are required.")

    evaluation_config = config["evaluation"]
    folds = min(int(evaluation_config["outer_folds"]), len(np.unique(groups)))
    splitter = StratifiedGroupKFold(
        n_splits=folds,
        shuffle=True,
        random_state=int(evaluation_config["random_state"]),
    )
    oof_probability = np.full(len(rows), np.nan, dtype=float)
    fold_results: list[dict[str, Any]] = []
    for fold_number, (train_index, test_index) in enumerate(splitter.split(X, y, groups), start=1):
        if len(np.unique(y[train_index])) < 2 or len(np.unique(y[test_index])) < 2:
            raise TrainingGateError(
                "A group-aware fold contains one class; collect broader labels before evaluation."
            )
        estimator = base_pipeline()
        estimator.fit(X[train_index], y[train_index])
        probability = estimator.predict_proba(X[test_index])[:, 1]
        oof_probability[test_index] = probability
        fold_results.append(
            {
                "fold": fold_number,
                "train_calls": len(train_index),
                "test_calls": len(test_index),
                "held_out_agents": sorted(set(groups[test_index])),
                "metrics": metric_payload(y[test_index], probability),
            }
        )
    if np.isnan(oof_probability).any():
        raise TrainingGateError("Group-aware evaluation did not score every labeled call.")

    probability_true, probability_pred = calibration_curve(
        y,
        oof_probability,
        n_bins=min(10, max(3, len(rows) // 20)),
        strategy="quantile",
    )
    base_full = base_pipeline()
    base_full.fit(X, y)
    coefficients = base_full.named_steps["logistic"].coef_[0]
    coefficient_rows = sorted(
        (
            {"feature": feature, "standardized_coefficient": round(float(coefficient), 6)}
            for feature, coefficient in zip(features, coefficients)
        ),
        key=lambda row: abs(row["standardized_coefficient"]),
        reverse=True,
    )

    minimum_class = int(min(np.sum(y == 0), np.sum(y == 1)))
    calibration_folds = min(5, minimum_class)
    calibrated_model = CalibratedClassifierCV(
        estimator=base_pipeline(),
        method=evaluation_config["calibration_method"],
        cv=calibration_folds,
    )
    calibrated_model.fit(X, y)

    evaluation = {
        "status": "research_only",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "contract_version": config["version"],
        "model": "standardized_logistic_regression_with_sigmoid_calibration",
        "target": config["target"],
        "population": {
            "labeled_calls": len(rows),
            "agents": len(np.unique(groups)),
            "positive": int(np.sum(y == 1)),
            "negative": int(np.sum(y == 0)),
        },
        "group_aware_oof_metrics": metric_payload(y, oof_probability),
        "fold_results": fold_results,
        "calibration_curve": [
            {"mean_predicted_probability": round(float(predicted), 6), "observed_positive_rate": round(float(observed), 6)}
            for predicted, observed in zip(probability_pred, probability_true)
        ],
        "standardized_coefficients": coefficient_rows,
        "guardrails": [
            "Agent identity is used only to keep agents separated across evaluation folds; it is not a model feature.",
            "The final estimator is calibrated on all governed labels and remains research-only.",
            "No decision threshold is approved; 0.5 metrics are diagnostic only.",
            "Fairness completion requires governed protected or operational slices and must not infer demographics.",
            "Predictions are conditional on survey completion and may reflect survey-response selection bias.",
        ],
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": calibrated_model,
            "feature_columns": features,
            "contract_version": config["version"],
            "target": config["target"],
            "research_only": True,
        },
        model_path,
    )
    evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    evaluation_path.write_text(json.dumps(evaluation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return evaluation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--readiness", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--evaluation", type=Path, default=DEFAULT_EVALUATION)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evaluation = train_baseline(
        args.dataset,
        args.config,
        args.readiness,
        args.model,
        args.evaluation,
    )
    print(json.dumps({"status": evaluation["status"], "metrics": evaluation["group_aware_oof_metrics"]}, indent=2))


if __name__ == "__main__":
    main()
