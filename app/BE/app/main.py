from __future__ import annotations

import json
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from .db import db_session, get_project, init_db, list_projects, rows, now_iso, make_id, insert_evidence
from .normalize import normalize_domain, registered_domain
from .jobs import enqueue_collection, worker
from .pipeline import collectors_for_profile, project_snapshot, run_collection
from .report import report_html, report_json, report_csv
from .sample_data import load_demo
from .schemas import ClaimReview, CollectRequest, ProjectCreate, AssetReview, EvidenceAttachment, DomainSetup
from .scope import host_from_url, is_host_allowed
from .config import settings


@asynccontextmanager
async def lifespan(app):
    init_db()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="Surface Map AI", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def index() -> dict[str, str]:
    return {"service": "Surface Map AI backend", "docs": "/docs"}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
def projects() -> list[dict]:
    with db_session() as db:
        return list_projects(db)


@app.post("/api/projects")
def create_project(payload: ProjectCreate) -> dict:
    data = project_data(payload)
    with db_session() as db:
        from .db import create_project
        return create_project(db, data)


@app.post("/api/projects/setup", status_code=202)
def setup_domain(payload: DomainSetup) -> dict:
    """Create a domain workspace and queue its standard collection atomically."""
    from .db import create_project as save_project
    domain = payload.domain
    website = f"https://{domain}/"
    marker = "domain-setup-v1"
    with db_session() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT id FROM projects WHERE official_website=? AND mode='passive' AND notes=? ORDER BY created_at LIMIT 1", (website, marker)).fetchone()
        if existing:
            project = get_project(db, existing["id"])
        else:
            data = project_data(ProjectCreate(
                organization_name=domain, official_website=website,
                root_domain=registered_domain(domain),
                allowed_domains=[domain.removeprefix("www.")], notes=marker))
            project = save_project(db, data)
        active = db.execute("SELECT id,status FROM collection_runs WHERE project_id=? AND status IN ('queued','running')", (project["id"],)).fetchone()
        collection = ({"run_id": active["id"], "status": active["status"], "profile": "standard"} if active else
                      enqueue_collection(project["id"], collectors_for_profile(project, "standard"), False, "standard", db=db))
    return {"project": project, "collection": collection, "created": existing is None}


def project_data(payload: ProjectCreate) -> dict:
    official_host = host_from_url(payload.official_website)
    root_domain = normalize_domain(payload.root_domain or registered_domain(official_host))
    allowed = sorted({normalize_domain(value) for value in (payload.allowed_domains or [root_domain]) if value.strip()})
    if not official_host or not allowed or not is_host_allowed(official_host, allowed):
        raise HTTPException(status_code=400, detail="official website host must be inside allowed_domains")
    if payload.mode == "authorized" and not payload.official_website.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="authorized projects require an HTTP(S) official website")
    return {**payload.model_dump(mode="json"), "root_domain": root_domain, "allowed_domains": allowed}


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectCreate) -> dict:
    data = project_data(payload)
    with db_session() as db:
        previous = get_project(db, project_id)
        if not previous:
            raise HTTPException(status_code=404, detail="project not found")
        if db.execute("SELECT id FROM collection_runs WHERE project_id=? AND status IN ('queued','running')", (project_id,)).fetchone():
            raise HTTPException(status_code=409, detail="wait for active collection before changing project scope")
        db.execute("INSERT INTO project_history(id, project_id, changed_at, previous_json, updated_json) VALUES(?,?,?,?,?)", (make_id("change"), project_id, now_iso(), json.dumps(previous), json.dumps(data)))
        db.execute("UPDATE projects SET organization_name=?, official_website=?, root_domain=?, allowed_domains=?, mode=?, notes=?, aliases_json=?, brands_json=?, known_social_json=?, authorized_assets_json=?, authorized_scopes_json=? WHERE id=?", (data["organization_name"], data["official_website"], data["root_domain"], json.dumps(data["allowed_domains"]), data["mode"], data["notes"], json.dumps(data["aliases"]), json.dumps(data["brands"]), json.dumps(data["known_social_accounts"]), json.dumps(data["authorized_assets"]), json.dumps(data["authorized_scopes"]), project_id))
        return get_project(db, project_id)


@app.get("/api/projects/{project_id}")
def project_detail(project_id: str) -> dict:
    with db_session() as db:
        snapshot = project_snapshot(db, project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="project not found")
    return snapshot


@app.post("/api/projects/{project_id}/collect")
def collect(project_id: str, payload: CollectRequest) -> dict:
    with db_session() as db:
        project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    collector_names = collectors_for_profile(project, payload.profile, payload.collectors)
    try:
        if payload.background:
            return JSONResponse(enqueue_collection(project_id, collector_names, payload.demo, payload.profile), status_code=202)
        return run_collection(project_id, collector_names, payload.demo, payload.profile)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="project already has an active collection")


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    with db_session() as db:
        existing = db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="project not found")
        if db.execute("SELECT id FROM collection_runs WHERE project_id=? AND status IN ('queued','running')", (project_id,)).fetchone():
            raise HTTPException(status_code=409, detail="wait for active collection before deleting")
        db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    return {"deleted": project_id}


@app.post("/api/demo/load")
def demo_load() -> dict:
    return load_demo()


@app.get("/api/projects/{project_id}/social")
def social(project_id: str) -> dict:
    with db_session() as db:
        if not get_project(db, project_id):
            raise HTTPException(status_code=404, detail="project not found")
        accounts = rows(db.execute("SELECT a.*, s.source_url, s.source_name FROM social_accounts a LEFT JOIN sources s ON s.id=a.source_id WHERE a.project_id=? ORDER BY a.platform, a.profile_url", (project_id,)))
        posts = rows(db.execute("SELECT p.*, a.platform, a.profile_url, s.source_url AS source_url FROM social_posts p LEFT JOIN social_accounts a ON a.id=p.social_account_id LEFT JOIN sources s ON s.id=p.source_id WHERE p.project_id=? ORDER BY p.collected_at DESC", (project_id,)))
        brands = rows(db.execute("SELECT * FROM brands WHERE project_id=? ORDER BY name", (project_id,)))
        return {"brands": brands, "accounts": accounts, "posts": posts}


@app.get("/api/projects/{project_id}/assets")
def assets(project_id: str, q: str = Query(""), asset_type: str = Query(""), status: str = Query(""), source: str = Query(""), classification: str = Query(""), min_confidence: float = Query(0, ge=0, le=1), observed_after: datetime | None = Query(None)) -> list[dict]:
    with db_session() as db:
        if not get_project(db, project_id):
            raise HTTPException(status_code=404, detail="project not found")
        query = "SELECT a.*, s.source_url, s.source_name FROM assets a LEFT JOIN sources s ON s.id=a.source_id WHERE a.project_id=?"
        params: list[str] = [project_id]
        if q:
            query += " AND (a.display_value LIKE ? OR a.canonical_value LIKE ?)"
            params += [f"%{q}%", f"%{q}%"]
        if asset_type:
            query += " AND a.asset_type=?"
            params.append(asset_type)
        if status:
            query += " AND a.status=?"
            params.append(status)
        if source:
            query += " AND EXISTS (SELECT 1 FROM observations o JOIN sources os ON os.id=o.source_id WHERE o.asset_id=a.id AND (os.source_url LIKE ? OR os.source_name LIKE ?))"
            params += [f"%{source}%", f"%{source}%"]
        if classification:
            query += " AND a.classification=?"
            params.append(classification)
        if min_confidence:
            query += " AND EXISTS (SELECT 1 FROM relationships r WHERE r.project_id=a.project_id AND r.confidence>=? AND ((r.subject_type='asset' AND r.subject_id=a.id) OR (r.object_type='asset' AND r.object_id=a.id)))"
            params.append(min_confidence)
        if observed_after:
            if observed_after.tzinfo is None:
                raise HTTPException(status_code=422, detail="observed_after requires a timezone")
            query += " AND a.last_seen_at>=?"
            params.append(observed_after.astimezone(timezone.utc).isoformat())
        result = rows(db.execute(query + " ORDER BY a.asset_type, a.display_value", params))
        for row in result:
            row["attributes"] = json.loads(row.pop("attributes_json"))
        return result


@app.get("/api/projects/{project_id}/relationships")
def relationships(project_id: str) -> list[dict]:
    with db_session() as db:
        snapshot = project_snapshot(db, project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="project not found")
    labels = {f"entity:{item['id']}": item["display_name"] for item in snapshot["entities"]}
    labels.update({f"asset:{item['id']}": item["display_value"] for item in snapshot["assets"]})
    labels.update({f"social_account:{item['id']}": f"{item['platform']}: {item['profile_url']}" for item in snapshot["social_accounts"]})
    labels.update({f"social_post:{item['id']}": item["permalink"] for item in snapshot["social_posts"]})
    for rel in snapshot["relationships"]:
        rel["subject_label"] = labels.get(f"{rel['subject_type']}:{rel['subject_id']}", rel["subject_id"])
        rel["object_label"] = labels.get(f"{rel['object_type']}:{rel['object_id']}", rel["object_id"])
    return snapshot["relationships"]


@app.get("/api/projects/{project_id}/graph")
def graph(project_id: str) -> dict:
    with db_session() as db:
        snapshot = project_snapshot(db, project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="project not found")
    nodes = [{"id": f"entity:{item['id']}", "label": item["display_name"], "kind": item["entity_type"], "status": item["status"]} for item in snapshot["entities"]]
    nodes += [{"id": f"asset:{item['id']}", "label": item["display_value"], "kind": item["asset_type"], "status": item["status"]} for item in snapshot["assets"]]
    nodes += [{"id": f"social_account:{item['id']}", "label": item["profile_url"], "kind": f"social:{item['platform']}", "status": item["verification_status"]} for item in snapshot["social_accounts"]]
    nodes += [{"id": f"social_post:{item['id']}", "label": item["permalink"], "kind": "social_post", "status": "related"} for item in snapshot["social_posts"]]
    edges = [{"id": rel["id"], "source": f"{rel['subject_type']}:{rel['subject_id']}", "target": f"{rel['object_type']}:{rel['object_id']}", "label": rel["predicate"], "status": rel["status"], "confidence": rel["confidence"]} for rel in snapshot["relationships"]]
    return {"nodes": nodes, "edges": edges}


@app.get("/api/projects/{project_id}/claims/{relationship_id}")
def claim(project_id: str, relationship_id: str) -> dict:
    with db_session() as db:
        row = db.execute("""SELECT r.*, e.quote, e.locator, e.collected_at AS evidence_collected_at, e.validity, e.confidence AS evidence_confidence, s.source_url, s.source_name, s.collected_at AS source_collected_at
            FROM relationships r LEFT JOIN evidence e ON e.id=r.evidence_id LEFT JOIN sources s ON s.id=e.source_id WHERE r.project_id=? AND r.id=?""", (project_id, relationship_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="relationship not found")
        result = dict(row)
        result["evidence_history"] = rows(db.execute("SELECT e.*, ce.role, s.source_url, s.source_name, s.content_hash FROM claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id JOIN sources s ON s.id=e.source_id WHERE ce.relationship_id=?", (relationship_id,)))
        result["reviews"] = rows(db.execute("SELECT * FROM reviews WHERE relationship_id=? ORDER BY reviewed_at, rowid", (relationship_id,)))
        return result


@app.patch("/api/projects/{project_id}/claims/{relationship_id}")
def review_claim(project_id: str, relationship_id: str, payload: ClaimReview) -> dict:
    with db_session() as db:
        existing = db.execute("SELECT id, status FROM relationships WHERE project_id=? AND id=?", (project_id, relationship_id)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="relationship not found")
        db.execute("UPDATE relationships SET status=?, rationale=COALESCE(?, rationale), verified_by='human_review', reviewed_at=? WHERE project_id=? AND id=?", (payload.status, payload.rationale, now_iso(), project_id, relationship_id))
        db.execute("INSERT INTO reviews(id, project_id, relationship_id, previous_status, status, reviewer, rationale, reviewed_at) VALUES(?,?,?,?,?,?,?,?)", (make_id("review"), project_id, relationship_id, existing["status"], payload.status, payload.reviewer, payload.rationale, now_iso()))
        row = db.execute("SELECT * FROM relationships WHERE project_id=? AND id=?", (project_id, relationship_id)).fetchone()
        return dict(row)


@app.get("/api/projects/{project_id}/report.json")
def json_report(project_id: str) -> JSONResponse:
    with db_session() as db:
        snapshot = project_snapshot(db, project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="project not found")
    return JSONResponse(report_json(snapshot), headers={"Content-Disposition": f"attachment; filename={project_id}-report.json"})


@app.post("/api/projects/{project_id}/claims/{relationship_id}/evidence")
def attach_evidence(project_id: str, relationship_id: str, payload: EvidenceAttachment):
    with db_session() as db:
        claim = db.execute("SELECT * FROM relationships WHERE id=? AND project_id=?", (relationship_id, project_id)).fetchone()
        source = db.execute("SELECT * FROM sources WHERE id=? AND project_id=?", (payload.source_id, project_id)).fetchone()
        if not claim or not source:
            raise HTTPException(status_code=404, detail="claim or source not found in this project")
        match = re.search(r"\s+".join(re.escape(part) for part in payload.quote.split()), source["raw_content"])
        if not match:
            raise HTTPException(status_code=400, detail="quote must occur verbatim in the saved source")
        evidence_id = insert_evidence(db, project_id, payload.source_id, match.group(), "human-evidence", 0.5)
        db.execute("INSERT INTO claim_evidence(relationship_id, evidence_id, role) VALUES(?,?,?)", (relationship_id, evidence_id, payload.role))
        if payload.role == "refutes":
            db.execute("UPDATE relationships SET status='needs_review' WHERE id=?", (relationship_id,))
            db.execute("INSERT INTO reviews(id, project_id, relationship_id, previous_status, status, reviewer, rationale, reviewed_at) VALUES(?,?,?,?,?,?,?,?)", (make_id("review"), project_id, relationship_id, claim["status"], "needs_review", payload.reviewer, "Counter-evidence attached; conflicting sources require review.", now_iso()))
        return {"id": evidence_id, "role": payload.role, "relationship_id": relationship_id}


@app.get("/api/projects/{project_id}/report.html", response_class=HTMLResponse)
def html_report(project_id: str) -> HTMLResponse:
    with db_session() as db:
        snapshot = project_snapshot(db, project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="project not found")
    return HTMLResponse(report_html(snapshot), headers={"Content-Disposition": f"attachment; filename={project_id}-report.html"})


@app.get("/api/projects/{project_id}/report.csv")
def csv_report(project_id: str):
    with db_session() as db:
        snapshot = project_snapshot(db, project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="project not found")
    return Response(report_csv(snapshot), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={project_id}-assets.csv"})


@app.get("/api/projects/{project_id}/runs")
def runs(project_id: str):
    with db_session() as db:
        if not get_project(db, project_id):
            raise HTTPException(status_code=404, detail="project not found")
        return rows(db.execute("SELECT * FROM collection_runs WHERE project_id=? ORDER BY started_at DESC, rowid DESC", (project_id,)))


@app.get("/api/projects/{project_id}/runs/{run_id}")
def run_detail(project_id: str, run_id: str):
    with db_session() as db:
        row = db.execute("SELECT * FROM collection_runs WHERE id=? AND project_id=?", (run_id, project_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="run not found")
        return {**dict(row), "collectors": rows(db.execute("SELECT * FROM collector_logs WHERE run_id=? ORDER BY rowid", (run_id,)))}


@app.get("/api/projects/{project_id}/sources/{source_id}")
def source_detail(project_id: str, source_id: str):
    with db_session() as db:
        row = db.execute("SELECT * FROM sources WHERE id=? AND project_id=?", (source_id, project_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        return {**dict(row), "chunks": rows(db.execute("SELECT * FROM source_chunks WHERE source_id=? ORDER BY start_offset", (source_id,)))}


@app.get("/api/projects/{project_id}/assets/{asset_id}")
def asset_detail(project_id: str, asset_id: str):
    with db_session() as db:
        row = db.execute("SELECT * FROM assets WHERE id=? AND project_id=?", (asset_id, project_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="asset not found")
        return {**dict(row), "observations": rows(db.execute("SELECT o.*, s.source_url, s.content_hash FROM observations o LEFT JOIN sources s ON s.id=o.source_id WHERE o.asset_id=? ORDER BY o.rowid", (asset_id,))),
                "reviews": rows(db.execute("SELECT * FROM asset_reviews WHERE asset_id=? ORDER BY rowid", (asset_id,))),
                "relationships": rows(db.execute("SELECT * FROM relationships WHERE project_id=? AND ((subject_type='asset' AND subject_id=?) OR (object_type='asset' AND object_id=?))", (project_id, asset_id, asset_id)))}


@app.patch("/api/projects/{project_id}/assets/{asset_id}")
def review_asset(project_id: str, asset_id: str, payload: AssetReview):
    with db_session() as db:
        row = db.execute("SELECT * FROM assets WHERE id=? AND project_id=?", (asset_id, project_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="asset not found")
        db.execute("INSERT INTO asset_reviews(id, project_id, asset_id, previous_classification, classification, reviewer, rationale, reviewed_at) VALUES(?,?,?,?,?,?,?,?)", (make_id("review"), project_id, asset_id, row["classification"], payload.classification, payload.reviewer, payload.rationale, now_iso()))
        db.execute("UPDATE assets SET classification=? WHERE id=?", (payload.classification, asset_id))
        return {"id": asset_id, **payload.model_dump()}
