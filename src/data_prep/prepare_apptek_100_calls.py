from pathlib import Path
import re
import shutil
import pandas as pd
from huggingface_hub import HfApi, hf_hub_download


# Configuration

DATASET_NAME = "apptek-com/apptek_callcenter_dialogues"

N_CALLS = 100
N_AGENTS = 10
CALLS_PER_AGENT = 10

AGENT_NAMES = [
    "Joyce Martinez",
    "Cesar Recuero",
    "Herminio Lopez",
    "Rogelio Roberts",
    "Anthony Williams",
    "Caballero Rivera",
    "Sharina Scott",
    "Jasury Bethancourt",
    "Daryelis Reid",
    "Laury Garcia",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_AUDIO_DIR = PROJECT_ROOT / "data" / "raw_audio"
METADATA_DIR = PROJECT_ROOT / "data" / "metadata"

OUTPUT_METADATA_PATH = METADATA_DIR / "calls_metadata.csv"


# Helpers

def validate_configuration():
    if len(AGENT_NAMES) != N_AGENTS:
        raise ValueError(
            f"Expected {N_AGENTS} agent names, but found {len(AGENT_NAMES)}."
        )

    if N_CALLS != N_AGENTS * CALLS_PER_AGENT:
        raise ValueError(
            "N_CALLS must equal N_AGENTS * CALLS_PER_AGENT."
        )


def parse_call_id_and_channel(file_path: str) -> tuple[str, str]:
    """Extract the call ID and channel from an audio filename."""

    filename = Path(file_path).name
    stem = Path(filename).stem

    match = re.match(r"(.+)_(channel[12])$", stem)

    if not match:
        raise ValueError(f"Could not parse call_id/channel from filename: {filename}")

    call_id = match.group(1)
    channel = match.group(2)

    return call_id, channel


def get_agent_id(call_index: int) -> str:
    """Map a zero-based call index to an agent ID."""

    agent_number = (call_index // CALLS_PER_AGENT) + 1
    return f"Agent_{agent_number:03d}"


def get_agent_name(call_index: int) -> str:
    agent_index = call_index // CALLS_PER_AGENT
    return AGENT_NAMES[agent_index]


def clean_folder_name(name: str) -> str:
    """Convert an agent name to a filesystem-safe folder name."""

    name = name.strip()
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    name = name.strip("_")

    return name


def is_audio_file(file_path: str) -> bool:
    return file_path.lower().endswith(".wav")


# Entry point

def main():
    validate_configuration()

    RAW_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Listing files from Hugging Face dataset repo...")

    api = HfApi()

    repo_files = api.list_repo_files(
        repo_id=DATASET_NAME,
        repo_type="dataset",
    )

    audio_files = [file for file in repo_files if is_audio_file(file)]

    if not audio_files:
        raise ValueError("No WAV files found in the dataset repository.")

    print(f"Total WAV files found: {len(audio_files)}")

    # Group channel1/channel2 files by call_id
    calls = {}

    for file_path in audio_files:
        try:
            call_id, channel = parse_call_id_and_channel(file_path)
        except ValueError:
            continue

        if call_id not in calls:
            calls[call_id] = {}

        calls[call_id][channel] = file_path

    complete_calls = [
        {
            "call_id": call_id,
            "channel1_file": channels["channel1"],
            "channel2_file": channels["channel2"],
        }
        for call_id, channels in calls.items()
        if "channel1" in channels and "channel2" in channels
    ]

    complete_calls = sorted(complete_calls, key=lambda x: x["call_id"])

    if len(complete_calls) < N_CALLS:
        raise ValueError(
            f"Only found {len(complete_calls)} complete calls. "
            f"Expected at least {N_CALLS}."
        )

    selected_calls = complete_calls[:N_CALLS]

    metadata_rows = []

    print(f"Downloading and organizing {N_CALLS} complete calls...")

    for idx, call in enumerate(selected_calls):
        call_id = call["call_id"]

        agent_id = get_agent_id(idx)
        agent_name = get_agent_name(idx)
        agent_call_number = (idx % CALLS_PER_AGENT) + 1

        agent_folder_name = f"{agent_id}_{clean_folder_name(agent_name)}"
        agent_dir = RAW_AUDIO_DIR / agent_folder_name
        agent_dir.mkdir(parents=True, exist_ok=True)

        channel1_output = agent_dir / f"{call_id}_channel1.wav"
        channel2_output = agent_dir / f"{call_id}_channel2.wav"

        print(
            f"[{idx + 1:03d}/{N_CALLS}] "
            f"{call_id} → {agent_id} | {agent_name}"
        )

        channel1_cache_path = hf_hub_download(
            repo_id=DATASET_NAME,
            filename=call["channel1_file"],
            repo_type="dataset",
        )

        channel2_cache_path = hf_hub_download(
            repo_id=DATASET_NAME,
            filename=call["channel2_file"],
            repo_type="dataset",
        )

        shutil.copyfile(channel1_cache_path, channel1_output)
        shutil.copyfile(channel2_cache_path, channel2_output)

        metadata_rows.append(
            {
                "call_id": call_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_folder": agent_folder_name,
                "agent_call_number": agent_call_number,
                "channel1_path": str(channel1_output.relative_to(PROJECT_ROOT)),
                "channel2_path": str(channel2_output.relative_to(PROJECT_ROOT)),
                "channel1_speaker_assumption": "agent",
                "channel2_speaker_assumption": "customer",
                "source_dataset": DATASET_NAME,
                "source_channel1_file": call["channel1_file"],
                "source_channel2_file": call["channel2_file"],
            }
        )

    metadata_df = pd.DataFrame(metadata_rows)
    metadata_df.to_csv(OUTPUT_METADATA_PATH, index=False, encoding="utf-8")

    print()
    print("Dataset preparation completed.")
    print(f"Metadata saved to: {OUTPUT_METADATA_PATH}")
    print()
    print(metadata_df.head(15))


if __name__ == "__main__":
    main()
