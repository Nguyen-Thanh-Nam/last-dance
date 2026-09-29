from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import settings


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def connect() -> sqlite3.Connection:
    path = settings.database_path
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db_session() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                organization_name TEXT NOT NULL,
                official_website TEXT NOT NULL,
                root_domain TEXT NOT NULL,
                allowed_domains TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('passive', 'authorized')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS collection_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                config_json TEXT NOT NULL DEFAULT '{}',
                error_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                source_type TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_url TEXT,
                title TEXT NOT NULL DEFAULT '',
                collected_at TEXT NOT NULL,
                raw_content TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                asset_type TEXT NOT NULL,
                canonical_value TEXT NOT NULL,
                display_value TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'discovered',
                source_id TEXT REFERENCES sources(id),
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                attributes_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(project_id, asset_type, canonical_value)
            );
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                entity_type TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'discovered',
                source_id TEXT REFERENCES sources(id),
                attributes_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(project_id, entity_type, canonical_name)
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                quote TEXT NOT NULL,
                locator TEXT NOT NULL DEFAULT '',
                collected_at TEXT NOT NULL,
                validity TEXT NOT NULL DEFAULT 'valid',
                confidence REAL NOT NULL DEFAULT 0.5
            );
            CREATE TABLE IF NOT EXISTS relationships (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'needs_review',
                confidence REAL NOT NULL DEFAULT 0.5,
                rationale TEXT NOT NULL DEFAULT '',
                evidence_id TEXT REFERENCES evidence(id),
                created_at TEXT NOT NULL,
                UNIQUE(project_id, subject_type, subject_id, predicate, object_type, object_id)
            );
            CREATE TABLE IF NOT EXISTS collector_logs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES collection_runs(id) ON DELETE CASCADE,
                collector TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                records_count INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
            CREATE INDEX IF NOT EXISTS idx_entities_project ON entities(project_id);
            CREATE INDEX IF NOT EXISTS idx_relationships_project ON relationships(project_id);
            CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence(project_id);
            """
        )


def row_or_none(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    return dict(row) if row else None


def rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def create_project(db: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    project_id = make_id("prj")
    created_at = now_iso()
    db.execute(
        "INSERT INTO projects(id, organization_name, official_website, root_domain, allowed_domains, mode, notes, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (project_id, data["organization_name"], data["official_website"], data["root_domain"], _json(data["allowed_domains"]), data["mode"], data.get("notes", ""), created_at),
    )
    return get_project(db, project_id)


def get_project(db: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    row = row_or_none(db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)))
    if row:
        row["allowed_domains"] = json.loads(row["allowed_domains"])
    return row


def list_projects(db: sqlite3.Connection) -> list[dict[str, Any]]:
    result = rows(db.execute("SELECT * FROM projects ORDER BY created_at DESC"))
    for row in result:
        row["allowed_domains"] = json.loads(row["allowed_domains"])
    return result


def insert_source(db: sqlite3.Connection, project_id: str, source_type: str, source_name: str, source_url: str | None = None, title: str = "", raw_content: str = "", metadata: dict[str, Any] | None = None) -> str:
    source_id = make_id("src")
    db.execute(
        "INSERT INTO sources(id, project_id, source_type, source_name, source_url, title, collected_at, raw_content, metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
        (source_id, project_id, source_type, source_name, source_url, title, now_iso(), raw_content, _json(metadata or {})),
    )
    return source_id


def upsert_asset(db: sqlite3.Connection, project_id: str, asset_type: str, canonical_value: str, display_value: str, status: str = "discovered", source_id: str | None = None, attributes: dict[str, Any] | None = None) -> str:
    timestamp = now_iso()
    asset_id = make_id("ast")
    db.execute(
        """INSERT INTO assets(id, project_id, asset_type, canonical_value, display_value, status, source_id, first_seen_at, last_seen_at, attributes_json)
           VALUES(?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(project_id, asset_type, canonical_value) DO UPDATE SET
             last_seen_at=excluded.last_seen_at,
             source_id=COALESCE(excluded.source_id, assets.source_id),
             status=CASE WHEN assets.status='confirmed' THEN assets.status ELSE excluded.status END,
             attributes_json=excluded.attributes_json""",
        (asset_id, project_id, asset_type, canonical_value, display_value, status, source_id, timestamp, timestamp, _json(attributes or {})),
    )
    found = row_or_none(db.execute("SELECT id FROM assets WHERE project_id=? AND asset_type=? AND canonical_value=?", (project_id, asset_type, canonical_value)))
    assert found
    return found["id"]


def upsert_entity(db: sqlite3.Connection, project_id: str, entity_type: str, canonical_name: str, display_name: str, status: str = "discovered", source_id: str | None = None, attributes: dict[str, Any] | None = None) -> str:
    entity_id = make_id("ent")
    db.execute(
        """INSERT INTO entities(id, project_id, entity_type, canonical_name, display_name, status, source_id, attributes_json)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(project_id, entity_type, canonical_name) DO UPDATE SET source_id=COALESCE(excluded.source_id, entities.source_id), attributes_json=excluded.attributes_json""",
        (entity_id, project_id, entity_type, canonical_name, display_name, status, source_id, _json(attributes or {})),
    )
    found = row_or_none(db.execute("SELECT id FROM entities WHERE project_id=? AND entity_type=? AND canonical_name=?", (project_id, entity_type, canonical_name)))
    assert found
    return found["id"]


def insert_evidence(db: sqlite3.Connection, project_id: str, source_id: str, quote: str, locator: str = "", confidence: float = 0.5, validity: str = "valid") -> str:
    evidence_id = make_id("evd")
    db.execute(
        "INSERT INTO evidence(id, project_id, source_id, quote, locator, collected_at, validity, confidence) VALUES(?,?,?,?,?,?,?,?)",
        (evidence_id, project_id, source_id, quote[:2000], locator, now_iso(), validity, max(0.0, min(1.0, confidence))),
    )
    return evidence_id


def insert_relationship(db: sqlite3.Connection, project_id: str, subject_type: str, subject_id: str, predicate: str, object_type: str, object_id: str, status: str = "needs_review", confidence: float = 0.5, rationale: str = "", evidence_id: str | None = None) -> str:
    rel_id = make_id("rel")
    db.execute(
        """INSERT INTO relationships(id, project_id, subject_type, subject_id, predicate, object_type, object_id, status, confidence, rationale, evidence_id, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(project_id, subject_type, subject_id, predicate, object_type, object_id) DO UPDATE SET
             status=excluded.status, confidence=excluded.confidence, rationale=excluded.rationale, evidence_id=COALESCE(excluded.evidence_id, relationships.evidence_id)""",
        (rel_id, project_id, subject_type, subject_id, predicate, object_type, object_id, status, max(0.0, min(1.0, confidence)), rationale, evidence_id, now_iso()),
    )
    found = row_or_none(db.execute("SELECT id FROM relationships WHERE project_id=? AND subject_type=? AND subject_id=? AND predicate=? AND object_type=? AND object_id=?", (project_id, subject_type, subject_id, predicate, object_type, object_id)))
    assert found
    return found["id"]
