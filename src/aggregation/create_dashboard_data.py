from pathlib import Path
from collections import Counter
import sys
import pandas as pd
import soundfile as sf

# Configuration

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.contracts.analytical_contract import (  # noqa: E402
    ANALYTICAL_CONTRACT_VERSION,
    RISK_RUBRIC_VERSION,
    RISK_SCORE_TYPE,
)

METADATA_PATH = PROJECT_ROOT / "data" / "metadata" / "calls_metadata.csv"
FINAL_OUTPUTS_DIR = PROJECT_ROOT / "data" / "final_outputs"
DASHBOARD_DATA_DIR = PROJECT_ROOT / "data" / "dashboard_data"

ALL_CALLS_OUTPUT = FINAL_OUTPUTS_DIR / "all_calls_summary.csv"
AGENT_SUMMARY_OUTPUT = DASHBOARD_DATA_DIR / "agent_dashboard_summary.csv"
RISK_DISTRIBUTION_OUTPUT = DASHBOARD_DATA_DIR / "risk_distribution_by_agent.csv"
TOP_REASONS_OUTPUT = DASHBOARD_DATA_DIR / "top_reasons_by_agent.csv"


# Helpers

def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value

    if pd.isna(value):
        return False

    return str(value).strip().lower() in ["true", "1", "yes", "y"]

def get_audio_duration_sec(audio_path: Path) -> float:
    """Read audio duration from WAV metadata."""

    info = sf.info(str(audio_path))

    if info.samplerate <= 0:
        return 0.0

    return info.frames / info.samplerate


def add_duration_metrics(all_calls_df: pd.DataFrame) -> pd.DataFrame:
    """Add duration metrics using the longer audio channel for each call."""

    if not METADATA_PATH.exists():
        raise FileNotFoundError(f"Missing metadata file: {METADATA_PATH}")

    metadata_df = pd.read_csv(METADATA_PATH)

    required_columns = [
        "call_id",
        "channel1_path",
        "channel2_path",
    ]

    missing_columns = [
        col for col in required_columns if col not in metadata_df.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing metadata columns: {missing_columns}")

    duration_rows = []

    for _, row in metadata_df.iterrows():
        call_id = row["call_id"]

        channel1_path = PROJECT_ROOT / row["channel1_path"]
        channel2_path = PROJECT_ROOT / row["channel2_path"]

        if not channel1_path.exists():
            raise FileNotFoundError(f"Missing channel1 audio: {channel1_path}")

        if not channel2_path.exists():
            raise FileNotFoundError(f"Missing channel2 audio: {channel2_path}")

        channel1_duration = get_audio_duration_sec(channel1_path)
        channel2_duration = get_audio_duration_sec(channel2_path)

        call_duration_sec = max(channel1_duration, channel2_duration)

        duration_rows.append(
            {
                "call_id": call_id,
                "call_duration_sec": round(call_duration_sec, 3),
                "call_duration_min": round(call_duration_sec / 60, 3),

                # Audio-duration estimate, not operational AHT.
                "estimated_aht_sec": round(call_duration_sec, 3),
                "estimated_aht_min": round(call_duration_sec / 60, 3),
            }
        )

    duration_df = pd.DataFrame(duration_rows)

    out = all_calls_df.merge(
        duration_df,
        on="call_id",
        how="left",
    )

    return out

def load_call_summary_files() -> pd.DataFrame:
    """Load per-call summaries and exclude overlapping batch summaries."""
    summary_files = sorted(FINAL_OUTPUTS_DIR.glob("*_call_summary.csv"))

    if not summary_files:
        raise FileNotFoundError(
            f"No per-call summary files found in: {FINAL_OUTPUTS_DIR}"
        )

    dataframes = []

    for file_path in summary_files:
        print(f"Loading: {file_path.name}")
        df = pd.read_csv(file_path)

        if len(df) != 1:
            raise ValueError(
                f"Expected exactly one row in per-call summary {file_path.name}, "
                f"but found {len(df)}."
            )

        dataframes.append(df)

    all_calls_df = pd.concat(dataframes, ignore_index=True)

    duplicate_call_ids = sorted(
        all_calls_df.loc[
            all_calls_df["call_id"].duplicated(keep=False), "call_id"
        ].unique()
    )

    if duplicate_call_ids:
        raise ValueError(
            "Duplicate call_id values found in per-call summaries: "
            f"{duplicate_call_ids}"
        )

    return all_calls_df


def validate_summary_coverage(all_calls_df: pd.DataFrame) -> None:
    """Ensures the analyzed calls match metadata exactly, including per agent."""
    if not METADATA_PATH.exists():
        raise FileNotFoundError(f"Missing metadata file: {METADATA_PATH}")

    metadata_df = pd.read_csv(METADATA_PATH)
    required_columns = ["call_id", "agent_id", "agent_name"]

    missing_metadata_columns = [
        col for col in required_columns if col not in metadata_df.columns
    ]
    missing_summary_columns = [
        col for col in required_columns if col not in all_calls_df.columns
    ]

    if missing_metadata_columns:
        raise ValueError(
            f"Missing metadata columns: {missing_metadata_columns}"
        )

    if missing_summary_columns:
        raise ValueError(
            f"Missing call summary columns: {missing_summary_columns}"
        )

    duplicate_metadata_ids = sorted(
        metadata_df.loc[
            metadata_df["call_id"].duplicated(keep=False), "call_id"
        ].unique()
    )
    duplicate_summary_ids = sorted(
        all_calls_df.loc[
            all_calls_df["call_id"].duplicated(keep=False), "call_id"
        ].unique()
    )

    if duplicate_metadata_ids:
        raise ValueError(
            f"Duplicate call_id values found in metadata: {duplicate_metadata_ids}"
        )

    if duplicate_summary_ids:
        raise ValueError(
            f"Duplicate call_id values found in summaries: {duplicate_summary_ids}"
        )

    expected_call_ids = set(metadata_df["call_id"])
    actual_call_ids = set(all_calls_df["call_id"])
    missing_call_ids = sorted(expected_call_ids - actual_call_ids)
    unexpected_call_ids = sorted(actual_call_ids - expected_call_ids)

    if missing_call_ids or unexpected_call_ids:
        raise ValueError(
            "Call summary coverage does not match metadata. "
            f"Missing: {missing_call_ids}; unexpected: {unexpected_call_ids}"
        )

    expected_agent_counts = (
        metadata_df.groupby("agent_id")["call_id"].nunique().sort_index()
    )
    actual_agent_counts = (
        all_calls_df.groupby("agent_id")["call_id"].nunique().sort_index()
    )

    if not expected_agent_counts.equals(actual_agent_counts):
        raise ValueError(
            "Per-agent call counts do not match metadata. "
            f"Expected: {expected_agent_counts.to_dict()}; "
            f"actual: {actual_agent_counts.to_dict()}"
        )


def create_risk_distribution(all_calls_df: pd.DataFrame) -> pd.DataFrame:
    risk_distribution = (
        all_calls_df
        .groupby(["agent_id", "agent_name", "conversation_risk_level"])
        .size()
        .reset_index(name="call_count")
    )

    return risk_distribution


def create_top_reasons(all_calls_df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for (agent_id, agent_name), group in all_calls_df.groupby(["agent_id", "agent_name"]):
        reason_counter = Counter()

        for reasons_text in group["reason_codes"].dropna():
            reasons = [reason.strip() for reason in str(reasons_text).split("|")]
            reasons = [reason for reason in reasons if reason]

            reason_counter.update(reasons)

        for reason_code, count in reason_counter.most_common():
            rows.append(
                {
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "reason_code": reason_code,
                    "reason_count": count,
                }
            )

    return pd.DataFrame(rows)


def create_agent_summary(all_calls_df: pd.DataFrame) -> pd.DataFrame:
    df = all_calls_df.copy()

    df["needs_manual_review_bool"] = df["needs_manual_review"].apply(to_bool)

    df["has_negative_customer_turns"] = df["negative_customer_turns"] > 0
    df["has_customer_frustration"] = df["customer_frustration_turns"] > 0
    df["has_high_customer_intensity"] = df["high_intensity_customer_turns"] > 0

    df["has_agent_empathy"] = df["agent_empathy_turns"] > 0
    df["has_agent_probing"] = df["agent_probing_turns"] > 0
    df["has_agent_ownership"] = df["agent_ownership_turns"] > 0
    df["has_agent_next_steps"] = df["agent_next_steps_turns"] > 0

    # Heuristic proxy; not QA, CSAT, NPS, or survey probability.
    df["heuristic_quality_proxy"] = 100 - df["conversation_risk_score"]

    agent_summary = (
        df
        .groupby(["agent_id", "agent_name"])
        .agg(
            total_calls=("call_id", "count"),

            total_call_duration_min=("call_duration_min", "sum"),
            avg_call_duration_sec=("call_duration_sec", "mean"),
            avg_call_duration_min=("call_duration_min", "mean"),
            avg_estimated_aht_sec=("estimated_aht_sec", "mean"),
            avg_estimated_aht_min=("estimated_aht_min", "mean"),
            avg_risk_score=("conversation_risk_score", "mean"),
            min_risk_score=("conversation_risk_score", "min"),
            max_risk_score=("conversation_risk_score", "max"),
            avg_heuristic_quality_proxy=("heuristic_quality_proxy", "mean"),
            avg_signal_coverage_confidence=(
                "signal_coverage_confidence",
                "mean",
            ),
            min_signal_coverage_confidence=(
                "signal_coverage_confidence",
                "min",
            ),

            manual_review_calls=("needs_manual_review_bool", "sum"),

            avg_total_turns=("total_turns", "mean"),
            avg_customer_turns=("customer_turns", "mean"),
            avg_agent_turns=("agent_turns", "mean"),

            avg_negative_customer_turns=("negative_customer_turns", "mean"),
            avg_customer_frustration_turns=("customer_frustration_turns", "mean"),
            avg_high_intensity_customer_turns=("high_intensity_customer_turns", "mean"),

            avg_agent_empathy_turns=("agent_empathy_turns", "mean"),
            avg_agent_probing_turns=("agent_probing_turns", "mean"),
            avg_agent_ownership_turns=("agent_ownership_turns", "mean"),
            avg_agent_next_steps_turns=("agent_next_steps_turns", "mean"),

            negative_customer_call_rate=("has_negative_customer_turns", "mean"),
            customer_frustration_call_rate=("has_customer_frustration", "mean"),
            high_intensity_customer_call_rate=("has_high_customer_intensity", "mean"),

            empathy_call_rate=("has_agent_empathy", "mean"),
            probing_call_rate=("has_agent_probing", "mean"),
            ownership_call_rate=("has_agent_ownership", "mean"),
            next_steps_call_rate=("has_agent_next_steps", "mean"),
        )
        .reset_index()
    )

    risk_counts = (
        df
        .pivot_table(
            index=["agent_id", "agent_name"],
            columns="conversation_risk_level",
            values="call_id",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
    )

    for col in ["low", "medium", "high"]:
        if col not in risk_counts.columns:
            risk_counts[col] = 0

    risk_counts = risk_counts.rename(
        columns={
            "low": "low_risk_calls",
            "medium": "medium_risk_calls",
            "high": "high_risk_calls",
        }
    )

    agent_summary = agent_summary.merge(
        risk_counts,
        on=["agent_id", "agent_name"],
        how="left",
    )

    agent_summary["manual_review_rate"] = (
        agent_summary["manual_review_calls"] / agent_summary["total_calls"]
    )

    # Descriptive order without call-mix or complexity adjustment.
    agent_summary["agent_rank_by_heuristic_risk"] = (
        agent_summary["avg_risk_score"]
        .rank(ascending=True, method="dense")
        .astype(int)
    )

    agent_summary["analytical_contract_version"] = ANALYTICAL_CONTRACT_VERSION
    agent_summary["risk_rubric_version"] = RISK_RUBRIC_VERSION
    agent_summary["risk_score_type"] = RISK_SCORE_TYPE
    agent_summary["risk_score_calibrated"] = False

    numeric_cols = agent_summary.select_dtypes(include="number").columns

    for col in numeric_cols:
        if "rank" not in col and "calls" not in col and "total" not in col:
            agent_summary[col] = agent_summary[col].round(3)

    agent_summary = agent_summary.sort_values(
        by=["agent_rank_by_heuristic_risk", "agent_id"]
    )

    return agent_summary


# Entry point

def main():
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_calls_df = load_call_summary_files()
    validate_summary_coverage(all_calls_df)
    all_calls_df = add_duration_metrics(all_calls_df)
    required_columns = [
        "call_id",
        "agent_id",
        "agent_name",
        "total_turns",
        "customer_turns",
        "agent_turns",
        "negative_customer_turns",
        "customer_frustration_turns",
        "high_intensity_customer_turns",
        "agent_empathy_turns",
        "agent_probing_turns",
        "agent_ownership_turns",
        "agent_next_steps_turns",
        "conversation_risk_score",
        "conversation_risk_level",
        "needs_manual_review",
        "main_reasons",
        "reason_codes",
        "evidence_json",
        "signal_coverage_confidence",
        "analytical_contract_version",
        "risk_rubric_version",
        "risk_score_type",
        "risk_score_calibrated",
        "real_outcome_available",
        "analytical_limitations",
        "call_duration_sec",
        "call_duration_min",
        "estimated_aht_sec",
        "estimated_aht_min",
    ]

    missing_columns = [
        col for col in required_columns if col not in all_calls_df.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    all_calls_df.to_csv(ALL_CALLS_OUTPUT, index=False, encoding="utf-8")

    agent_summary = create_agent_summary(all_calls_df)
    risk_distribution = create_risk_distribution(all_calls_df)
    top_reasons = create_top_reasons(all_calls_df)

    agent_summary.to_csv(AGENT_SUMMARY_OUTPUT, index=False, encoding="utf-8")
    risk_distribution.to_csv(RISK_DISTRIBUTION_OUTPUT, index=False, encoding="utf-8")
    top_reasons.to_csv(TOP_REASONS_OUTPUT, index=False, encoding="utf-8")

    print()
    print("Dashboard data created.")
    print(f"All calls summary saved to: {ALL_CALLS_OUTPUT}")
    print(f"Agent dashboard summary saved to: {AGENT_SUMMARY_OUTPUT}")
    print(f"Risk distribution saved to: {RISK_DISTRIBUTION_OUTPUT}")
    print(f"Top reasons saved to: {TOP_REASONS_OUTPUT}")

    print()
    print("Agent Summary:")
    print(agent_summary)


if __name__ == "__main__":
    main()
