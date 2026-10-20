"""Export an immutable, hash-verified fixed-window training dataset."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.paths import VAR_DIR  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.ml.dataset import export_dataset  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=["BLUESKY", "MASTODON"])
    parser.add_argument("--directory", type=Path, default=VAR_DIR / "datasets/ml")
    args = parser.parse_args()
    with SessionLocal() as db:
        result = export_dataset(db, args.directory, platform=args.platform)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
