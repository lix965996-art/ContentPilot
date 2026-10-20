"""Read-only ML readiness audit; no legacy observation-window fabrication."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.paths import REPORTS_DIR  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.ml.dataset import audit_dataset  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["BLUESKY", "MASTODON"])
    parser.add_argument("--output", type=Path, default=REPORTS_DIR / "ml/readiness.json")
    args = parser.parse_args()
    with SessionLocal() as db:
        _, report = audit_dataset(db, platform=args.platform)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
