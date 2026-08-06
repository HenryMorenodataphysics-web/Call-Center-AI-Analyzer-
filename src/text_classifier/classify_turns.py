from pathlib import Path
import re
import pandas as pd
from transformers import pipeline


# Configuration

CALL_ID = "en_CA_Agriculture_1586885"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "speaker_turns"
    / f"{CALL_ID}_speaker_turns.csv"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "text_analysis"

SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"


# Rule-based detectors

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


# Entry point

def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Speaker turns file not found: {INPUT_PATH}")

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
        raise ValueError(f"Missing columns in speaker turns CSV: {missing_columns}")

    print("Loading Hugging Face sentiment model...")
    sentiment_pipeline = pipeline(
        task="sentiment-analysis",
        model=SENTIMENT_MODEL,
        tokenizer=SENTIMENT_MODEL,
    )

    results = []

    print("Classifying turns...")

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

        results.append(
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

    output_df = pd.DataFrame(results)

    output_path = OUTPUT_DIR / f"{CALL_ID}_text_analysis.csv"
    output_df.to_csv(output_path, index=False, encoding="utf-8")

    print("Text classification completed.")
    print(f"Output saved to: {output_path}")
    print()
    print(output_df.head(15))


if __name__ == "__main__":
    main()
