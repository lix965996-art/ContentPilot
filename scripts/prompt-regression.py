import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.prompt_regression.evaluator import run_regression  # noqa: E402

print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
