from pathlib import Path
import numpy as np
import soundfile as sf


# Configuration

CALL_ID = "en_CA_Agriculture_1586885"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_AUDIO_DIR = PROJECT_ROOT / "data" / "raw_audio"

CHANNEL_1_PATH = RAW_AUDIO_DIR / f"{CALL_ID}_channel1.wav"
CHANNEL_2_PATH = RAW_AUDIO_DIR / f"{CALL_ID}_channel2.wav"

OUTPUT_PATH = RAW_AUDIO_DIR / f"{CALL_ID}_stereo_agent_left_customer_right.wav"


# Entry point

def main():
    if not CHANNEL_1_PATH.exists():
        raise FileNotFoundError(f"File not found: {CHANNEL_1_PATH}")

    if not CHANNEL_2_PATH.exists():
        raise FileNotFoundError(f"File not found: {CHANNEL_2_PATH}")

    channel1, sr1 = sf.read(CHANNEL_1_PATH)
    channel2, sr2 = sf.read(CHANNEL_2_PATH)

    if sr1 != sr2:
        raise ValueError(f"Sample rates do not match: {sr1} vs {sr2}")

    min_length = min(len(channel1), len(channel2))

    channel1 = channel1[:min_length]
    channel2 = channel2[:min_length]

    stereo_audio = np.column_stack((channel1, channel2))

    sf.write(
        OUTPUT_PATH,
        stereo_audio,
        sr1
    )

    print("Stereo audio created.")
    print(f"Output saved to: {OUTPUT_PATH}")
    print()
    print("Left channel: agent")
    print("Right channel: customer")


if __name__ == "__main__":
    main()
