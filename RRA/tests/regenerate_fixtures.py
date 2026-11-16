"""Regenerate JSON fixtures with dates relative to 'now'.

Run this before using the CLI so the fixtures produce meaningful
SLA-proximity behavior regardless of when you run the project.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from risk_radar.tests.fixture_builders import (
    clean_case, hold_case, escalate_case,
)
from risk_radar.schema import _serialize

OUT = Path(__file__).parent / "fixtures"
OUT.mkdir(exist_ok=True)

for name, builder in [
    ("case_proceed.json", clean_case),
    ("case_hold.json", hold_case),
    ("case_escalate.json", escalate_case),
]:
    path = OUT / name
    with open(path, "w") as f:
        json.dump(_serialize(builder()), f, indent=2)
    print(f"wrote {path}")
