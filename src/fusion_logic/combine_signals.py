from pathlib import Path
import sys
import pandas as pd
import numpy as np


# Configuration

CALL_ID = "en_CA_Agriculture_1586885"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.contracts.analytical_contract import (  # noqa: E402
    build_call_contract_fields,
    enrich_turn_fusion,
    write_analysis_manifest,
)

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "acoustic_features"
    / f"{CALL_ID}_acoustic_features.csv"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "final_outputs"
METADATA_PATH = PROJECT_ROOT / "data" / "metadata" / "calls_metadata.csv"


# Optional call-center metrics.
SYSTEM_METRICS = {
    "aht_sec": None,
    "hold_time_sec": None,
    "transfer": None,
}


# Helpers

def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value

    if pd.isna(value):
        return False

    return str(value).strip().lower() in ["true", "1", "yes", "y"]


def normalize_sentiment(label: str) -> str:
    label = str(label).strip().lower()

    if "negative" in label:
        return "negative"

    if "positive" in label:
        return "positive"

    if "neutral" in label:
        return "neutral"

    return "unknown"


def classify_vocal_intensity(row) -> str:
    score = 0

    volume_level = str(row.get("volume_level", "unknown")).lower()
    speaking_rate_level = str(row.get("speaking_rate_level", "unknown")).lower()
    pitch_level = str(row.get("pitch_level", "unknown")).lower()

    if volume_level == "high":
        score += 2
    elif volume_level == "medium":
        score += 1

    if speaking_rate_level == "high":
        score += 1

    if pitch_level == "high":
        score += 1

    if score >= 3:
        return "high"

    if score >= 1:
        return "medium"

    return "low"


def score_turn(row) -> tuple[int, str]:
    speaker = row["speaker"]
    sentiment = normalize_sentiment(row.get("sentiment_label", "unknown"))
    vocal_intensity = row["vocal_intensity_level"]

    frustration_flag = to_bool(row.get("frustration_flag", False))
    empathy_flag = to_bool(row.get("empathy_flag", False))
    probing_flag = to_bool(row.get("probing_flag", False))
    ownership_flag = to_bool(row.get("ownership_flag", False))
    next_steps_flag = to_bool(row.get("next_steps_flag", False))

    score = 0
    reasons = []

    if speaker == "customer":
        if sentiment == "negative":
            score += 15
            reasons.append("negative customer sentiment")

        if frustration_flag:
            score += 25
            reasons.append("customer frustration language")

        if vocal_intensity == "high":
            score += 15
            reasons.append("high customer vocal intensity")
        elif vocal_intensity == "medium":
            score += 5
            reasons.append("medium customer vocal intensity")

    elif speaker == "agent":
        if sentiment == "negative":
            score += 8
            reasons.append("negative agent sentiment")

        if empathy_flag:
            score -= 10
            reasons.append("agent empathy detected")

        if probing_flag:
            score -= 5
            reasons.append("agent probing question detected")

        if ownership_flag:
            score -= 5
            reasons.append("agent ownership detected")

        if next_steps_flag:
            score -= 5
            reasons.append("agent next step detected")

    score = int(np.clip(score, 0, 100))

    if not reasons:
        reasons.append("no strong signal")

    return score, " | ".join(reasons)


def risk_level(score: int) -> str:
    if score >= 60:
        return "high"

    if score >= 30:
        return "medium"

    return "low"


def build_call_summary(df: pd.DataFrame) -> dict:
    customer_df = df[df["speaker"] == "customer"].copy()
    agent_df = df[df["speaker"] == "agent"].copy()

    negative_customer_turns = (
        customer_df["normalized_sentiment"] == "negative"
    ).sum()

    customer_frustration_turns = customer_df["frustration_flag_bool"].sum()

    high_intensity_customer_turns = (
        customer_df["vocal_intensity_level"] == "high"
    ).sum()

    agent_empathy_turns = agent_df["empathy_flag_bool"].sum()
    agent_probing_turns = agent_df["probing_flag_bool"].sum()
    agent_ownership_turns = agent_df["ownership_flag_bool"].sum()
    agent_next_steps_turns = agent_df["next_steps_flag_bool"].sum()

    score = 0
    reasons = []

    # Customer risk signals
    if negative_customer_turns > 0:
        score += 15
        reasons.append("negative customer sentiment detected")

    if customer_frustration_turns > 0:
        score += 25
        reasons.append("customer frustration detected")

    if high_intensity_customer_turns > 0:
        score += 15
        reasons.append("high customer vocal intensity detected")

    # Agent mitigation signals
    if customer_frustration_turns > 0 and agent_empathy_turns == 0:
        score += 15
        reasons.append("customer frustration was not clearly acknowledged")

    if agent_empathy_turns > 0:
        score -= 10
        reasons.append("agent empathy detected")

    if agent_probing_turns > 0:
        score -= 8
        reasons.append("agent probing detected")
    else:
        score += 8
        reasons.append("no agent probing detected")

    if agent_ownership_turns > 0:
        score -= 8
        reasons.append("agent ownership detected")
    else:
        score += 8
        reasons.append("no agent ownership detected")

    if agent_next_steps_turns > 0:
        score -= 8
        reasons.append("agent next steps detected")
    else:
        score += 8
        reasons.append("no clear agent next steps detected")

    # Optional system metrics
    transfer = SYSTEM_METRICS.get("transfer")
    hold_time_sec = SYSTEM_METRICS.get("hold_time_sec")
    aht_sec = SYSTEM_METRICS.get("aht_sec")

    if transfer is True:
        score += 10
        reasons.append("call was transferred")

    if (
        hold_time_sec is not None
        and aht_sec is not None
        and aht_sec > 0
    ):
        hold_ratio = hold_time_sec / aht_sec

        if hold_ratio >= 0.20:
            score += 10
            reasons.append("high hold-time ratio")

    score = int(np.clip(score, 0, 100))

    needs_manual_review = (
        score >= 60
        or (
            customer_frustration_turns > 0
            and high_intensity_customer_turns > 0
        )
    )

    return {
        "call_id": CALL_ID,
        "total_turns": len(df),
        "customer_turns": len(customer_df),
        "agent_turns": len(agent_df),

        "negative_customer_turns": int(negative_customer_turns),
        "customer_frustration_turns": int(customer_frustration_turns),
        "high_intensity_customer_turns": int(high_intensity_customer_turns),

        "agent_empathy_turns": int(agent_empathy_turns),
        "agent_probing_turns": int(agent_probing_turns),
        "agent_ownership_turns": int(agent_ownership_turns),
        "agent_next_steps_turns": int(agent_next_steps_turns),

        "system_aht_sec": aht_sec,
        "system_hold_time_sec": hold_time_sec,
        "system_transfer": transfer,

        "conversation_risk_score": score,
        "conversation_risk_level": risk_level(score),
        "needs_manual_review": needs_manual_review,
        "main_reasons": " | ".join(reasons),
    }


# Entry point

def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Acoustic features file not found: {INPUT_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_analysis_manifest()

    df = pd.read_csv(INPUT_PATH)

    required_columns = [
        "call_id",
        "turn_id",
        "speaker",
        "channel",
        "start_time",
        "end_time",
        "text",
        "sentiment_label",
        "frustration_flag",
        "empathy_flag",
        "probing_flag",
        "ownership_flag",
        "next_steps_flag",
        "volume_level",
        "speaking_rate_level",
        "pitch_level",
    ]

    missing_columns = [
        col for col in required_columns if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing columns in acoustic features CSV: {missing_columns}")

    # Normalize booleans and sentiment
    df["frustration_flag_bool"] = df["frustration_flag"].apply(to_bool)
    df["empathy_flag_bool"] = df["empathy_flag"].apply(to_bool)
    df["probing_flag_bool"] = df["probing_flag"].apply(to_bool)
    df["ownership_flag_bool"] = df["ownership_flag"].apply(to_bool)
    df["next_steps_flag_bool"] = df["next_steps_flag"].apply(to_bool)

    df["normalized_sentiment"] = df["sentiment_label"].apply(normalize_sentiment)

    # Acoustic fusion feature
    df["vocal_intensity_level"] = df.apply(classify_vocal_intensity, axis=1)

    # Turn-level fusion
    turn_scores = df.apply(score_turn, axis=1)
    df["turn_risk_score"] = [item[0] for item in turn_scores]
    df["turn_main_signal"] = [item[1] for item in turn_scores]
    df["turn_risk_level"] = df["turn_risk_score"].apply(risk_level)
    df = enrich_turn_fusion(df)

    # Call-level fusion
    call_summary = build_call_summary(df)
    if METADATA_PATH.exists():
        metadata_df = pd.read_csv(METADATA_PATH)
        metadata_match = metadata_df[metadata_df["call_id"] == CALL_ID]
        if len(metadata_match) == 1:
            metadata_row = metadata_match.iloc[0]
            call_summary.update(
                {
                    "agent_id": metadata_row["agent_id"],
                    "agent_name": metadata_row["agent_name"],
                    "agent_folder": metadata_row["agent_folder"],
                    "agent_call_number": metadata_row["agent_call_number"],
                }
            )

    call_summary.update(
        build_call_contract_fields(df, call_summary["main_reasons"])
    )
    summary_df = pd.DataFrame([call_summary])

    turn_output_path = OUTPUT_DIR / f"{CALL_ID}_turn_fusion.csv"
    summary_output_path = OUTPUT_DIR / f"{CALL_ID}_call_summary.csv"

    df.to_csv(turn_output_path, index=False, encoding="utf-8")
    summary_df.to_csv(summary_output_path, index=False, encoding="utf-8")

    print("Fusion logic completed.")
    print(f"Turn-level output saved to: {turn_output_path}")
    print(f"Call-level summary saved to: {summary_output_path}")
    print()
    print(summary_df.T)


if __name__ == "__main__":
    main()
