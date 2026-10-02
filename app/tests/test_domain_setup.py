from unittest.mock import patch
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.jobs import worker
from app.db import db_session
from app.collectors.base import CollectorResult
from app.collectors.social import SocialOSINTCollector


@pytest.fixture
def queued_client(monkeypatch):
    # Keep jobs queued while checking setup transactions and retries.
    monkeypatch.setattr(worker, "run_one", lambda: False)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("entered,host,root,scope", [
    (" Example.ORG. ", "example.org", "example.org", "example.org"),
    ("https://WWW.Example.ORG/", "www.example.org", "example.org", "example.org"),
    ("app.example.co.uk", "app.example.co.uk", "example.co.uk", "app.example.co.uk"),
    ("TÉST.vn", "xn--tst-bma.vn", "xn--tst-bma.vn", "xn--tst-bma.vn"),
])
def test_domain_alone_creates_and_queues(queued_client, entered, host, root, scope):
    response = queued_client.post("/api/projects/setup", json={"domain": entered})
    assert response.status_code == 202, response.text
    result = response.json()
    project = result["project"]
    assert result["created"] is True
    assert project["organization_name"] == host
    assert project["official_website"] == f"https://{host}/"
    assert project["root_domain"] == root
    assert project["allowed_domains"] == [scope]
    assert project["mode"] == "passive"
    assert project["authorized_scopes"] == project["authorized_assets"] == []
    run = queued_client.get(f"/api/projects/{project['id']}/runs/{result['collection']['run_id']}").json()
    assert run["status"] == "queued"
    config = json.loads(run["config_json"])
    assert config["collectors"] == ["passive_web", "dns", "certificate_transparency", "rdap", "social_osint", "ai"]
    assert config["demo"] is False


@pytest.mark.parametrize("payload", [
    {}, {"domain": ""}, {"domain": "localhost"}, {"domain": "*.example.org"},
    {"domain": "127.0.0.1"}, {"domain": "example..org"}, {"domain": "example.org:443"},
    {"domain": "https://user:secret@example.org"}, {"domain": "https://example.org/path"},
    {"domain": "https://example.org/?token=value"}, {"domain": "ftp://example.org"},
    {"domain": "https://example.org:bad"}, {"domain": "example.org", "mode": "authorized"},
])
def test_bad_domain_does_not_create_or_queue(queued_client, payload):
    response = queued_client.post("/api/projects/setup", json=payload)
    assert response.status_code == 422, response.text
    assert queued_client.get("/api/projects").json() == []
    with db_session() as db:
        assert db.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0] == 0


def test_repeated_setup_reuses_project_and_active_job(queued_client):
    first = queued_client.post("/api/projects/setup", json={"domain": "example.org"}).json()
    second = queued_client.post("/api/projects/setup", json={"domain": "EXAMPLE.ORG"}).json()
    assert second["created"] is False
    assert first["project"]["id"] == second["project"]["id"]
    assert first["collection"]["run_id"] == second["collection"]["run_id"]
    with db_session() as db:
        db.execute("UPDATE collection_runs SET status='completed'")
    third = queued_client.post("/api/projects/setup", json={"domain": "example.org"}).json()
    assert third["created"] is False
    assert third["collection"]["run_id"] != first["collection"]["run_id"]
    assert len(queued_client.get("/api/projects").json()) == 1


def test_setup_rolls_back_project_if_queue_fails(queued_client):
    with patch("app.main.enqueue_collection", side_effect=RuntimeError("queue unavailable")):
        with pytest.raises(RuntimeError, match="queue unavailable"):
            queued_client.post("/api/projects/setup", json={"domain": "example.org"})
    assert queued_client.get("/api/projects").json() == []


def test_setup_runs_collectors_social_discovery_and_ai_automatically(monkeypatch):
    content = '<title>Acme</title>Product: Acme Portal helps teams. <a href="https://app.acme.example/">Acme Portal</a><a href="https://www.facebook.com/AcmeRobotics">Facebook</a><a href="https://www.facebook.com/sharer/sharer.php?u=acme.example">Share</a>'
    monkeypatch.setattr("app.collectors.passive.fetch_scoped", lambda *args, **kwargs: ("https://acme.example/", "text/html", content))
    for name in ("DnsCollector", "CertificateTransparencyCollector", "RdapCollector"):
        monkeypatch.setattr(f"app.pipeline.{name}.collect", lambda self, context: CollectorResult(self.name, "skipped", "isolated fixture"))
    # Facebook is a manual-only platform; its official backlink is captured locally.
    monkeypatch.setattr("app.collectors.social.fetch_scoped", lambda *args, **kwargs: pytest.fail("unexpected social network request"))
    with TestClient(app) as client:
        result = client.post("/api/projects/setup", json={"domain": "acme.example"}).json()
        prefix = f"/api/projects/{result['project']['id']}"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            run = client.get(prefix + "/runs/" + result["collection"]["run_id"]).json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(.02)
        assert run["status"] == "completed"
        snapshot = client.get(prefix).json()
        assert snapshot["assets"] and snapshot["sources"] and snapshot["relationships"]
        assert snapshot["model_runs"][0]["provider"] == "rules-demo"
        accounts = snapshot["social_accounts"]
        assert len(accounts) == 1
        assert accounts[0]["profile_url"] == "https://www.facebook.com/AcmeRobotics"
        assert accounts[0]["verification_status"] == "confirmed"
        assert any(log["collector"] == "social_osint" and log["status"] == "ok" for log in run["collectors"])


def test_social_discovery_ignores_out_of_scope_snapshot(queued_client):
    from app.db import insert_source, get_project
    from app.collectors.base import CollectorContext
    result = queued_client.post("/api/projects/setup", json={"domain": "acme.example"}).json()
    with db_session() as db:
        project = get_project(db, result["project"]["id"])
        insert_source(db, project["id"], "website", "external", "https://outside.example/", raw_content='<a href="https://www.facebook.com/Unrelated">Facebook</a>')
        collected = SocialOSINTCollector().collect(CollectorContext(db, project, "test", 1, 0, 0))
        assert collected.status == "skipped"
        assert db.execute("SELECT COUNT(*) FROM social_accounts").fetchone()[0] == 0
