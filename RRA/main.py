"""
Risk Radar Agent — CLI runner.

Usage:
    python -m risk_radar.main <path/to/case.json>

Prints the full RiskRadarOutput as JSON to stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .agent import RiskRadarAgent
from .schema import CaseInput


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python -m risk_radar.main <case.json>", file=sys.stderr)
        return 2

    case_path = Path(argv[1])
    if not case_path.exists():
        print(f"File not found: {case_path}", file=sys.stderr)
        return 2

    with open(case_path) as f:
        case = CaseInput.from_dict(json.load(f))

    agent = RiskRadarAgent()
    output = agent.evaluate(case)

    print(output.to_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
