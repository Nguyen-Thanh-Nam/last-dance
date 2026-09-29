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
                aliases_json TEXT NOT NULL DEFAULT '[]',
                brands_json TEXT NOT NULL DEFAULT '[]',
                known_social_json TEXT NOT NULL DEFAULT '[]',
                authorized_assets_json TEXT NOT NULL DEFAULT '[]',
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
                relation_class TEXT NOT NULL DEFAULT 'unknown',
                status TEXT NOT NULL DEFAULT 'needs_review',
                confidence REAL NOT NULL DEFAULT 0.5,
                rationale TEXT NOT NULL DEFAULT '',
                evidence_id TEXT REFERENCES evidence(id),
                verified_by TEXT NOT NULL DEFAULT 'system',
                reviewed_at TEXT,
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
            CREATE TABLE IF NOT EXISTS brands (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                source_id TEXT REFERENCES sources(id),
                status TEXT NOT NULL DEFAULT 'discovered',
                created_at TEXT NOT NULL,
                UNIQUE(project_id, canonical_name)
            );
            CREATE TABLE IF NOT EXISTS social_accounts (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                platform TEXT NOT NULL,
                handle TEXT NOT NULL DEFAULT '',
                profile_url TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT 'needs_review',
                verification_reason TEXT NOT NULL DEFAULT '',
                source_id TEXT REFERENCES sources(id),
                collected_at TEXT NOT NULL,
                UNIQUE(project_id, profile_url)
            );
            CREATE TABLE IF NOT EXISTS social_posts (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                social_account_id TEXT REFERENCES social_accounts(id) ON DELETE CASCADE,
                permalink TEXT NOT NULL,
                published_at TEXT,
                collected_at TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                source_id TEXT REFERENCES sources(id),
                UNIQUE(project_id, permalink)
            );
            CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
            CREATE INDEX IF NOT EXISTS idx_entities_project ON entities(project_id);
            CREATE INDEX IF NOT EXISTS idx_relationships_project ON relationships(project_id);
            CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence(project_id);
            """
        )
        _ensure_columns(db, "projects", {
            "aliases_json": "TEXT NOT NULL DEFAULT '[]'",
            "brands_json": "TEXT NOT NULL DEFAULT '[]'",
            "known_social_json": "TEXT NOT NULL DEFAULT '[]'",
            "authorized_assets_json": "TEXT NOT NULL DEFAULT '[]'",
        })
        _ensure_columns(db, "relationships", {
            "relation_class": "TEXT NOT NULL DEFAULT 'unknown'",
            "verified_by": "TEXT NOT NULL DEFAULT 'system'",
            "reviewed_at": "TEXT",
        })


def _ensure_columns(db: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, declaration in columns.items():
        if name not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def row_or_none(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    return dict(row) if row else None


def rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def create_project(db: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    project_id = make_id("prj")
    created_at = now_iso()
    db.execute(
        "INSERT INTO projects(id, organization_name, official_website, root_domain, allowed_domains, mode, notes, aliases_json, brands_json, known_social_json, authorized_assets_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, data["organization_name"], data["official_website"], data["root_domain"], _json(data["allowed_domains"]), data["mode"], data.get("notes", ""), _json(data.get("aliases", [])), _json(data.get("brands", [])), _json(data.get("known_social_accounts", [])), _json(data.get("authorized_assets", [])), created_at),
    )
    return get_project(db, project_id)


def get_project(db: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    row = row_or_none(db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)))
    if row:
        row["allowed_domains"] = json.loads(row["allowed_domains"])
        for key in ("aliases_json", "brands_json", "known_social_json", "authorized_assets_json"):
            output_key = "known_social_accounts" if key == "known_social_json" else key.removesuffix("_json")
            row[output_key] = json.loads(row.pop(key))
    return row


def list_projects(db: sqlite3.Connection) -> list[dict[str, Any]]:
    result = rows(db.execute("SELECT * FROM projects ORDER BY created_at DESC"))
    for row in result:
        row["allowed_domains"] = json.loads(row["allowed_domains"])
        for key in ("aliases_json", "brands_json", "known_social_json", "authorized_assets_json"):
            output_key = "known_social_accounts" if key == "known_social_json" else key.removesuffix("_json")
            row[output_key] = json.loads(row.pop(key))
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


def insert_relationship(db: sqlite3.Connection, project_id: str, subject_type: str, subject_id: str, predicate: str, object_type: str, object_id: str, status: str = "needs_review", confidence: float = 0.5, rationale: str = "", evidence_id: str | None = None, relation_class: str | None = None, verified_by: str = "system", reviewed_at: str | None = None) -> str:
    rel_id = make_id("rel")
    relation_class = relation_class or _relation_class_for_predicate(predicate)
    db.execute(
        """INSERT INTO relationships(id, project_id, subject_type, subject_id, predicate, object_type, object_id, relation_class, status, confidence, rationale, evidence_id, verified_by, reviewed_at, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(project_id, subject_type, subject_id, predicate, object_type, object_id) DO UPDATE SET
             relation_class=excluded.relation_class, status=excluded.status, confidence=excluded.confidence, rationale=excluded.rationale, evidence_id=COALESCE(excluded.evidence_id, relationships.evidence_id), verified_by=excluded.verified_by, reviewed_at=excluded.reviewed_at""",
        (rel_id, project_id, subject_type, subject_id, predicate, object_type, object_id, relation_class, status, max(0.0, min(1.0, confidence)), rationale, evidence_id, verified_by, reviewed_at, now_iso()),
    )
    found = row_or_none(db.execute("SELECT id FROM relationships WHERE project_id=? AND subject_type=? AND subject_id=? AND predicate=? AND object_type=? AND object_id=?", (project_id, subject_type, subject_id, predicate, object_type, object_id)))
    assert found
    return found["id"]


def _relation_class_for_predicate(predicate: str) -> str:
    value = predicate.casefold()
    if "own" in value:
        return "owned"
    if "operat" in value:
        return "operated"
    if "use" in value or "link" in value:
        return "used"
    if "partner" in value:
        return "partner"
    if "mention" in value or "post_" in value:
        return "mentioned"
    return "unknown"


def insert_brand(db: sqlite3.Connection, project_id: str, name: str, canonical_name: str, source_id: str | None = None, status: str = "discovered") -> str:
    brand_id = make_id("brd")
    db.execute("INSERT INTO brands(id, project_id, name, canonical_name, source_id, status, created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(project_id, canonical_name) DO UPDATE SET source_id=COALESCE(excluded.source_id, brands.source_id), status=excluded.status", (brand_id, project_id, name, canonical_name, source_id, status, now_iso()))
    found = row_or_none(db.execute("SELECT id FROM brands WHERE project_id=? AND canonical_name=?", (project_id, canonical_name)))
    assert found
    return found["id"]


def upsert_social_account(db: sqlite3.Connection, project_id: str, platform: str, handle: str, profile_url: str, verification_status: str = "needs_review", verification_reason: str = "", source_id: str | None = None) -> str:
    account_id = make_id("soc")
    db.execute("INSERT INTO social_accounts(id, project_id, platform, handle, profile_url, verification_status, verification_reason, source_id, collected_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id, profile_url) DO UPDATE SET handle=excluded.handle, verification_status=excluded.verification_status, verification_reason=excluded.verification_reason, source_id=COALESCE(excluded.source_id, social_accounts.source_id), collected_at=excluded.collected_at", (account_id, project_id, platform, handle, profile_url, verification_status, verification_reason, source_id, now_iso()))
    found = row_or_none(db.execute("SELECT id FROM social_accounts WHERE project_id=? AND profile_url=?", (project_id, profile_url)))
    assert found
    return found["id"]


def insert_social_post(db: sqlite3.Connection, project_id: str, social_account_id: str, permalink: str, content: str, published_at: str | None = None, source_id: str | None = None) -> str:
    post_id = make_id("pst")
    db.execute("INSERT INTO social_posts(id, project_id, social_account_id, permalink, published_at, collected_at, content, source_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(project_id, permalink) DO UPDATE SET content=excluded.content, published_at=excluded.published_at, source_id=COALESCE(excluded.source_id, social_posts.source_id), collected_at=excluded.collected_at", (post_id, project_id, social_account_id, permalink, published_at, now_iso(), content, source_id))
    found = row_or_none(db.execute("SELECT id FROM social_posts WHERE project_id=? AND permalink=?", (project_id, permalink)))
    assert found
    return found["id"]
