from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import db_session, get_project, init_db, list_projects, rows, now_iso
from .normalize import normalize_domain
from .pipeline import collectors_for_profile, project_snapshot, run_collection
from .report import report_html, report_json
from .sample_data import load_demo
from .schemas import ClaimReview, CollectRequest, ProjectCreate
from .scope import host_from_url, is_host_allowed


app = FastAPI(title="Surface Map AI", version="0.1.0")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/projects")
def projects() -> list[dict]:
    with db_session() as db:
        return list_projects(db)


@app.post("/api/projects")
def create_project(payload: ProjectCreate) -> dict:
    official_host = host_from_url(payload.official_website)
    root_domain = normalize_domain(payload.root_domain or official_host)
    allowed = sorted({normalize_domain(value) for value in (payload.allowed_domains or [root_domain]) if value.strip()})
    if not official_host or not allowed or not is_host_allowed(official_host, allowed):
        raise HTTPException(status_code=400, detail="official website host must be inside allowed_domains")
    if payload.mode == "authorized" and not payload.official_website.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="authorized projects require an HTTP(S) official website")
    with db_session() as db:
        from .db import create_project

        return create_project(db, {"organization_name": payload.organization_name.strip(), "official_website": payload.official_website.strip(), "root_domain": root_domain, "allowed_domains": allowed, "aliases": payload.aliases, "brands": payload.brands, "known_social_accounts": payload.known_social_accounts, "authorized_assets": payload.authorized_assets, "mode": payload.mode, "notes": payload.notes.strip()})


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
    return run_collection(project_id, collector_names, payload.demo, payload.profile)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    with db_session() as db:
        existing = db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="project not found")
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
def assets(project_id: str, q: str = Query(""), asset_type: str = Query(""), status: str = Query(""), source: str = Query("")) -> list[dict]:
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
            query += " AND (s.source_url LIKE ? OR s.source_name LIKE ?)"
            params += [f"%{source}%", f"%{source}%"]
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
        return dict(row)


@app.patch("/api/projects/{project_id}/claims/{relationship_id}")
def review_claim(project_id: str, relationship_id: str, payload: ClaimReview) -> dict:
    with db_session() as db:
        existing = db.execute("SELECT id FROM relationships WHERE project_id=? AND id=?", (project_id, relationship_id)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="relationship not found")
        db.execute("UPDATE relationships SET status=?, rationale=COALESCE(?, rationale), verified_by='human_review', reviewed_at=? WHERE project_id=? AND id=?", (payload.status, payload.rationale, now_iso(), project_id, relationship_id))
        row = db.execute("SELECT * FROM relationships WHERE project_id=? AND id=?", (project_id, relationship_id)).fetchone()
        return dict(row)


@app.get("/api/projects/{project_id}/report.json")
def json_report(project_id: str) -> JSONResponse:
    with db_session() as db:
        snapshot = project_snapshot(db, project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="project not found")
    return JSONResponse(report_json(snapshot), headers={"Content-Disposition": f"attachment; filename={project_id}-report.json"})


@app.get("/api/projects/{project_id}/report.html", response_class=HTMLResponse)
def html_report(project_id: str) -> HTMLResponse:
    with db_session() as db:
        snapshot = project_snapshot(db, project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="project not found")
    return HTMLResponse(report_html(snapshot), headers={"Content-Disposition": f"attachment; filename={project_id}-report.html"})
