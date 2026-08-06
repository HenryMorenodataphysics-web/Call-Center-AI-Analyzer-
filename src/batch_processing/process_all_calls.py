from pathlib import Path
import re
import sys
import numpy as np
import pandas as pd
import librosa
from faster_whisper import WhisperModel
from transformers import pipeline


# Configuration

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.contracts.analytical_contract import (  # noqa: E402
    build_call_contract_fields,
    enrich_turn_fusion,
    write_analysis_manifest,
)

METADATA_PATH = PROJECT_ROOT / "data" / "metadata" / "calls_metadata.csv"

TRANSCRIPTS_DIR = PROJECT_ROOT / "data" / "transcripts"
SPEAKER_TURNS_DIR = PROJECT_ROOT / "data" / "speaker_turns"
TEXT_ANALYSIS_DIR = PROJECT_ROOT / "data" / "text_analysis"
ACOUSTIC_FEATURES_DIR = PROJECT_ROOT / "data" / "acoustic_features"
FINAL_OUTPUTS_DIR = PROJECT_ROOT / "data" / "final_outputs"

# Agent range to process.
START_AGENT = 2
END_AGENT = 2

# faster-whisper
MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

# Hugging Face sentiment model
SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"


# Rule-based patterns

FRUSTRATION_PATTERNS = [
    r"\bfrustrated\b",
    r"\bupset\b",
    r"\bangry\b",
    r"\bannoyed\b",
    r"\bunacceptable\b",
    r"\bthis is ridiculous\b",
    r"\bi already called\b",
    r"\bi have called\b",
    r"\bno one helped\b",
    r"\bnot working again\b",
    r"\bsame issue\b",
]

EMPATHY_PATTERNS = [
    r"\bi understand\b",
    r"\bi completely understand\b",
    r"\bi apologize\b",
    r"\bi am sorry\b",
    r"\bsorry about that\b",
    r"\bi know this is frustrating\b",
    r"\bi can see how\b",
]

OWNERSHIP_PATTERNS = [
    r"\blet me check\b",
    r"\blet me take a look\b",
    r"\bi can help\b",
    r"\bi will help\b",
    r"\bwe can try\b",
    r"\blet's go ahead\b",
    r"\bi'll go ahead\b",
]

NEXT_STEPS_PATTERNS = [
    r"\bnext step\b",
    r"\bwhat we are going to do\b",
    r"\bwhat we'll do\b",
    r"\bi will transfer\b",
    r"\bi will schedule\b",
    r"\byou will receive\b",
    r"\bafter this\b",
    r"\bonce we\b",
]


# Utilities

def ensure_output_dirs():
    for directory in [
        TRANSCRIPTS_DIR,
        SPEAKER_TURNS_DIR,
        TEXT_ANALYSIS_DIR,
        ACOUSTIC_FEATURES_DIR,
        FINAL_OUTPUTS_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def contains_pattern(text: str, patterns: list[str]) -> bool:
    text = str(text).lower()

    for pattern in patterns:
        if re.search(pattern, text):
            return True

    return False


def is_probing_question(text: str, speaker: str) -> bool:
    if speaker != "agent":
        return False

    text_lower = str(text).lower().strip()

    question_starters = [
        "what",
        "when",
        "where",
        "why",
        "how",
        "can you",
        "could you",
        "did you",
        "do you",
        "have you",
        "are you",
        "is it",
    ]

    if "?" in text_lower:
        return True

    return any(text_lower.startswith(starter) for starter in question_starters)


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


def risk_level(score: int) -> str:
    if score >= 60:
        return "high"

    if score >= 30:
        return "medium"

    return "low"


# Transcription

def transcribe_channel(model, audio_path: Path, call_id: str, channel: str):
    segments, info = model.transcribe(
        str(audio_path),
        language="en",
        beam_size=5,
    )

    rows = []

    for segment_id, segment in enumerate(segments, start=1):
        rows.append(
            {
                "call_id": call_id,
                "channel": channel,
                "segment_id": segment_id,
                "start_time": round(segment.start, 2),
                "end_time": round(segment.end, 2),
                "text": segment.text.strip(),
            }
        )

    return rows


def create_transcript(call_row, model):
    call_id = call_row["call_id"]

    channel1_path = PROJECT_ROOT / call_row["channel1_path"]
    channel2_path = PROJECT_ROOT / call_row["channel2_path"]

    if not channel1_path.exists():
        raise FileNotFoundError(f"Missing channel1 file: {channel1_path}")

    if not channel2_path.exists():
        raise FileNotFoundError(f"Missing channel2 file: {channel2_path}")

    rows = []

    rows.extend(
        transcribe_channel(
            model=model,
            audio_path=channel1_path,
            call_id=call_id,
            channel="channel1",
        )
    )

    rows.extend(
        transcribe_channel(
            model=model,
            audio_path=channel2_path,
            call_id=call_id,
            channel="channel2",
        )
    )

    transcript_df = pd.DataFrame(rows)

    output_path = TRANSCRIPTS_DIR / f"{call_id}_transcript.csv"
    transcript_df.to_csv(output_path, index=False, encoding="utf-8")

    return transcript_df


# Speaker assignment

def assign_speakers(transcript_df: pd.DataFrame):
    channel_to_speaker = {
        "channel1": "agent",
        "channel2": "customer",
    }

    df = transcript_df.copy()
    df["speaker"] = df["channel"].map(channel_to_speaker)

    df = df.sort_values(
        by=["start_time", "end_time"]
    ).reset_index(drop=True)

    df.insert(1, "turn_id", range(1, len(df) + 1))

    df = df[
        [
            "call_id",
            "turn_id",
            "speaker",
            "channel",
            "segment_id",
            "start_time",
            "end_time",
            "text",
        ]
    ]

    call_id = df["call_id"].iloc[0]
    output_path = SPEAKER_TURNS_DIR / f"{call_id}_speaker_turns.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")

    return df


# Text classification

def classify_text(turns_df: pd.DataFrame, sentiment_pipeline):
    rows = []

    for _, row in turns_df.iterrows():
        text = str(row["text"])
        speaker = row["speaker"]

        if text.strip():
            sentiment_result = sentiment_pipeline(text[:512])[0]
            sentiment_label = sentiment_result["label"]
            sentiment_score = round(float(sentiment_result["score"]), 4)
        else:
            sentiment_label = "unknown"
            sentiment_score = 0.0

        frustration_flag = (
            speaker == "customer"
            and contains_pattern(text, FRUSTRATION_PATTERNS)
        )

        empathy_flag = (
            speaker == "agent"
            and contains_pattern(text, EMPATHY_PATTERNS)
        )

        probing_flag = is_probing_question(text, speaker)

        ownership_flag = (
            speaker == "agent"
            and contains_pattern(text, OWNERSHIP_PATTERNS)
        )

        next_steps_flag = (
            speaker == "agent"
            and contains_pattern(text, NEXT_STEPS_PATTERNS)
        )

        rows.append(
            {
                **row.to_dict(),
                "sentiment_label": sentiment_label,
                "sentiment_score": sentiment_score,
                "frustration_flag": frustration_flag,
                "empathy_flag": empathy_flag,
                "probing_flag": probing_flag,
                "ownership_flag": ownership_flag,
                "next_steps_flag": next_steps_flag,
            }
        )

    df = pd.DataFrame(rows)

    call_id = df["call_id"].iloc[0]
    output_path = TEXT_ANALYSIS_DIR / f"{call_id}_text_analysis.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")

    return df


# Acoustic features

def load_audio(channel_path: Path):
    y, sr = librosa.load(channel_path, sr=None, mono=True)
    return y, sr


def extract_audio_segment(y: np.ndarray, sr: int, start_time: float, end_time: float):
    start_sample = int(start_time * sr)
    end_sample = int(end_time * sr)

    start_sample = max(0, start_sample)
    end_sample = min(len(y), end_sample)

    return y[start_sample:end_sample]


def safe_mean(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]

    if len(values) == 0:
        return np.nan

    return float(np.mean(values))


def extract_segment_features(segment: np.ndarray, sr: int, text: str):
    duration_sec = len(segment) / sr if sr > 0 else 0

    if len(segment) == 0 or duration_sec <= 0:
        return {
            "segment_duration_sec": duration_sec,
            "rms_energy": np.nan,
            "peak_amplitude": np.nan,
            "rms_db": np.nan,
            "zero_crossing_rate": np.nan,
            "spectral_centroid": np.nan,
            "pitch_mean_hz": np.nan,
            "pitch_std_hz": np.nan,
            "speaking_rate_wps": np.nan,
        }

    rms_energy = float(np.sqrt(np.mean(segment ** 2)))
    peak_amplitude = float(np.max(np.abs(segment)))

    if rms_energy > 0:
        rms_db = float(20 * np.log10(rms_energy))
    else:
        rms_db = np.nan

    zero_crossing_rate = float(
        np.mean(librosa.feature.zero_crossing_rate(segment)[0])
    )

    spectral_centroid = float(
        np.mean(librosa.feature.spectral_centroid(y=segment, sr=sr)[0])
    )

    if len(segment) >= 2048:
        try:
            f0 = librosa.yin(
                segment,
                fmin=50,
                fmax=400,
                sr=sr,
                frame_length=1024,
                hop_length=256,
            )

            f0 = f0[np.isfinite(f0)]
            f0 = f0[(f0 >= 50) & (f0 <= 400)]

            pitch_mean_hz = safe_mean(f0)
            pitch_std_hz = float(np.std(f0)) if len(f0) > 0 else np.nan

        except Exception:
            pitch_mean_hz = np.nan
            pitch_std_hz = np.nan
    else:
        pitch_mean_hz = np.nan
        pitch_std_hz = np.nan

    words = str(text).split()
    speaking_rate_wps = len(words) / duration_sec if duration_sec > 0 else np.nan

    return {
        "segment_duration_sec": round(duration_sec, 3),
        "rms_energy": round(rms_energy, 6),
        "peak_amplitude": round(peak_amplitude, 6),
        "rms_db": round(rms_db, 3) if np.isfinite(rms_db) else np.nan,
        "zero_crossing_rate": round(zero_crossing_rate, 6),
        "spectral_centroid": round(spectral_centroid, 3),
        "pitch_mean_hz": round(pitch_mean_hz, 3) if np.isfinite(pitch_mean_hz) else np.nan,
        "pitch_std_hz": round(pitch_std_hz, 3) if np.isfinite(pitch_std_hz) else np.nan,
        "speaking_rate_wps": round(speaking_rate_wps, 3) if np.isfinite(speaking_rate_wps) else np.nan,
    }


def add_relative_levels(df: pd.DataFrame):
    out = df.copy()

    for col, level_col in [
        ("rms_db", "volume_level"),
        ("speaking_rate_wps", "speaking_rate_level"),
        ("pitch_mean_hz", "pitch_level"),
    ]:
        valid = out[col].dropna()

        if len(valid) < 3:
            out[level_col] = "unknown"
            continue

        q_low = valid.quantile(0.33)
        q_high = valid.quantile(0.66)

        def assign_level(value):
            if pd.isna(value):
                return "unknown"
            if value <= q_low:
                return "low"
            if value >= q_high:
                return "high"
            return "medium"

        out[level_col] = out[col].apply(assign_level)

    return out


def extract_acoustic_features(text_df: pd.DataFrame, call_row):
    channel1_path = PROJECT_ROOT / call_row["channel1_path"]
    channel2_path = PROJECT_ROOT / call_row["channel2_path"]

    audio_data = {
        "channel1": load_audio(channel1_path),
        "channel2": load_audio(channel2_path),
    }

    rows = []

    for _, row in text_df.iterrows():
        channel = row["channel"]
        y, sr = audio_data[channel]

        segment = extract_audio_segment(
            y=y,
            sr=sr,
            start_time=float(row["start_time"]),
            end_time=float(row["end_time"]),
        )

        features = extract_segment_features(
            segment=segment,
            sr=sr,
            text=row["text"],
        )

        rows.append(
            {
                **row.to_dict(),
                **features,
            }
        )

    df = pd.DataFrame(rows)
    df = add_relative_levels(df)

    call_id = df["call_id"].iloc[0]
    output_path = ACOUSTIC_FEATURES_DIR / f"{call_id}_acoustic_features.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")

    return df


# Signal fusion

def classify_vocal_intensity(row):
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


def score_turn(row):
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


def build_call_summary(df: pd.DataFrame, call_row):
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

    if negative_customer_turns > 0:
        score += 15
        reasons.append("negative customer sentiment detected")

    if customer_frustration_turns > 0:
        score += 25
        reasons.append("customer frustration detected")

    if high_intensity_customer_turns > 0:
        score += 15
        reasons.append("high customer vocal intensity detected")

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

    score = int(np.clip(score, 0, 100))

    needs_manual_review = (
        score >= 60
        or (
            customer_frustration_turns > 0
            and high_intensity_customer_turns > 0
        )
    )

    return {
        "call_id": call_row["call_id"],
        "agent_id": call_row["agent_id"],
        "agent_name": call_row["agent_name"],
        "agent_folder": call_row["agent_folder"],
        "agent_call_number": call_row["agent_call_number"],

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

        "conversation_risk_score": score,
        "conversation_risk_level": risk_level(score),
        "needs_manual_review": needs_manual_review,
        "main_reasons": " | ".join(reasons),
    }


def apply_fusion(acoustic_df: pd.DataFrame, call_row):
    df = acoustic_df.copy()

    df["frustration_flag_bool"] = df["frustration_flag"].apply(to_bool)
    df["empathy_flag_bool"] = df["empathy_flag"].apply(to_bool)
    df["probing_flag_bool"] = df["probing_flag"].apply(to_bool)
    df["ownership_flag_bool"] = df["ownership_flag"].apply(to_bool)
    df["next_steps_flag_bool"] = df["next_steps_flag"].apply(to_bool)

    df["normalized_sentiment"] = df["sentiment_label"].apply(normalize_sentiment)

    df["vocal_intensity_level"] = df.apply(classify_vocal_intensity, axis=1)

    turn_scores = df.apply(score_turn, axis=1)
    df["turn_risk_score"] = [item[0] for item in turn_scores]
    df["turn_main_signal"] = [item[1] for item in turn_scores]
    df["turn_risk_level"] = df["turn_risk_score"].apply(risk_level)

    df = enrich_turn_fusion(df)

    call_summary = build_call_summary(df, call_row)
    call_summary.update(
        build_call_contract_fields(df, call_summary["main_reasons"])
    )
    summary_df = pd.DataFrame([call_summary])

    call_id = call_row["call_id"]

    turn_output_path = FINAL_OUTPUTS_DIR / f"{call_id}_turn_fusion.csv"
    summary_output_path = FINAL_OUTPUTS_DIR / f"{call_id}_call_summary.csv"

    df.to_csv(turn_output_path, index=False, encoding="utf-8")
    summary_df.to_csv(summary_output_path, index=False, encoding="utf-8")

    return call_summary


# Batch execution

def main():
    ensure_output_dirs()
    manifest_path = write_analysis_manifest()

    if not METADATA_PATH.exists():
        raise FileNotFoundError(f"Missing metadata file: {METADATA_PATH}")

    metadata_df = pd.read_csv(METADATA_PATH)

    start_agent_id = f"Agent_{START_AGENT:03d}"
    end_agent_id = f"Agent_{END_AGENT:03d}"

    selected_metadata = metadata_df[
        (metadata_df["agent_id"] >= start_agent_id)
        & (metadata_df["agent_id"] <= end_agent_id)
    ].copy()

    if selected_metadata.empty:
        raise ValueError("No calls found for selected agent range.")

    selected_metadata = selected_metadata.sort_values(
        by=["agent_id", "agent_call_number"]
    )

    print("Loading faster-whisper model...")
    whisper_model = WhisperModel(
        MODEL_SIZE,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
    )

    print("Loading Hugging Face sentiment model...")
    sentiment_pipeline = pipeline(
        task="sentiment-analysis",
        model=SENTIMENT_MODEL,
        tokenizer=SENTIMENT_MODEL,
    )

    all_summaries = []

    total_calls = len(selected_metadata)

    print()
    print(f"Processing {total_calls} calls...")
    print(f"Agent range: {start_agent_id} to {end_agent_id}")
    print(f"Analytical manifest: {manifest_path}")
    print()

    for _, call_row in selected_metadata.iterrows():
        call_number = len(all_summaries) + 1
        call_id = call_row["call_id"]
        agent_id = call_row["agent_id"]
        agent_name = call_row["agent_name"]

        print(
            f"[{call_number:03d}/{total_calls}] "
            f"{agent_id} | {agent_name} | {call_id}"
        )

        transcript_df = create_transcript(call_row, whisper_model)
        speaker_turns_df = assign_speakers(transcript_df)
        text_df = classify_text(speaker_turns_df, sentiment_pipeline)
        acoustic_df = extract_acoustic_features(text_df, call_row)
        call_summary = apply_fusion(acoustic_df, call_row)

        all_summaries.append(call_summary)

    all_summary_df = pd.DataFrame(all_summaries)

    if START_AGENT == 1 and END_AGENT == 10:
        output_path = FINAL_OUTPUTS_DIR / "all_calls_summary.csv"
    else:
        output_path = (
            FINAL_OUTPUTS_DIR
            / f"calls_summary_{start_agent_id}_to_{end_agent_id}.csv"
        )

    all_summary_df.to_csv(output_path, index=False, encoding="utf-8")

    print()
    print("Batch processing completed.")
    print(f"Summary saved to: {output_path}")
    print()
    print(all_summary_df.head())


if __name__ == "__main__":
    main()
