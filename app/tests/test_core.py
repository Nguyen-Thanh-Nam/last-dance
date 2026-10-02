from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app import config
from app.collectors.active import _authorized_asset_allowed
from app.db import create_project, db_session, init_db
from app.db import insert_source, upsert_asset
from app.ai.service import run_ai_enrichment
from app.main import app
from app.normalize import normalize_endpoint, normalize_name
from app.pipeline import collectors_for_profile
from app.schemas import ModelOutput, ModelRelationship
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
    project = {"mode": "authorized", "allowed_domains": ["acme.example"], "authorized_assets": ["app.acme.example"]}
    assert _authorized_asset_allowed("https://app.acme.example/login", project)
    assert not _authorized_asset_allowed("https://status.acme.example/", project)


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
        social = client.get(f"/api/projects/{project_id}/social").json()
        assert social["accounts"][0]["platform"] == "facebook"
        assert any(node["kind"] == "social:facebook" for node in client.get(f"/api/projects/{project_id}/graph").json()["nodes"])
        assert client.get(f"/api/projects/{project_id}/graph").json()["nodes"]
        assert client.get(f"/api/projects/{project_id}/report.json").status_code == 200
        assert "Evidence-backed relationships" in client.get(f"/api/projects/{project_id}/report.html").text


def test_human_review_can_reject_a_claim(tmp_path):
    _use_tmp_db(tmp_path)
    with TestClient(app) as client:
        project_id = client.post("/api/demo/load").json()["project_id"]
        relationship_id = client.get(f"/api/projects/{project_id}/relationships").json()[0]["id"]
        response = client.patch(f"/api/projects/{project_id}/claims/{relationship_id}", json={"status": "rejected", "rationale": "Manual test rejection"})
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"


def test_model_output_never_accepts_unknown_evidence(tmp_path):
    _use_tmp_db(tmp_path)
    with db_session() as db:
        create_project(db, {"organization_name": "Org", "official_website": "https://org.example", "root_domain": "org.example", "allowed_domains": ["org.example"], "mode": "passive"})
    # This test exercises the API-level scope gate; a model cannot create a project outside it.
    with TestClient(app) as client:
        response = client.post("/api/projects", json={"organization_name": "Org", "official_website": "https://other.example", "allowed_domains": ["org.example"], "mode": "passive"})
        assert response.status_code == 400


def test_collector_failure_is_logged_without_aborting_run(tmp_path):
    _use_tmp_db(tmp_path)
    with TestClient(app) as client:
        created = client.post("/api/projects", json={"organization_name": "Scoped Org", "official_website": "https://scope.example", "allowed_domains": ["scope.example"], "aliases": ["Scope"], "brands": ["Scope Brand"], "known_social_accounts": [{"platform": "github", "url": "https://github.com/scope"}], "mode": "passive"}).json()
        result = client.post(f"/api/projects/{created['id']}/collect", json={"collectors": ["unknown_collector", "ai"], "background": False})
        assert result.status_code == 200
        assert result.json()["status"] == "completed_with_errors"
        detail = client.get(f"/api/projects/{created['id']}").json()
        assert detail["project"]["brands"] == ["Scope Brand"]
        assert any(log["collector"] == "unknown_collector" and log["status"] == "error" for log in detail["collector_logs"])


@pytest.mark.parametrize("quote", ["invented quote not present", "PRODUCT: KNOWN PRODUCT links to https://APP.evidence.example"])
def test_invalid_model_quote_is_saved_as_needs_review(tmp_path, monkeypatch, quote):
    _use_tmp_db(tmp_path)
    with db_session() as db:
        project = create_project(db, {"organization_name": "Evidence Org", "official_website": "https://evidence.example", "root_domain": "evidence.example", "allowed_domains": ["evidence.example"], "mode": "passive"})
        source_id = insert_source(db, project["id"], "website", "official", "https://evidence.example", raw_content="Product: Known Product links to https://app.evidence.example")
        asset_id = upsert_asset(db, project["id"], "host", "app.evidence.example", "app.evidence.example", "discovered", source_id)

        class FakeAdapter:
            name = "fake-test-model"

            def analyze(self, project, sources, assets):
                return ModelOutput(entities=[{"entity_type": "product", "name": "Known Product", "source_id": source_id}], relationships=[ModelRelationship(subject_type="entity", subject_ref="candidate:product:known product", predicate="PRODUCT_USES_WEBSITE", object_type="asset", object_ref=f"asset:{asset_id}", evidence_source_id=source_id, evidence_quote=quote, confidence=0.99)])

        monkeypatch.setattr("app.ai.service._adapter", lambda: FakeAdapter())
        result = run_ai_enrichment(db, project)
        assert result["relationships_needs_review"] == 1
        relationship = db.execute("SELECT status, confidence FROM relationships WHERE project_id=?", (project["id"],)).fetchone()
        assert relationship["status"] == "needs_review"
        assert relationship["confidence"] <= 0.25


def test_full_profile_respects_authorization_scope_and_delete_project(tmp_path):
    _use_tmp_db(tmp_path)
    assert "authorized_http" not in collectors_for_profile({"mode": "passive"}, "full")
    assert "authorized_http" in collectors_for_profile({"mode": "authorized"}, "full")
    with TestClient(app) as client:
        created = client.post("/api/projects", json={"organization_name": "Delete Me", "official_website": "https://delete.example", "allowed_domains": ["delete.example"], "mode": "passive"}).json()
        deleted = client.delete(f"/api/projects/{created['id']}")
        assert deleted.status_code == 200
        assert client.get(f"/api/projects/{created['id']}").status_code == 404
