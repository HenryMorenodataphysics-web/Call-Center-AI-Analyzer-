from pathlib import Path
import pandas as pd


# Configuration

CALL_ID = "en_CA_Agriculture_1586885"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TRANSCRIPT_PATH = (
    PROJECT_ROOT
    / "data"
    / "transcripts"
    / f"{CALL_ID}_transcript.csv"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "speaker_turns"

CHANNEL_TO_SPEAKER = {
    "channel1": "agent",
    "channel2": "customer",
}


# Entry point

def main():
    if not TRANSCRIPT_PATH.exists():
        raise FileNotFoundError(f"Transcript file not found: {TRANSCRIPT_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    transcript_df = pd.read_csv(TRANSCRIPT_PATH)

    required_columns = [
        "call_id",
        "channel",
        "segment_id",
        "start_time",
        "end_time",
        "text",
    ]

    missing_columns = [
        col for col in required_columns if col not in transcript_df.columns
    ]

    if missing_columns:
        raise ValueError(f"Missing columns in transcript CSV: {missing_columns}")

    transcript_df["speaker"] = transcript_df["channel"].map(CHANNEL_TO_SPEAKER)

    if transcript_df["speaker"].isna().any():
        unknown_channels = transcript_df.loc[
            transcript_df["speaker"].isna(), "channel"
        ].unique()

        raise ValueError(f"Unknown channel mapping: {unknown_channels}")

    speaker_turns_df = transcript_df.sort_values(
        by=["start_time", "end_time"]
    ).reset_index(drop=True)

    speaker_turns_df.insert(1, "turn_id", range(1, len(speaker_turns_df) + 1))

    speaker_turns_df = speaker_turns_df[
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

    output_path = OUTPUT_DIR / f"{CALL_ID}_speaker_turns.csv"

    speaker_turns_df.to_csv(output_path, index=False, encoding="utf-8")

    print("Speaker assignment completed.")
    print(f"Output saved to: {output_path}")
    print()
    print(speaker_turns_df.head(15))


if __name__ == "__main__":
    main()
