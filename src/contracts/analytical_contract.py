from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib import metadata as package_metadata
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = PROJECT_ROOT / "config" / "analytical_contract_v1.json"
MANIFEST_PATH = PROJECT_ROOT / "data" / "metadata" / "analysis_manifest.json"
KPI_CATALOG_PATH = PROJECT_ROOT / "data" / "metadata" / "kpi_catalog.csv"

ANALYTICAL_CONTRACT_VERSION = "1.0.0"
RISK_RUBRIC_VERSION = "conversation_risk_v1"
RISK_SCORE_TYPE = "heuristic_proxy"
DATASET_RELEASE_ID = "apptek_100_calls_v1"
ASR_MODEL_ID = "faster-whisper/small"
SENTIMENT_MODEL_ID = "cardiffnlp/twitter-roberta-base-sentiment-latest"

ANALYTICAL_LIMITATIONS = (
    "NO_GROUND_TRUTH_OUTCOME",
    "HEURISTIC_RISK_NOT_CALIBRATED",
    "RELATIVE_WITHIN_CALL_ACOUSTIC_LEVELS",
    "RULE_BASED_BEHAVIOR_FLAGS",
    "PORTFOLIO_SAMPLE_NOT_PRODUCTION_POPULATION",
)

TURN_REASON_TEXT_TO_CODE = {
    "negative customer sentiment": "CUST_NEGATIVE_SENTIMENT",
    "customer frustration language": "CUST_FRUSTRATION_LANGUAGE",
    "high customer vocal intensity": "CUST_HIGH_VOCAL_INTENSITY",
    "medium customer vocal intensity": "CUST_MEDIUM_VOCAL_INTENSITY",
    "negative agent sentiment": "AGENT_NEGATIVE_SENTIMENT",
    "agent empathy detected": "AGENT_EMPATHY",
    "agent probing question detected": "AGENT_PROBING",
    "agent ownership detected": "AGENT_OWNERSHIP",
    "agent next step detected": "AGENT_NEXT_STEPS",
    "no strong signal": "NO_STRONG_SIGNAL",
}

CALL_REASON_TEXT_TO_CODE = {
    "negative customer sentiment detected": "CUST_NEGATIVE_SENTIMENT",
    "customer frustration detected": "CUST_FRUSTRATION_LANGUAGE",
    "high customer vocal intensity detected": "CUST_HIGH_VOCAL_INTENSITY",
    "customer frustration was not clearly acknowledged": (
        "AGENT_NO_EMPATHY_AFTER_FRUSTRATION"
    ),
    "agent empathy detected": "AGENT_EMPATHY",
    "agent probing detected": "AGENT_PROBING",
    "no agent probing detected": "AGENT_NO_PROBING",
    "agent ownership detected": "AGENT_OWNERSHIP",
    "no agent ownership detected": "AGENT_NO_OWNERSHIP",
    "agent next steps detected": "AGENT_NEXT_STEPS",
    "no clear agent next steps detected": "AGENT_NO_NEXT_STEPS",
}


def load_contract() -> dict[str, Any]:
    with CONTRACT_PATH.open("r", encoding="utf-8") as contract_file:
        contract = json.load(contract_file)

    if contract.get("contract_version") != ANALYTICAL_CONTRACT_VERSION:
        raise ValueError(
            "Contract file version does not match the code version: "
            f"{contract.get('contract_version')} != "
            f"{ANALYTICAL_CONTRACT_VERSION}"
        )

    return contract


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _is_present(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return bool(str(value).strip())


def _is_finite_number(value: Any, minimum: float, maximum: float) -> bool:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False
    return minimum <= numeric_value <= maximum


def reason_codes_from_text(
    reasons_text: str, mapping: dict[str, str]
) -> list[str]:
    reason_codes = []

    for reason in str(reasons_text).split("|"):
        normalized_reason = reason.strip().lower()
        if not normalized_reason:
            continue

        reason_code = mapping.get(normalized_reason)
        if reason_code is None:
            raise ValueError(f"Unmapped analytical reason: {reason.strip()}")

        if reason_code not in reason_codes:
            reason_codes.append(reason_code)

    return reason_codes


def calculate_signal_coverage_confidence(row: pd.Series) -> float:
    """
    Measures input coverage, not predictive correctness.

    Text contributes 0.20, usable sentiment contributes 0.30, and the acoustic
    measures rms_db, speaking_rate_wps, and pitch_mean_hz share the remaining
    0.50. The result must never be presented as model probability.
    """
    confidence = 0.0

    if _is_present(row.get("text")):
        confidence += 0.20

    sentiment_label = str(row.get("normalized_sentiment", "unknown")).lower()
    sentiment_score = row.get("sentiment_score")
    if (
        sentiment_label in {"negative", "neutral", "positive"}
        and _is_finite_number(sentiment_score, 0.0, 1.0)
    ):
        confidence += 0.30

    acoustic_columns = ("rms_db", "speaking_rate_wps", "pitch_mean_hz")
    available_acoustic_features = sum(
        _is_finite_number(row.get(column), -1_000_000.0, 1_000_000.0)
        for column in acoustic_columns
    )
    confidence += 0.50 * available_acoustic_features / len(acoustic_columns)

    return round(confidence, 3)


def enrich_turn_fusion(turn_df: pd.DataFrame) -> pd.DataFrame:
    enriched = turn_df.copy()

    enriched["turn_reason_codes"] = enriched["turn_main_signal"].apply(
        lambda value: "|".join(
            reason_codes_from_text(value, TURN_REASON_TEXT_TO_CODE)
        )
    )
    enriched["evidence_id"] = enriched.apply(
        lambda row: f"{row['call_id']}:turn:{int(row['turn_id'])}", axis=1
    )
    enriched["signal_coverage_confidence"] = enriched.apply(
        calculate_signal_coverage_confidence, axis=1
    )
    enriched["analytical_contract_version"] = ANALYTICAL_CONTRACT_VERSION
    enriched["risk_rubric_version"] = RISK_RUBRIC_VERSION
    enriched["risk_score_type"] = RISK_SCORE_TYPE
    enriched["risk_score_calibrated"] = False
    enriched["asr_model_id"] = ASR_MODEL_ID
    enriched["sentiment_model_id"] = SENTIMENT_MODEL_ID

    return enriched


def _turn_ids(turn_df: pd.DataFrame, mask: pd.Series) -> list[int]:
    return sorted(turn_df.loc[mask, "turn_id"].astype(int).unique().tolist())


def build_evidence_map(turn_df: pd.DataFrame, reason_codes: list[str]) -> dict:
    customer = turn_df["speaker"].astype(str).str.lower().eq("customer")
    agent = turn_df["speaker"].astype(str).str.lower().eq("agent")
    negative = (
        turn_df["normalized_sentiment"].astype(str).str.lower().eq("negative")
    )
    high_intensity = (
        turn_df["vocal_intensity_level"].astype(str).str.lower().eq("high")
    )

    masks = {
        "CUST_NEGATIVE_SENTIMENT": customer & negative,
        "CUST_FRUSTRATION_LANGUAGE": customer
        & turn_df["frustration_flag_bool"].apply(_to_bool),
        "CUST_HIGH_VOCAL_INTENSITY": customer & high_intensity,
        "AGENT_EMPATHY": agent & turn_df["empathy_flag_bool"].apply(_to_bool),
        "AGENT_PROBING": agent & turn_df["probing_flag_bool"].apply(_to_bool),
        "AGENT_OWNERSHIP": agent
        & turn_df["ownership_flag_bool"].apply(_to_bool),
        "AGENT_NEXT_STEPS": agent
        & turn_df["next_steps_flag_bool"].apply(_to_bool),
    }

    evidence = {}
    for reason_code in reason_codes:
        mask = masks.get(reason_code)
        evidence[reason_code] = _turn_ids(turn_df, mask) if mask is not None else []

    return evidence


def build_call_contract_fields(
    turn_df: pd.DataFrame, reasons_text: str
) -> dict[str, Any]:
    reason_codes = reason_codes_from_text(
        reasons_text, CALL_REASON_TEXT_TO_CODE
    )
    evidence = build_evidence_map(turn_df, reason_codes)

    return {
        "reason_codes": "|".join(reason_codes),
        "evidence_json": json.dumps(evidence, separators=(",", ":")),
        "signal_coverage_confidence": round(
            float(turn_df["signal_coverage_confidence"].mean()), 3
        ),
        "analytical_contract_version": ANALYTICAL_CONTRACT_VERSION,
        "risk_rubric_version": RISK_RUBRIC_VERSION,
        "risk_score_type": RISK_SCORE_TYPE,
        "risk_score_calibrated": False,
        "real_outcome_available": False,
        "analytical_limitations": "|".join(ANALYTICAL_LIMITATIONS),
        "dataset_release_id": DATASET_RELEASE_ID,
        "asr_model_id": ASR_MODEL_ID,
        "sentiment_model_id": SENTIMENT_MODEL_ID,
    }


def _installed_version(package_name: str) -> str | None:
    try:
        return package_metadata.version(package_name)
    except package_metadata.PackageNotFoundError:
        return None


def write_analysis_manifest() -> Path:
    contract = load_contract()
    manifest = {
        "manifest_version": "1.0.0",
        "manifest_created_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract_version": ANALYTICAL_CONTRACT_VERSION,
        "dataset_release_id": DATASET_RELEASE_ID,
        "source_dataset": contract["source_dataset"],
        "risk_rubric_version": RISK_RUBRIC_VERSION,
        "risk_score_type": RISK_SCORE_TYPE,
        "risk_score_calibrated": False,
        "models": contract["models"],
        "package_versions": {
            package: _installed_version(package)
            for package in (
                "faster-whisper",
                "transformers",
                "torch",
                "librosa",
                "pandas",
                "numpy",
            )
        },
        "legacy_inference_timestamp_note": (
            "Exact per-call inference timestamps were not captured before "
            "contract v1. The manifest timestamp records contract application, "
            "not original model execution."
        ),
        "analytical_limitations": list(ANALYTICAL_LIMITATIONS),
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, indent=2)
        manifest_file.write("\n")

    return MANIFEST_PATH


def export_metric_catalog() -> Path:
    contract = load_contract()
    rows = []

    for metric_name, definition in contract["metric_catalog"].items():
        rows.append(
            {
                "metric_name": metric_name,
                "category": definition.get("category"),
                "grain": definition.get("grain"),
                "source": definition.get("source"),
                "availability": definition.get("availability", "available"),
                "direction": definition.get("direction"),
                "confidence_field": definition.get("confidence_field"),
                "limitation": definition.get("limitation"),
                "required_source": definition.get("required_source"),
                "analytical_contract_version": ANALYTICAL_CONTRACT_VERSION,
            }
        )

    KPI_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(KPI_CATALOG_PATH, index=False, encoding="utf-8")
    return KPI_CATALOG_PATH
