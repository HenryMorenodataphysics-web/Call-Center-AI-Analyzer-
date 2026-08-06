#!/usr/bin/env python3
"""Compare completed human review labels with conversation_risk_v1."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLINDED_PATH = PROJECT_ROOT / "data" / "validation" / "risk_review_pilot_blinded.csv"
KEY_PATH = PROJECT_ROOT / "data" / "validation" / "risk_review_pilot_key.csv"
REPORT_JSON = PROJECT_ROOT / "data" / "validation" / "risk_review_pilot_report.json"
REPORT_MD = PROJECT_ROOT / "data" / "validation" / "risk_review_pilot_report.md"
VALID_LABELS = {"0", "1"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def completed_reviews(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("human_review_needed", "").strip() in VALID_LABELS]


def evaluate(blinded_path: Path = BLINDED_PATH, key_path: Path = KEY_PATH) -> dict[str, Any]:
    reviews = completed_reviews(read_csv(blinded_path))
    if len(reviews) < 20:
        raise ValueError(
            f"At least 20 completed human labels are required; found {len(reviews)}. "
            "Use only 0 or 1 in human_review_needed."
        )

    key = {row["review_id"]: row for row in read_csv(key_path)}
    missing = sorted({row["review_id"] for row in reviews} - set(key))
    if missing:
        raise ValueError(f"Review IDs missing from proxy key: {missing}")

    human = [int(row["human_review_needed"]) for row in reviews]
    proxy = [int(key[row["review_id"]]["proxy_review_flag"]) for row in reviews]
    scores = [float(key[row["review_id"]]["conversation_risk_score"]) for row in reviews]
    tn, fp, fn, tp = confusion_matrix(human, proxy, labels=[0, 1]).ravel()

    both_human_classes = len(set(human)) == 2
    def finite_or_none(value: float) -> float | None:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    metrics: dict[str, Any] = {
        "accuracy": finite_or_none(accuracy_score(human, proxy)),
        "balanced_accuracy": finite_or_none(balanced_accuracy_score(human, proxy)),
        "precision": finite_or_none(precision_score(human, proxy, zero_division=0)),
        "recall": finite_or_none(recall_score(human, proxy, zero_division=0)),
        "specificity": finite_or_none(tn / (tn + fp)) if tn + fp else None,
        "f1": finite_or_none(f1_score(human, proxy, zero_division=0)),
        "cohen_kappa": finite_or_none(cohen_kappa_score(human, proxy)),
        "roc_auc_continuous_score": finite_or_none(roc_auc_score(human, scores)) if both_human_classes else None,
        "average_precision_continuous_score": (
            finite_or_none(average_precision_score(human, scores)) if both_human_classes else None
        ),
    }
    return {
        "status": "exploratory_pilot_complete",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rubric": "conversation_risk_v1",
        "review_count": len(reviews),
        "human_positive": sum(human),
        "human_negative": len(human) - sum(human),
        "confusion_matrix": {"true_negative": int(tn), "false_positive": int(fp), "false_negative": int(fn), "true_positive": int(tp)},
        "metrics": metrics,
        "interpretation_boundary": (
            "Exploratory construct-validity evidence only. This small, purposive sample "
            "does not calibrate the score, establish a production threshold, measure fairness, "
            "or authorize employment decisions. Do not tune weights on this same pilot."
        ),
    }


def markdown(report: dict[str, Any]) -> str:
    def fmt(value: Any) -> str:
        return "not estimable" if value is None else f"{value:.3f}"

    cm = report["confusion_matrix"]
    lines = [
        "# Human review pilot for `conversation_risk_v1`",
        "",
        f"- Status: **{report['status']}**",
        f"- Completed reviews: **{report['review_count']}**",
        f"- Human review-needed labels: **{report['human_positive']} yes / {report['human_negative']} no**",
        "",
        "## Comparison with the proxy review flag",
        "",
        f"- True negative: {cm['true_negative']}",
        f"- False positive: {cm['false_positive']}",
        f"- False negative: {cm['false_negative']}",
        f"- True positive: {cm['true_positive']}",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for name, value in report["metrics"].items():
        lines.append(f"| {name.replace('_', ' ')} | {fmt(value)} |")
    lines.extend(["", "## Interpretation boundary", "", report["interpretation_boundary"], ""])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blinded", type=Path, default=BLINDED_PATH)
    parser.add_argument("--key", type=Path, default=KEY_PATH)
    parser.add_argument("--json-output", type=Path, default=REPORT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=REPORT_MD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = evaluate(args.blinded, args.key)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(f"Pilot report: {args.markdown_output}")


if __name__ == "__main__":
    main()
