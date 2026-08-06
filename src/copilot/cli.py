#!/usr/bin/env python3
"""Command-line interface for the grounded local copilot."""

from __future__ import annotations

import argparse
import json

from .service import CopilotService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, help="Agent ID or unique agent name")
    parser.add_argument("--stage", default="live", choices=["start", "live", "end"])
    parser.add_argument("--question", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    response = CopilotService().ask(args.question, args.agent, args.stage)
    if args.as_json:
        print(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(response.answer)


if __name__ == "__main__":
    main()
