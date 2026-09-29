from __future__ import annotations

import html
import json
from typing import Any


def report_json(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"generated_at": __import__("app.db", fromlist=["now_iso"]).now_iso(), "project": snapshot["project"], "brands": snapshot.get("brands", []), "assets": snapshot["assets"], "entities": snapshot["entities"], "social_accounts": snapshot.get("social_accounts", []), "social_posts": snapshot.get("social_posts", []), "relationships": snapshot["relationships"], "collection_runs": snapshot["runs"], "collector_logs": snapshot["collector_logs"]}


def report_html(snapshot: dict[str, Any]) -> str:
    project = snapshot["project"]
    rows = []
    for rel in snapshot["relationships"]:
        subject = f"{rel['subject_type']}:{rel['subject_id']}"
        object_ = f"{rel['object_type']}:{rel['object_id']}"
        rows.append(f"<tr><td>{html.escape(subject)}</td><td>{html.escape(rel['predicate'])}</td><td>{html.escape(object_)}</td><td>{html.escape(rel.get('relation_class') or 'unknown')}</td><td>{html.escape(rel['status'])}</td><td>{rel['confidence']:.2f}</td><td>{html.escape(rel.get('source_url') or '')}</td><td>{html.escape(rel.get('quote') or '')}</td></tr>")
    asset_rows = "".join(f"<tr><td>{html.escape(a['asset_type'])}</td><td>{html.escape(a['display_value'])}</td><td>{html.escape(a['status'])}</td><td>{html.escape(a.get('source_url') or '')}</td></tr>" for a in snapshot["assets"])
    social_rows = "".join(f"<tr><td>{html.escape(a['platform'])}</td><td>{html.escape(a['profile_url'])}</td><td>{html.escape(a['verification_status'])}</td><td>{html.escape(a['verification_reason'])}</td></tr>" for a in snapshot.get("social_accounts", []))
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Surface map report - {html.escape(project['organization_name'])}</title><style>body{{font-family:system-ui;margin:2rem;color:#172033}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #ccd3df;padding:.45rem;text-align:left;vertical-align:top}}th{{background:#eef2f7}}code{{white-space:pre-wrap}}</style></head><body><h1>External surface report: {html.escape(project['organization_name'])}</h1><p>Mode: {html.escape(project['mode'])} | Root domain: {html.escape(project['root_domain'])}</p><h2>Assets ({len(snapshot['assets'])})</h2><table><tr><th>Type</th><th>Value</th><th>Status</th><th>Source</th></tr>{asset_rows}</table><h2>Social accounts ({len(snapshot.get('social_accounts', []))})</h2><table><tr><th>Platform</th><th>Profile</th><th>Verification</th><th>Reason</th></tr>{social_rows}</table><h2>Evidence-backed relationships ({len(snapshot['relationships'])})</h2><table><tr><th>Subject</th><th>Predicate</th><th>Object</th><th>Class</th><th>Status</th><th>Confidence</th><th>Source URL</th><th>Evidence</th></tr>{''.join(rows)}</table><h2>Machine-readable export</h2><pre><code>{html.escape(json.dumps(report_json(snapshot), ensure_ascii=False, indent=2))}</code></pre></body></html>"""
