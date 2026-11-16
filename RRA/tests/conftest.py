import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# RRA was developed standalone as a package named `risk_radar`; in this repo
# the folder is `RRA`. Alias the name so the original test imports resolve.
sys.modules.setdefault("risk_radar", importlib.import_module("RRA"))
