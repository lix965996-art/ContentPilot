"""Bounded native model experiment. Use --youtube for the existing public research dataset."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.paths import VAR_DIR  # noqa: E402
from app.ml.dataset import load_dataset  # noqa: E402
from app.ml.public_data import obtain_youtube, prepare_youtube  # noqa: E402
from app.ml.training import train_experiment  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--dataset", type=Path)
    inputs.add_argument("--youtube", action="store_true")
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--models", type=Path, default=VAR_DIR / "models")
    args = parser.parse_args()
    dataset = args.dataset
    if args.youtube:
        result = prepare_youtube(
            obtain_youtube(
                VAR_DIR / "datasets/sources/youtube-duration",
                proxy=settings.outbound_http_proxy.strip() or None,
            ),
            VAR_DIR / "datasets/ml",
        )
        dataset = Path(result["directory"])
    if dataset is None:
        parser.error("请选择冻结数据集或 --youtube")
    rows, manifest = load_dataset(dataset)
    result = train_experiment(rows, manifest, args.models, seed=args.seed)
    print(
        json.dumps(
            {
                "model": result["manifest"],
                "test": result["evaluation"]["test"],
                "improvement": result["evaluation"]["improvement"],
                "directory": result["directory"],
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
