"""Run frontend logic checks against an isolated, synthetic project snapshot."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "BE"))


def main():
    with tempfile.TemporaryDirectory(prefix="surface-ui-logic-") as temporary:
        os.environ["DATABASE_PATH"] = str(Path(temporary) / "fixture.db")
        os.environ["AI_PROVIDER"] = "rules-demo"
        from app.db import db_session, init_db
        from app.sample_data import load_demo
        from app.pipeline import project_snapshot
        init_db()
        loaded = load_demo()
        with db_session() as db:
            snapshot = project_snapshot(db, loaded["project_id"])
        subprocess.run(["node", str(ROOT / "scripts/check_frontend.cjs")],
                       input=json.dumps(snapshot), text=True, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
