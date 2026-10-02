from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "BE"))

from app.db import init_db
from app.sample_data import load_demo


if __name__ == "__main__":
    init_db()
    print(load_demo())
