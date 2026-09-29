from __future__ import annotations

from .ai.service import run_ai_enrichment
from .db import create_project, db_session, insert_source, upsert_asset
from .normalize import normalize_endpoint, normalize_url, parameter_names


DEMO_HTML = """
<html><head><title>Acme Robotics | Products</title></head>
<body>
<h1>Acme Robotics</h1>
<p>Product: Fleet Console helps operators monitor field robots.</p>
<p>Project: Horizon is the public autonomy research program.</p>
<a href=\"https://app.acme.example/login?next=/dashboard&tenant=acme\">Open Fleet Console</a>
<a href=\"https://status.acme.example/\">Service status</a>
</body></html>
"""


def load_demo() -> dict:
    with db_session() as db:
        existing = db.execute("SELECT id FROM projects WHERE root_domain='acme.example' LIMIT 1").fetchone()
        if existing:
            project_id = existing["id"]
            project = __import__("app.db", fromlist=["get_project"]).get_project(db, project_id)
        else:
            project = create_project(db, {"organization_name": "Acme Robotics", "official_website": "https://acme.example/", "root_domain": "acme.example", "allowed_domains": ["acme.example", "app.acme.example", "status.acme.example"], "mode": "authorized", "notes": "Deterministic offline demo dataset."})
            project_id = project["id"]
        source_id = insert_source(db, project_id, "demo_fixture", "Acme official product page", "https://acme.example/products", "Products", DEMO_HTML, {"fixture": True})
        website_id = upsert_asset(db, project_id, "website", normalize_url("https://acme.example/products"), "https://acme.example/products", "confirmed", source_id, {"fixture": True})
        endpoint = "https://app.acme.example/login?next=&tenant="
        upsert_asset(db, project_id, "endpoint", normalize_endpoint(endpoint), endpoint, "confirmed", source_id, {"parameter_names": parameter_names(endpoint), "fixture": True})
        for host in ["acme.example", "app.acme.example", "status.acme.example"]:
            upsert_asset(db, project_id, "host", host, host, "confirmed" if host == "acme.example" else "related", source_id, {"fixture": True})
        for parameter in ["next", "tenant"]:
            upsert_asset(db, project_id, "parameter", parameter, parameter, "discovered", source_id, {"fixture": True})
        ai_result = run_ai_enrichment(db, project)
        db.execute("INSERT OR IGNORE INTO collection_runs(id, project_id, status, started_at, finished_at, config_json, error_count) VALUES(?,?,?,?,?,?,?)", ("run_demo", project_id, "completed", __import__("app.db", fromlist=["now_iso"]).now_iso(), __import__("app.db", fromlist=["now_iso"]).now_iso(), '{"demo":true}', 0))
        return {"project_id": project_id, "ai": ai_result, "message": "Demo data loaded (rules-demo, deterministic fixture)."}
