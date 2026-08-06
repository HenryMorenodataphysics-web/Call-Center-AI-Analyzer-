from pathlib import Path
import numpy as np
import pandas as pd
import librosa


# Configuration

CALL_ID = "en_CA_Agriculture_1586885"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "text_analysis"
    / f"{CALL_ID}_text_analysis.csv"
)

RAW_AUDIO_DIR = PROJECT_ROOT / "data" / "raw_audio"

OUTPUT_DIR = PROJECT_ROOT / "data" / "acoustic_features"

CHANNEL_FILES = {
    "channel1": RAW_AUDIO_DIR / f"{CALL_ID}_channel1.wav",
    "channel2": RAW_AUDIO_DIR / f"{CALL_ID}_channel2.wav",
}


# Helpers

def load_audio_files(channel_files: dict) -> dict:
    audio_data = {}

    for channel, audio_path in channel_files.items():
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        print(f"Loading audio: {audio_path.name}")
        y, sr = librosa.load(audio_path, sr=None, mono=True)

        audio_data[channel] = {
            "y": y,
            "sr": sr,
        }

    return audio_data


def extract_audio_segment(y: np.ndarray, sr: int, start_time: float, end_time: float) -> np.ndarray:
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


def extract_segment_features(segment: np.ndarray, sr: int, text: str) -> dict:
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

    zero_crossing_rate = float(np.mean(librosa.feature.zero_crossing_rate(segment)[0]))

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


def add_relative_levels(df: pd.DataFrame) -> pd.DataFrame:
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


# Entry point

def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Text analysis file not found: {INPUT_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    turns_df = pd.read_csv(INPUT_PATH)

    required_columns = [
        "call_id",
        "turn_id",
        "speaker",
        "channel",
        "start_time",
        "end_time",
        "text",
    ]

    missing_columns = [
        col for col in required_columns if col not in turns_df.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing columns in text analysis CSV: {missing_columns}")

    audio_data = load_audio_files(CHANNEL_FILES)

    rows = []

    print("Extracting acoustic features...")

    for _, row in turns_df.iterrows():
        channel = row["channel"]

        y = audio_data[channel]["y"]
        sr = audio_data[channel]["sr"]

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

    output_df = pd.DataFrame(rows)
    output_df = add_relative_levels(output_df)

    output_path = OUTPUT_DIR / f"{CALL_ID}_acoustic_features.csv"

    output_df.to_csv(output_path, index=False, encoding="utf-8")

    print("Acoustic feature extraction completed.")
    print(f"Output saved to: {output_path}")
    print()
    print(output_df.head(15))


if __name__ == "__main__":
    main()
