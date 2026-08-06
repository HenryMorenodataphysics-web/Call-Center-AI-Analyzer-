#!/usr/bin/env python3
"""Prepare a score-blinded human review pilot for conversation_risk_v1."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CALLS_PATH = PROJECT_ROOT / "data" / "final_outputs" / "all_calls_summary.csv"
METADATA_PATH = PROJECT_ROOT / "data" / "metadata" / "calls_metadata.csv"
BLINDED_PATH = PROJECT_ROOT / "data" / "validation" / "risk_review_pilot_blinded.csv"
KEY_PATH = PROJECT_ROOT / "data" / "validation" / "risk_review_pilot_key.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def select_three_per_agent(calls: list[dict[str, str]]) -> list[tuple[str, dict[str, str]]]:
    """Select the minimum, middle, and maximum score call for every agent."""
    by_agent: dict[str, list[dict[str, str]]] = {}
    for row in calls:
        by_agent.setdefault(row["agent_id"], []).append(row)

    selected: list[tuple[str, dict[str, str]]] = []
    for agent_id in sorted(by_agent):
        ordered = sorted(
            by_agent[agent_id],
            key=lambda row: (float(row["conversation_risk_score"]), row["call_id"]),
        )
        if len(ordered) < 3:
            raise ValueError(f"{agent_id} has fewer than three calls")
        positions = [("agent_min", 0), ("agent_middle", len(ordered) // 2), ("agent_max", -1)]
        chosen_ids: set[str] = set()
        for stratum, index in positions:
            row = ordered[index]
            if row["call_id"] in chosen_ids:
                raise ValueError(f"Sampling produced a duplicate for {agent_id}")
            chosen_ids.add(row["call_id"])
            selected.append((stratum, row))
    return selected


def build_pilot(
    calls_path: Path = CALLS_PATH,
    metadata_path: Path = METADATA_PATH,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    calls = read_csv(calls_path)
    metadata = {row["call_id"]: row for row in read_csv(metadata_path)}
    selected = select_three_per_agent(calls)

    blinded: list[dict[str, object]] = []
    key: list[dict[str, object]] = []
    for index, (stratum, call) in enumerate(selected, start=1):
        call_id = call["call_id"]
        meta = metadata[call_id]
        review_id = f"RISK-{index:03d}"
        blinded.append(
            {
                "review_id": review_id,
                "call_id": call_id,
                "transcript_path": f"data/transcripts/{call_id}_transcript.csv",
                "agent_audio_path": meta["channel1_path"].replace("\\", "/"),
                "customer_audio_path": meta["channel2_path"].replace("\\", "/"),
                "human_review_needed": "",
                "reviewer_confidence": "",
                "primary_reason": "",
                "notes": "",
                "reviewer_id": "",
                "reviewed_at_utc": "",
            }
        )
        key.append(
            {
                "review_id": review_id,
                "call_id": call_id,
                "agent_id": call["agent_id"],
                "sample_stratum": stratum,
                "conversation_risk_score": int(float(call["conversation_risk_score"])),
                "conversation_risk_level": call["conversation_risk_level"],
                "proxy_review_flag": int(parse_bool(call["needs_manual_review"])),
                "risk_rubric_version": call["risk_rubric_version"],
            }
        )
    return blinded, key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blinded-output", type=Path, default=BLINDED_PATH)
    parser.add_argument("--key-output", type=Path, default=KEY_PATH)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing review file even if it contains human labels.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.blinded_output.exists() and not args.force:
        existing = read_csv(args.blinded_output)
        completed = [
            row for row in existing if row.get("human_review_needed", "").strip() in {"0", "1"}
        ]
        if completed:
            raise SystemExit(
                f"Refusing to overwrite {len(completed)} completed human labels. "
                "Use --force only if that replacement is intentional."
            )
    blinded, key = build_pilot()
    write_csv(args.blinded_output, blinded, list(blinded[0]))
    write_csv(args.key_output, key, list(key[0]))
    print(f"Prepared {len(blinded)} score-blinded reviews: {args.blinded_output}")
    print(f"Saved proxy key separately: {args.key_output}")


if __name__ == "__main__":
    main()
