from __future__ import annotations

import json
import threading

from .db import db_session, make_id, now_iso, get_project
from .pipeline import run_collection


class CollectionWorker:
    """Single process worker backed by a persistent SQLite queue."""
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        self.stop_event.clear()
        with db_session() as db:
            db.execute("UPDATE collection_runs SET status='interrupted', finished_at=? WHERE status='running'", (now_iso(),))
        self.thread = threading.Thread(target=self.loop, name="collection-worker", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=50)

    def loop(self):
        while not self.stop_event.is_set():
            self.run_one()
            self.stop_event.wait(0.2)

    def run_one(self):
        with db_session() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT * FROM collection_runs WHERE status='queued' ORDER BY started_at, rowid LIMIT 1").fetchone()
            if not job:
                return False
            job = dict(job)
            db.execute("UPDATE collection_runs SET status='running' WHERE id=?", (job["id"],))
        try:
            config = json.loads(job["config_json"])
            run_collection(job["project_id"], config["collectors"], config["demo"], config["profile"], job["id"])
        except Exception:
            with db_session() as db:
                db.execute("UPDATE collection_runs SET status='failed', error_count=error_count+1, finished_at=? WHERE id=?", (now_iso(), job["id"]))
        return True


def enqueue_collection(project_id, names, demo, profile, db=None):
    if db is None:
        with db_session() as connection:
            return enqueue_collection(project_id, names, demo, profile, db=connection)
    run_id = make_id("run")
    if not get_project(db, project_id):
        raise KeyError("project not found")
    db.execute("INSERT INTO collection_runs(id, project_id, status, started_at, config_json) VALUES(?,?,?,?,?)",
               (run_id, project_id, "queued", now_iso(), json.dumps({"collectors": names, "demo": demo, "profile": profile})))
    return {"run_id": run_id, "status": "queued", "profile": profile}


worker = CollectionWorker()
