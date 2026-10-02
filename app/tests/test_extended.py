from __future__ import annotations

import copy
import hashlib
import json
import time
import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import db_session, init_db, insert_source, upsert_asset, get_project
from app.main import app
from app.normalize import normalize_domain, normalize_url, registered_domain
from app.scope import authorized_target, public_addresses
from app.collectors.base import CollectorContext
from app.ai.service import run_ai_enrichment
from app.schemas import ModelOutput, ModelRelationship
from scripts.evaluate import scores, evaluate_snapshot


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def demo(client):
    response = client.post("/api/demo/load")
    assert response.status_code == 200
    return response.json()["project_id"]


def project(client, **values):
    response = client.post("/api/projects", json={"organization_name":"Example Org", "official_website":"https://example.org", **values})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("path", ["/", "/api/health", "/openapi.json", "/docs", "/redoc", "/api/projects"])
def test_public_routes(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/static/app.js", "/static/styles.css", "/static/extra.css"])
def test_backend_does_not_serve_frontend(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("origin,allowed", [("http://127.0.0.1:2222", True), ("http://localhost:2222", True), ("http://outside.example:2222", False)])
def test_frontend_cors_preflight(client, origin, allowed):
    response = client.options("/api/projects", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)


@pytest.mark.parametrize("suffix", ["", "/assets", "/social", "/relationships", "/graph", "/report.json", "/report.html", "/report.csv", "/runs", "/runs/missing", "/sources/missing", "/assets/missing", "/claims/missing"])
def test_missing_project_routes(client, suffix):
    assert client.get("/api/projects/missing" + suffix).status_code == 404


@pytest.mark.parametrize("values", [
    {"organization_name":"  "}, {"official_website":"ftp://example.org"},
    {"official_website":"https://user:password@example.org"},
    {"official_website":"https://example.org:99999"},
    {"allowed_domains":["*.example.org"]}, {"allowed_domains":["example..org"]},
    {"mode":"unknown"}, {"unexpected":"field"},
    {"authorized_scopes":[{"kind":"cidr","value":"wrong"}]},
    {"authorized_scopes":[{"kind":"hostname","value":"example.org","expires_at":"2025-01-01T00:00:00"}]},
])
def test_input_validation(client, values):
    response = client.post("/api/projects", json={"organization_name":"Example Org","official_website":"https://example.org",**values})
    assert response.status_code == 422, response.text


def test_scope_mismatch_and_review_validation(client, demo):
    assert client.post("/api/projects", json={"organization_name":"Other Org","official_website":"https://outside.example","allowed_domains":["example.org"]}).status_code == 400
    assert client.post("/api/projects/missing/collect", json={}).status_code == 404
    assert client.delete("/api/projects/missing").status_code == 404
    assert client.patch(f"/api/projects/{demo}/claims/missing",json={"status":"rejected"}).status_code == 404
    assert client.post(f"/api/projects/{demo}/collect",json={"profile":"wrong"}).status_code == 422
    rel = client.get(f"/api/projects/{demo}/relationships").json()[0]["id"]
    assert client.patch(f"/api/projects/{demo}/claims/{rel}",json={"status":"wrong"}).status_code == 422


def test_exports_details_filters_and_review_survive_recollection(client, demo):
    snapshot = client.get(f"/api/projects/{demo}").json()
    rel = next(r["id"] for r in snapshot["relationships"] if r["predicate"] == "PRODUCT_USES_WEBSITE")
    assert client.patch(f"/api/projects/{demo}/claims/{rel}",json={"status":"rejected","rationale":"Human rejection","reviewer":"tester"}).status_code == 200
    response = client.post(f"/api/projects/{demo}/collect",json={"collectors":["ai"],"background":False})
    assert response.status_code == 200
    reviewed = client.get(f"/api/projects/{demo}/claims/{rel}").json()
    assert reviewed["status"] == "rejected"
    assert reviewed["rationale"] == "Human rejection"
    assert reviewed["reviews"][0]["reviewer"] == "tester"
    assert len(reviewed["evidence_history"]) >= 2
    source = client.get(f"/api/projects/{demo}/sources/{snapshot['sources'][0]['id']}").json()
    assert hashlib.sha256(source["raw_content"].encode()).hexdigest() == source["content_hash"]
    asset = client.get(f"/api/projects/{demo}/assets/{snapshot['assets'][0]['id']}").json()
    assert asset["observations"]
    filtered = client.get(f"/api/projects/{demo}/assets",params={"q":"app.acme","asset_type":"host","status":"related","source":"facebook"}).json()
    assert len(filtered)==1
    for suffix in ["report.json","report.html","report.csv"]:
        exported = client.get(f"/api/projects/{demo}/{suffix}")
        assert exported.status_code==200
        assert "attachment" in exported.headers["content-disposition"]
    graph = client.get(f"/api/projects/{demo}/graph").json()
    nodes={n["id"] for n in graph["nodes"]}
    assert all(e["source"] in nodes and e["target"] in nodes for e in graph["edges"])


def test_cross_project_ids_are_rejected(client, demo):
    other = project(client)
    snapshot = client.get(f"/api/projects/{demo}").json()
    for suffix, item in [("claims",snapshot["relationships"][0]),("assets",snapshot["assets"][0]),("sources",snapshot["sources"][0]),("runs",snapshot["runs"][0])]:
        assert client.get(f"/api/projects/{other['id']}/{suffix}/{item['id']}").status_code == 404


def test_background_job_progress(client):
    created=project(client)
    response=client.post(f"/api/projects/{created['id']}/collect",json={"collectors":["ai"]})
    assert response.status_code==202
    run_id=response.json()["run_id"]
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        detail=client.get(f"/api/projects/{created['id']}/runs/{run_id}").json()
        if detail["status"] not in {"queued","running"}:
            break
        time.sleep(.05)
    assert detail["status"]=="completed"
    assert detail["collectors"][0]["collector"]=="ai"
    assert client.get(f"/api/projects/{created['id']}/runs").json()
    assert client.delete(f"/api/projects/{created['id']}").status_code==200


def test_duplicate_jobs_and_delete_active_project(client):
    created=project(client)
    from app.jobs import enqueue_collection
    # Insert while worker is stopped so duplicate/delete decisions are deterministic.
    from app.jobs import worker
    worker.stop()
    enqueue_collection(created["id"], ["ai"], False, "standard")
    assert client.post(f"/api/projects/{created['id']}/collect",json={"collectors":["ai"]}).status_code==409
    assert client.delete(f"/api/projects/{created['id']}").status_code==409


@pytest.mark.parametrize("value,expected", [
    ("WWW.Example.COM.","www.example.com"), ("TÉST.vn","xn--tst-bma.vn"),
    ("2001:0db8::1","2001:db8::1"), ("*.Example.com","*.example.com"),
])
def test_domain_normalization(value,expected):
    assert normalize_domain(value)==expected


def test_url_normalization_preserves_semantics():
    assert normalize_url("HTTPS://EXAMPLE.COM:443/A?X=1&x=2#part")=="https://example.com/A?X=1&x=2"
    assert normalize_url("http://[2001:db8::1]:8080/A")=="http://[2001:db8::1]:8080/A"
    assert registered_domain("app.example.co.uk")=="example.co.uk"


def test_scope_expiration_types_and_empty_authorization():
    base={"mode":"authorized","allowed_domains":["example.org","8.8.8.8"],"authorized_assets":[]}
    assert not authorized_target("https://example.org",base)
    exact={**base,"authorized_scopes":[{"kind":"hostname","value":"example.org","allowed_tests":["http"]}]}
    assert authorized_target("https://example.org",exact)
    assert not authorized_target("https://api.example.org",exact)
    assert not authorized_target("https://example.org",exact,"tls")
    expired={**base,"authorized_scopes":[{"kind":"domain","value":"example.org","expires_at":"2020-01-01T00:00:00Z"}]}
    assert not authorized_target("https://api.example.org",expired)
    cidr={**base,"authorized_scopes":[{"kind":"cidr","value":"8.8.8.0/24"}]}
    assert authorized_target("https://8.8.8.8",cidr)
    assert not authorized_target("https://example.org.evil.test",exact)


@pytest.mark.parametrize("addresses", [["127.0.0.1"],["::1"],["8.8.8.8","10.0.0.1"],["8.8.8.8","fe80::1"],["0.0.0.0"]])
def test_all_resolved_addresses_are_checked(monkeypatch,addresses):
    monkeypatch.setattr(socket,"getaddrinfo",lambda *args,**kwargs:[(0,0,0,"",(a,443)) for a in addresses])
    with pytest.raises(ValueError):
        public_addresses("example.org")


def test_scoped_redirect_rechecks_authorized_scope(monkeypatch):
    from app.collectors import http_utils
    connections=[]
    class FakeResponse:
        status=302
        def getheaders(self): return [("Location","https://other.example.org")]
        def getheader(self,key,default=None): return "https://other.example.org" if key=="Location" else default
    class FakeConnection:
        def __init__(self,*args,**kwargs): connections.append(args); self.sock=None
        def request(self,*args,**kwargs): pass
        def getresponse(self): return FakeResponse()
        def close(self): pass
    monkeypatch.setattr(http_utils.http.client,"HTTPConnection",FakeConnection)
    monkeypatch.setattr(http_utils,"public_addresses",lambda *args:["8.8.8.8"])
    monkeypatch.setattr(http_utils.socket,"create_connection",lambda *args:object())
    p={"mode":"authorized","allowed_domains":["example.org"],"authorized_assets":["example.org"]}
    with pytest.raises(ValueError,match="authorized"):
        http_utils.fetch_page("http://example.org",["example.org"],project=p)
    assert len(connections)==1


def test_http_403_is_recorded_and_connections_are_pinned(monkeypatch):
    from app.collectors import http_utils
    targets=[]
    class FakeResponse:
        status=403
        def getheaders(self): return [("Content-Type","text/plain")]
        def getheader(self,key,default=None): return "text/plain" if key=="Content-Type" else default
        def read(self,n): return b"Forbidden"
    class FakeConnection:
        def __init__(self,*args,**kwargs): self.sock=None
        def request(self,*args,**kwargs): pass
        def getresponse(self): return FakeResponse()
        def close(self): pass
    monkeypatch.setattr(http_utils.http.client,"HTTPConnection",FakeConnection)
    monkeypatch.setattr(http_utils,"public_addresses",lambda *args:["8.8.8.8"])
    monkeypatch.setattr(http_utils.socket,"create_connection",lambda target,*args: targets.append(target) or object())
    result=http_utils.fetch_page("http://example.org",["example.org"])
    assert result["status_code"]==403 and result["content"]=="Forbidden"
    assert targets==[("8.8.8.8",80)]


def test_ct_retains_wildcard_and_history(client,monkeypatch):
    from app.collectors.ct import CertificateTransparencyCollector
    payload=[{"id":1,"name_value":"*.example.org\napp.example.org","not_before":"2020","not_after":"2021"}]
    monkeypatch.setattr("app.collectors.ct.fetch_scoped",lambda *args,**kwargs:("", "application/json",json.dumps(payload)))
    created=project(client)
    with db_session() as db:
        result=CertificateTransparencyCollector().collect(CollectorContext(db,created,"test"))
        assert result.records_count==2
        assert db.execute("SELECT id FROM assets WHERE asset_type='wildcard'").fetchone()
        assert db.execute("SELECT id FROM relationships WHERE predicate='certificate_contains'").fetchone()


def test_dns_types_and_relations(client,monkeypatch):
    from app.collectors.dns import DnsCollector
    import dns.resolver
    answers={"A":["8.8.8.8"],"AAAA":["2001:4860:4860::8888"],"CNAME":["cdn.example.net."],"MX":["10 mail.example.org."],"NS":["ns.example.org."]}
    class Answer(list): rrset=SimpleNamespace(ttl=60)
    class Resolver:
        def resolve(self,host,kind):
            if host.startswith("wildcard-"): raise dns.resolver.NXDOMAIN()
            return Answer(SimpleNamespace(to_text=lambda value=value:value) for value in answers[kind])
    monkeypatch.setattr("app.collectors.dns.dns.resolver.Resolver",Resolver)
    created=project(client)
    with db_session() as db:
        result=DnsCollector().collect(CollectorContext(db,created,"test"))
        assert result.records_count==5
        types={json.loads(r["attributes_json"])["type"] for r in db.execute("SELECT attributes_json FROM assets WHERE asset_type='dns_record'")}
        assert types==set(answers)
        assert len(db.execute("SELECT id FROM relationships").fetchall())==3


def test_rdap_enrichment_and_skip(client,monkeypatch):
    from app.collectors.rdap import RdapCollector
    created=project(client)
    with db_session() as db:
        assert RdapCollector().collect(CollectorContext(db,created,"test")).status=="skipped"
        object.__setattr__(settings,"enable_rdap",True)
        payload={"name":"REGISTRY RECORD","entities":[{"handle":"REG-1","roles":["registrar"]}]}
        monkeypatch.setattr("app.collectors.rdap.fetch_scoped",lambda *a,**k:("", "",json.dumps(payload)))
        assert RdapCollector().collect(CollectorContext(db,created,"test")).status=="ok"
        assert db.execute("SELECT id FROM assets WHERE asset_type='registrar'").fetchone()


def test_passive_and_authorized_collectors(client,monkeypatch):
    from app.collectors.passive import PassiveWebCollector
    from app.collectors.active import AuthorizedHttpCollector
    html='<title>Example</title><a href="https://app.example.org/Search?X=1">App</a>'
    monkeypatch.setattr("app.collectors.passive.fetch_scoped",lambda *a,**k:("https://example.org/","text/html",html))
    monkeypatch.setattr("app.collectors.active.fetch_page",lambda *a,**k:{"url":a[0],"content_type":"text/html","content":"<title>Example</title>","status_code":403})
    created=project(client,mode="authorized",authorized_assets=["example.org"])
    with db_session() as db:
        assert PassiveWebCollector().collect(CollectorContext(db,created,"test")).status=="ok"
        assert AuthorizedHttpCollector().collect(CollectorContext(db,created,"test",request_delay=0)).records_count==1


def test_tls_capture_and_failure(client,monkeypatch):
    from app.collectors.tls import TlsCollector
    monkeypatch.setattr("app.collectors.tls.public_addresses",lambda *a:["8.8.8.8"])
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def getpeercert(self): return {"subjectAltName":[("DNS","app.example.org")]}
        def version(self): return "TLSv1.3"
        def cipher(self): return ("TLS_AES_256_GCM_SHA384","TLSv1.3",256)
    monkeypatch.setattr("app.collectors.tls.socket.create_connection",lambda *a,**k:Connection())
    monkeypatch.setattr("app.collectors.tls.ssl.create_default_context",lambda:SimpleNamespace(wrap_socket=lambda *a,**k:Connection()))
    created=project(client,mode="authorized",authorized_assets=["example.org"])
    with db_session() as db:
        assert TlsCollector().collect(CollectorContext(db,created,"test")).records_count==1
        assert db.execute("SELECT id FROM assets WHERE asset_type='certificate'").fetchone()
    def fail(*a,**k): raise OSError("TLS failed")
    monkeypatch.setattr("app.collectors.tls.socket.create_connection",fail)
    with db_session() as db:
        assert TlsCollector().collect(CollectorContext(db,created,"test")).status=="error"
        assert db.execute("SELECT id FROM sources WHERE source_type='probe_error'").fetchone()


def test_unknown_entity_model_ref_cannot_create_dangling_graph(client,monkeypatch):
    created=project(client)
    with db_session() as db:
        source=insert_source(db,created["id"],"website","test",raw_content="Known exact quote.")
        asset=upsert_asset(db,created["id"],"host","example.org","example.org",source_id=source)
        class Fake:
            name="fake"
            def analyze(self,*a): return ModelOutput(relationships=[ModelRelationship(subject_type="entity",subject_ref="entity:invented",predicate="uses_domain",object_type="asset",object_ref=f"asset:{asset}",evidence_source_id=source,evidence_quote="Known exact quote.",confidence=.99)])
        result=run_ai_enrichment(db,created,Fake())
        assert result["relationships_needs_review"]==1
        assert not db.execute("SELECT id FROM relationships").fetchone()
        assert db.execute("SELECT id FROM model_runs").fetchone()


def test_evaluation_penalizes_false_positives(client,demo):
    snapshot=client.get(f"/api/projects/{demo}").json()
    truth=json.loads(__import__("pathlib").Path("data/evaluation_ground_truth.json").read_text(encoding="utf-8"))
    baseline=evaluate_snapshot(snapshot,truth)
    snapshot["assets"].append({"id":"false","asset_type":"host","canonical_value":"unrelated.example","status":"confirmed"})
    changed=evaluate_snapshot(snapshot,truth)
    assert changed["asset_scores"]["precision"] < baseline["asset_scores"]["precision"]
    assert changed["asset_scores"]["false_positive"]==baseline["asset_scores"]["false_positive"]+1
    assert scores(set(),set())["f1"]==0


def test_project_delete_cascades_all_tables(client,demo):
    assert client.delete(f"/api/projects/{demo}").status_code==200
    with db_session() as db:
        for table in ["sources","assets","entities","evidence","relationships","observations","reviews","model_runs","collection_runs","social_accounts","social_posts"]:
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?",(demo,)).fetchone()[0]==0


def test_asset_classification_is_independent_and_preserved(client,demo):
    asset=client.get(f'/api/projects/{demo}/assets').json()[0]
    response=client.patch(f'/api/projects/{demo}/assets/{asset["id"]}',json={'classification':'third_party','rationale':'Evidence shows a supplier','reviewer':'tester'})
    assert response.status_code==200
    client.post('/api/demo/load')
    updated=client.get(f'/api/projects/{demo}/assets/{asset["id"]}').json()
    assert updated['classification']=='third_party'
    assert updated['status']==asset['status']
    assert updated['reviews'][0]['previous_classification']=='candidate'
    assert client.patch(f'/api/projects/{demo}/assets/missing',json={'classification':'candidate','rationale':'Test'}).status_code==404
    assert client.patch(f'/api/projects/{demo}/assets/{asset["id"]}',json={'classification':'bad','rationale':'Test'}).status_code==422


def test_source_chunks_reconstruct_snapshot(client,demo):
    snapshot=client.get(f'/api/projects/{demo}').json()
    source=client.get(f'/api/projects/{demo}/sources/{snapshot["sources"][0]["id"]}').json()
    assert ''.join(chunk['text'] for chunk in source['chunks'])==source['raw_content']
    assert all(source['raw_content'][c['start_offset']:c['end_offset']]==c['text'] for c in source['chunks'])


def test_offline_collect_never_calls_network(client,demo,monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Network collector must not execute in offline mode')
    monkeypatch.setattr('app.collectors.passive.PassiveWebCollector.collect',forbidden)
    result=client.post(f'/api/projects/{demo}/collect',json={'collectors':['passive_web','ai'],'demo':True,'background':False}).json()
    assert result['status']=='completed'
    assert result['collectors'][0]['status']=='skipped'


def test_manual_social_assertion_requires_backlink_or_review(client):
    from app.collectors.social import SocialOSINTCollector
    created=project(client,known_social_accounts=[{'platform':'facebook','url':'https://facebook.com/example','verification_evidence':'The official example.org links this official page.'}])
    with db_session() as db:
        assert SocialOSINTCollector().collect(CollectorContext(db,created,'test')).status=='ok'
        account=db.execute('SELECT verification_status FROM social_accounts').fetchone()
        assert account['verification_status']=='needs_review'
        assert db.execute('SELECT status FROM relationships').fetchone()['status']=='needs_review'


def test_model_http_adapter_request_and_schema(monkeypatch):
    from app.ai.openai_compatible import OpenAICompatibleAdapter
    captures=[]
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return json.dumps({'choices':[{'message':{'content':'{"entities":[],"relationships":[],"explanation":"ok"}'}}]}).encode()
    def fetch(req,timeout): captures.append(req); return Response()
    monkeypatch.setattr('app.ai.openai_compatible.urllib.request.urlopen',fetch)
    adapter=OpenAICompatibleAdapter('https://provider.invalid/v1','fixture-key','fixture-model')
    result=adapter.analyze({'organization_name':'Fixture','root_domain':'example.org'},[],[])
    assert result.explanation=='ok'
    assert captures[0].full_url=='https://provider.invalid/v1/chat/completions'
    body=json.loads(captures[0].data)
    assert 'untrusted' in body['messages'][0]['content']
    with pytest.raises(RuntimeError): OpenAICompatibleAdapter('','','').analyze({},[],[])


def test_rule_product_links_do_not_include_unrelated_same_page_hosts(client,demo):
    rels=client.get(f'/api/projects/{demo}/relationships').json()
    product_rels=[r for r in rels if r['predicate']=='PRODUCT_USES_WEBSITE']
    assert product_rels
    assert all('status.acme.example' not in r['object_label'] and r['object_label']!='acme.example' for r in product_rels)

def test_counter_evidence_retains_both_sources_and_requires_review(client,demo):
    claim=client.get(f'/api/projects/{demo}/claims/'+client.get(f'/api/projects/{demo}/relationships').json()[0]['id']).json()
    prefix=f'/api/projects/{demo}/claims/{claim["id"]}'
    payload={'source_id':claim['evidence_history'][0]['source_id'],'quote':claim['quote'],'role':'refutes'}
    assert client.post(prefix+'/evidence',json=payload).status_code==200
    updated=client.get(prefix).json()
    assert updated['status']=='needs_review'
    assert {e['role'] for e in updated['evidence_history']}=={'supports','refutes'}
    assert client.post(prefix+'/evidence',json={**payload,'quote':'Not present in source'}).status_code==400
    assert client.post(prefix+'/evidence',json={**payload,'source_id':'other-project-source'}).status_code==404

def test_private_lab_requires_global_and_per_scope_opt_in(monkeypatch):
    from app.scope import authorized_private_lab
    project={'mode':'authorized','allowed_domains':['127.0.0.1'],'authorized_scopes':[{'kind':'ip','value':'127.0.0.1','allow_private':True}]}
    assert not authorized_private_lab(project,'http://127.0.0.1','http')
    object.__setattr__(settings,'allow_private_lab',True)
    assert authorized_private_lab(project,'http://127.0.0.1','http')
    assert not authorized_private_lab({**project,'authorized_scopes':[]},'http://127.0.0.1','http')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',('127.0.0.1',80))])
    assert public_addresses('127.0.0.1',80,True)==['127.0.0.1']
    with pytest.raises(ValueError):public_addresses('127.0.0.1',80)


def test_metadata_link_local_stays_blocked_in_lab(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',('169.254.169.254',80))])
    with pytest.raises(ValueError):public_addresses('169.254.169.254',80,True)

def test_project_edit_scope_audit_and_missing_ids(client):
    created=project(client)
    payload={'organization_name':'Updated Org','official_website':'https://example.org','mode':'authorized','authorized_scopes':[{'kind':'hostname','value':'example.org','allowed_tests':['tls']}],'aliases':['Updated']}
    response=client.put(f'/api/projects/{created["id"]}',json=payload)
    assert response.status_code==200
    assert response.json()['authorized_scopes'][0]['allowed_tests']==['tls']
    detail=client.get(f'/api/projects/{created["id"]}').json()
    assert json.loads(detail['project_history'][0]['previous_json'])['mode']=='passive'
    assert client.put('/api/projects/missing',json=payload).status_code==404
    assert client.put(f'/api/projects/{created["id"]}',json={**payload,'organization_name':' '}).status_code==422
