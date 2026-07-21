"""Seed the stage-1 roles and demo users from the project root."""

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db.seed import main  # noqa: E402


if __name__ == "__main__":
    main()

