from __future__ import annotations

import html
import json
import csv
import io
from typing import Any


def report_json(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"generated_at": __import__("app.db", fromlist=["now_iso"]).now_iso(), **snapshot,
            "limitations": ["Confidence values are heuristic rankings, not calibrated probabilities.", "Technical DNS/CT/TLS links do not prove ownership.", "Offline fixtures are synthetic; real-model research evaluation is required separately."]}


def report_csv(snapshot: dict[str, Any]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    columns = ["id", "asset_type", "canonical_value", "status", "classification", "source_url", "first_seen_at", "last_seen_at"]
    writer.writerow(columns)
    for asset in snapshot["assets"]:
        values = [str(asset.get(key) or "") for key in columns]
        writer.writerow(["'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value for value in values])
    return "\ufeff" + buffer.getvalue()


def report_html(snapshot: dict[str, Any]) -> str:
    project = snapshot["project"]
    labels = {e["id"]: e["display_name"] for e in snapshot["entities"]}
    labels.update({a["id"]: a["display_value"] for a in snapshot["assets"]})
    labels.update({a["id"]: a["profile_url"] for a in snapshot.get("social_accounts", [])})
    labels.update({p["id"]: p["permalink"] for p in snapshot.get("social_posts", [])})
    rows = []
    for rel in snapshot["relationships"]:
        subject = labels.get(rel['subject_id'], rel['subject_id'])
        object_ = labels.get(rel['object_id'], rel['object_id'])
        rows.append(f"<tr><td>{html.escape(subject)}</td><td>{html.escape(rel['predicate'])}</td><td>{html.escape(object_)}</td><td>{html.escape(rel.get('relation_class') or 'unknown')}</td><td>{html.escape(rel['status'])}</td><td>{rel['confidence']:.2f}</td><td>{html.escape(rel.get('source_url') or '')}</td><td>{html.escape(rel.get('quote') or '')}</td></tr>")
    asset_rows = "".join(f"<tr><td>{html.escape(a['asset_type'])}</td><td>{html.escape(a['display_value'])}</td><td>{html.escape(a['status'])}</td><td>{html.escape(a.get('source_url') or '')}</td></tr>" for a in snapshot["assets"])
    social_rows = "".join(f"<tr><td>{html.escape(a['platform'])}</td><td>{html.escape(a['profile_url'])}</td><td>{html.escape(a['verification_status'])}</td><td>{html.escape(a['verification_reason'])}</td></tr>" for a in snapshot.get("social_accounts", []))
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Surface map report - {html.escape(project['organization_name'])}</title><style>body{{font-family:system-ui;margin:2rem;color:#172033}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #ccd3df;padding:.45rem;text-align:left;vertical-align:top}}th{{background:#eef2f7}}code{{white-space:pre-wrap}}</style></head><body><h1>External surface report: {html.escape(project['organization_name'])}</h1><p>Mode: {html.escape(project['mode'])} | Root domain: {html.escape(project['root_domain'])}</p><h2>Assets ({len(snapshot['assets'])})</h2><table><tr><th>Type</th><th>Value</th><th>Status</th><th>Source</th></tr>{asset_rows}</table><h2>Social accounts ({len(snapshot.get('social_accounts', []))})</h2><table><tr><th>Platform</th><th>Profile</th><th>Verification</th><th>Reason</th></tr>{social_rows}</table><h2>Evidence-backed relationships ({len(snapshot['relationships'])})</h2><table><tr><th>Subject</th><th>Predicate</th><th>Object</th><th>Class</th><th>Status</th><th>Confidence</th><th>Source URL</th><th>Evidence</th></tr>{''.join(rows)}</table><h2>Machine-readable export</h2><pre><code>{html.escape(json.dumps(report_json(snapshot), ensure_ascii=False, indent=2))}</code></pre></body></html>"""
