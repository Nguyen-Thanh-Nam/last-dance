from __future__ import annotations

import time
from typing import Any

from .ai.service import run_ai_enrichment
from .collectors import AuthorizedHttpCollector, CertificateTransparencyCollector, CollectorContext, DnsCollector, PassiveWebCollector, RdapCollector, SocialOSINTCollector
from .config import settings
from .db import db_session, get_project, make_id, now_iso, row_or_none, rows


def run_collection(project_id: str, collector_names: list[str], demo: bool = False) -> dict[str, Any]:
    with db_session() as db:
        project = get_project(db, project_id)
        if not project:
            raise KeyError("project not found")
        run_id = make_id("run")
        started = now_iso()
        db.execute("INSERT INTO collection_runs(id, project_id, status, started_at, config_json) VALUES(?,?,?,?,?)", (run_id, project_id, "running", started, __import__("json").dumps({"collectors": collector_names, "demo": demo, "max_pages": settings.max_crawl_pages, "max_depth": settings.max_crawl_depth, "request_delay_seconds": settings.request_delay_seconds, "allowed_domains": project["allowed_domains"]})))
        context = CollectorContext(db, project, run_id, settings.max_crawl_pages, settings.max_crawl_depth, settings.request_delay_seconds)
        registry = {"passive_web": PassiveWebCollector(), "dns": DnsCollector(), "certificate_transparency": CertificateTransparencyCollector(), "rdap": RdapCollector(), "social_osint": SocialOSINTCollector(), "authorized_http": AuthorizedHttpCollector()}
        result_rows: list[dict[str, Any]] = []
        errors = 0
        for name in collector_names:
            if name == "ai":
                started_at = time.monotonic()
                try:
                    result = run_ai_enrichment(db, project)
                    status, message, count = "ok", f"{result['provider']}: {result['relationships_accepted']} accepted, {result['relationships_needs_review']} needs review", result["relationships_accepted"]
                except Exception as exc:
                    status, message, count = "error", str(exc), 0
                    errors += 1
                duration = int((time.monotonic() - started_at) * 1000)
                db.execute("INSERT INTO collector_logs(id, run_id, collector, status, message, records_count, duration_ms) VALUES(?,?,?,?,?,?,?)", (make_id("log"), run_id, "ai", status, message, count, duration))
                result_rows.append({"collector": "ai", "status": status, "message": message, "records_count": count})
                continue
            collector = registry.get(name)
            if not collector:
                errors += 1
                db.execute("INSERT INTO collector_logs(id, run_id, collector, status, message, records_count, duration_ms) VALUES(?,?,?,?,?,?,?)", (make_id("log"), run_id, name, "error", "unknown collector", 0, 0))
                result_rows.append({"collector": name, "status": "error", "message": "unknown collector", "records_count": 0})
                continue
            started_at = time.monotonic()
            try:
                result = collector.collect(context)
            except Exception as exc:
                result = type("CollectorFailure", (), {"status": "error", "message": str(exc), "records_count": 0})()
            duration = int((time.monotonic() - started_at) * 1000)
            if result.status == "error":
                errors += 1
            db.execute("INSERT INTO collector_logs(id, run_id, collector, status, message, records_count, duration_ms) VALUES(?,?,?,?,?,?,?)", (make_id("log"), run_id, name, result.status, result.message, result.records_count, duration))
            result_rows.append({"collector": name, "status": result.status, "message": result.message, "records_count": result.records_count})
        final_status = "completed_with_errors" if errors else "completed"
        db.execute("UPDATE collection_runs SET status=?, finished_at=?, error_count=? WHERE id=?", (final_status, now_iso(), errors, run_id))
        return {"run_id": run_id, "status": final_status, "error_count": errors, "collectors": result_rows}


def project_snapshot(db, project_id: str) -> dict[str, Any] | None:
    project = get_project(db, project_id)
    if not project:
        return None
    assets = rows(db.execute("SELECT a.*, s.source_url, s.source_name FROM assets a LEFT JOIN sources s ON s.id=a.source_id WHERE a.project_id=? ORDER BY a.asset_type, a.display_value", (project_id,)))
    entities = rows(db.execute("SELECT e.*, s.source_url FROM entities e LEFT JOIN sources s ON s.id=e.source_id WHERE e.project_id=? ORDER BY e.entity_type, e.display_name", (project_id,)))
    relationships = rows(db.execute("""SELECT r.*, e.quote, e.locator, e.confidence AS evidence_confidence, s.source_url, s.source_name
        FROM relationships r LEFT JOIN evidence e ON e.id=r.evidence_id LEFT JOIN sources s ON s.id=e.source_id
        WHERE r.project_id=? ORDER BY r.created_at""", (project_id,)))
    for row in assets + entities:
        if "attributes_json" in row:
            row["attributes"] = __import__("json").loads(row.pop("attributes_json"))
    brands = rows(db.execute("SELECT * FROM brands WHERE project_id=? ORDER BY name", (project_id,)))
    social_accounts = rows(db.execute("SELECT a.*, s.source_url, s.source_name FROM social_accounts a LEFT JOIN sources s ON s.id=a.source_id WHERE a.project_id=? ORDER BY a.platform, a.profile_url", (project_id,)))
    social_posts = rows(db.execute("SELECT p.*, a.platform, a.profile_url, s.source_url AS source_url FROM social_posts p LEFT JOIN social_accounts a ON a.id=p.social_account_id LEFT JOIN sources s ON s.id=p.source_id WHERE p.project_id=? ORDER BY p.collected_at DESC", (project_id,)))
    runs = rows(db.execute("SELECT * FROM collection_runs WHERE project_id=? ORDER BY started_at DESC", (project_id,)))
    logs = rows(db.execute("SELECT l.* FROM collector_logs l JOIN collection_runs r ON r.id=l.run_id WHERE r.project_id=? ORDER BY l.id DESC", (project_id,)))
    return {"project": project, "assets": assets, "entities": entities, "brands": brands, "social_accounts": social_accounts, "social_posts": social_posts, "relationships": relationships, "runs": runs, "collector_logs": logs}
