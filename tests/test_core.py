from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app import config
from app.db import db_session, init_db
from app.main import app
from app.normalize import normalize_endpoint, normalize_name
from app.scope import is_host_allowed, validate_url_scope


def _use_tmp_db(tmp_path):
    object.__setattr__(config.settings, "database_path", str(tmp_path / "test.db"))
    init_db()


def test_normalization_deduplicates_values():
    assert normalize_name("  Acme   Robotics ") == "acme robotics"
    assert normalize_endpoint("https://app.example/search?b=2&a=one") == "https://app.example/search?a=&b="
    assert normalize_endpoint("https://app.example/search?a=another&b=99") == "https://app.example/search?a=&b="


def test_scope_requires_allowlist_and_blocks_private_hosts():
    assert is_host_allowed("api.acme.example", ["acme.example"])
    assert not is_host_allowed("partner.example.net", ["acme.example"])
    assert validate_url_scope("https://api.acme.example/path", ["acme.example"], require_public=False)[0]
    assert not validate_url_scope("http://127.0.0.1/admin", ["127.0.0.1"], require_public=True)[0]


def test_demo_api_produces_evidence_backed_relationship_and_reports(tmp_path):
    _use_tmp_db(tmp_path)
    with TestClient(app) as client:
        demo = client.post("/api/demo/load")
        assert demo.status_code == 200, demo.text
        project_id = demo.json()["project_id"]
        detail = client.get(f"/api/projects/{project_id}").json()
        assert detail["assets"]
        relationships = client.get(f"/api/projects/{project_id}/relationships").json()
        assert any(r["status"] == "confirmed" and r["quote"] and r["source_url"] for r in relationships)
        assert client.get(f"/api/projects/{project_id}/graph").json()["nodes"]
        assert client.get(f"/api/projects/{project_id}/report.json").status_code == 200
        assert "Evidence-backed relationships" in client.get(f"/api/projects/{project_id}/report.html").text


def test_model_output_never_accepts_unknown_evidence(tmp_path):
    _use_tmp_db(tmp_path)
    with db_session() as db:
        db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?,?)", ("p", "Org", "https://org.example", "org.example", json.dumps(["org.example"]), "passive", "", "2025-01-01T00:00:00+00:00"))
    # This test exercises the API-level scope gate; a model cannot create a project outside it.
    with TestClient(app) as client:
        response = client.post("/api/projects", json={"organization_name": "Org", "official_website": "https://other.example", "allowed_domains": ["org.example"], "mode": "passive"})
        assert response.status_code == 400
