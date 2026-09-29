from __future__ import annotations

from .ai.service import run_ai_enrichment
from .collectors import CollectorContext, SocialOSINTCollector
from .db import create_project, db_session, get_project, insert_brand, insert_source, upsert_asset
from .normalize import normalize_endpoint, normalize_url, parameter_names


DEMO_HTML = """
<html><head><title>Acme Robotics | Products</title></head>
<body>
<h1>Acme Robotics</h1>
<p>Product: Fleet Console helps operators monitor field robots.</p>
<p>Project: Horizon is the public autonomy research program.</p>
<a href=\"https://app.acme.example/login?next=/dashboard&tenant=acme\">Open Fleet Console</a>
<a href=\"https://status.acme.example/\">Service status</a>
<a href=\"https://facebook.com/acmerobotics\">Official Facebook</a>
</body></html>
"""

DEMO_SOCIAL = {
    "platform": "facebook",
    "handle": "acmerobotics",
    "url": "https://facebook.com/acmerobotics",
    "verification_evidence": "The official website acme.example links to this official Facebook page.",
    "posts": [{
        "permalink": "https://facebook.com/acmerobotics/posts/1001",
        "published_at": "2025-02-01T10:00:00Z",
        "content": "Product: Fleet Console helps operators monitor field robots. Try the app at https://app.acme.example/login?next=/dashboard&tenant=acme.",
    }],
}


def load_demo() -> dict:
    with db_session() as db:
        existing = db.execute("SELECT id FROM projects WHERE root_domain='acme.example' LIMIT 1").fetchone()
        if existing:
            project_id = existing["id"]
            db.execute("UPDATE projects SET known_social_json=?, brands_json=? WHERE id=?", (__import__("json").dumps([DEMO_SOCIAL]), __import__("json").dumps(["Acme Robotics"]), project_id))
            project = get_project(db, project_id)
        else:
            project = create_project(db, {"organization_name": "Acme Robotics", "official_website": "https://acme.example/", "root_domain": "acme.example", "allowed_domains": ["acme.example", "app.acme.example", "status.acme.example"], "brands": ["Acme Robotics"], "known_social_accounts": [DEMO_SOCIAL], "mode": "authorized", "notes": "Deterministic offline demo dataset."})
            project_id = project["id"]
        source_id = insert_source(db, project_id, "demo_fixture", "Acme official product page", "https://acme.example/products", "Products", DEMO_HTML, {"fixture": True})
        website_id = upsert_asset(db, project_id, "website", normalize_url("https://acme.example/products"), "https://acme.example/products", "confirmed", source_id, {"fixture": True})
        endpoint = "https://app.acme.example/login?next=&tenant="
        upsert_asset(db, project_id, "endpoint", normalize_endpoint(endpoint), endpoint, "confirmed", source_id, {"parameter_names": parameter_names(endpoint), "fixture": True})
        for host in ["acme.example", "app.acme.example", "status.acme.example"]:
            upsert_asset(db, project_id, "host", host, host, "confirmed" if host == "acme.example" else "related", source_id, {"fixture": True})
        for parameter in ["next", "tenant"]:
            upsert_asset(db, project_id, "parameter", parameter, parameter, "discovered", source_id, {"fixture": True})
        insert_brand(db, project_id, "Acme Robotics", "acme robotics", source_id, "confirmed")
        # The social collector consumes a fixed public-record fixture, so the demo remains offline.
        social_result = SocialOSINTCollector().collect(CollectorContext(db, project, "run_demo"))
        ai_result = run_ai_enrichment(db, project)
        db.execute("INSERT OR IGNORE INTO collection_runs(id, project_id, status, started_at, finished_at, config_json, error_count) VALUES(?,?,?,?,?,?,?)", ("run_demo", project_id, "completed", __import__("app.db", fromlist=["now_iso"]).now_iso(), __import__("app.db", fromlist=["now_iso"]).now_iso(), '{"demo":true}', 0))
        return {"project_id": project_id, "ai": ai_result, "social": {"status": social_result.status, "records": social_result.records_count}, "message": "Demo data loaded (rules-demo, deterministic fixture with official Facebook -> post -> app URL evidence)."}
