from pathlib import Path
import pandas as pd
from faster_whisper import WhisperModel


# Configuration

CALL_ID = "en_CA_Agriculture_1586885"

MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_AUDIO_DIR = PROJECT_ROOT / "data" / "raw_audio"
OUTPUT_DIR = PROJECT_ROOT / "data" / "transcripts"

CHANNEL_FILES = {
    "channel1": RAW_AUDIO_DIR / f"{CALL_ID}_channel1.wav",
    "channel2": RAW_AUDIO_DIR / f"{CALL_ID}_channel2.wav",
}


# Transcription function

def transcribe_audio(model, audio_path: Path, call_id: str, channel: str):
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"Transcribing {channel}: {audio_path.name}")

    segments, info = model.transcribe(
        str(audio_path),
        language="en",
        beam_size=5
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


# Entry point

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading faster-whisper model...")
    model = WhisperModel(
        MODEL_SIZE,
        device=DEVICE,
        compute_type=COMPUTE_TYPE
    )

    all_rows = []

    for channel, audio_path in CHANNEL_FILES.items():
        channel_rows = transcribe_audio(
            model=model,
            audio_path=audio_path,
            call_id=CALL_ID,
            channel=channel
        )
        all_rows.extend(channel_rows)

    transcript_df = pd.DataFrame(all_rows)

    output_path = OUTPUT_DIR / f"{CALL_ID}_transcript.csv"
    transcript_df.to_csv(output_path, index=False, encoding="utf-8")

    print("Transcription completed.")
    print(f"Output saved to: {output_path}")
    print()
    print(transcript_df.head(10))


if __name__ == "__main__":
    main()
