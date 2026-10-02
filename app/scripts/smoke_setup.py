"""Test the one-domain workflow with real curl and an isolated offline fixture server."""
from pathlib import Path
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is required")
    checks = []
    with tempfile.TemporaryDirectory(prefix="surface-domain-curl-") as temporary:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = {**os.environ, "DATABASE_PATH": str(Path(temporary) / "setup.db"),
               "AI_PROVIDER": "rules-demo", "ENABLE_RDAP": "false", "REQUEST_DELAY_SECONDS": "0",
               "GOOGLE_CSE_API_KEY": "", "GOOGLE_CSE_ID": "",
               "PYTHONPATH": str(ROOT / "BE"), "PYTHONDONTWRITEBYTECODE": "1"}
        with (Path(temporary) / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "setup_smoke_app:app", "--app-dir",
                str(ROOT / "tests"), "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT,
                env=env, stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        raise RuntimeError("Fixture server exited")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=.2):
                            break
                    except OSError:
                        time.sleep(.1)

                def request(method, route, payload=None, expected=200):
                    body = Path(temporary) / "response"
                    command = [curl, "--silent", "--show-error", "--noproxy", "*", "--max-time", "15",
                               "-X", method, "-o", str(body), "-w", "%{http_code}"]
                    if payload is not None:
                        data = Path(temporary) / "request.json"
                        data.write_text(json.dumps(payload), encoding="utf-8")
                        command.extend(["-H", "Content-Type: application/json", "--data-binary", "@" + str(data)])
                    command.append(f"http://127.0.0.1:{port}{route}")
                    response = subprocess.run(command, capture_output=True, text=True, check=True)
                    assert response.stdout == str(expected), (route, response.stdout, body.read_text())
                    checks.append({"method": method, "path": route, "status": expected})
                    content = body.read_text(encoding="utf-8-sig")
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return content

                request("GET", "/api/health")
                result = request("POST", "/api/projects/setup", {"domain": "acme.example"}, 202)
                assert result["project"]["allowed_domains"] == ["acme.example"]
                assert result["project"]["authorized_scopes"] == []
                prefix = "/api/projects/" + result["project"]["id"]
                run_route = prefix + "/runs/" + result["collection"]["run_id"]
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    run = request("GET", run_route)
                    if run["status"] not in {"queued", "running"}:
                        break
                    time.sleep(.05)
                assert run["status"] == "completed"
                snapshot = request("GET", prefix)
                assert snapshot["assets"] and snapshot["relationships"]
                assert snapshot["model_runs"][0]["provider"] == "rules-demo"
                assert snapshot["social_accounts"][0]["verification_status"] == "confirmed"
                dork_log = next(log for log in run["collectors"] if log["collector"] == "google_dork")
                assert dork_log["status"] == "skipped" and "GOOGLE_DORK_LINKS:" in dork_log["message"]
                request("GET", prefix + "/assets")
                request("GET", prefix + "/relationships")
                request("GET", prefix + "/social")
                source = request("GET", prefix + "/sources/" + snapshot["sources"][0]["id"])
                assert source["content_hash"] and source["raw_content"]
                for suffix in ("report.json", "report.html", "report.csv"):
                    request("GET", prefix + "/" + suffix)
                repeated = request("POST", "/api/projects/setup", {"domain": "ACME.EXAMPLE"}, 202)
                assert repeated["created"] is False and repeated["project"]["id"] == result["project"]["id"]
                assert len(request("GET", "/api/projects")) == 1
                for payload in ({"domain": "127.0.0.1"}, {"domain": "*.acme.example"},
                                {"domain": "acme.example", "mode": "authorized"}, {}):
                    request("POST", "/api/projects/setup", payload, 422)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    report = ROOT / "docs/verification/domain-setup-curl.json"
    report.write_text(json.dumps({"result": "passed", "curl_requests": len(checks),
        "scope": "Isolated fixture server and temporary DB; no external collection or paid AI calls", "checks": checks},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = f"PASS: {len(checks)} curl checks; domain-only setup, automatic pipeline, Google Dork fallback, social discovery, AI fixture and reports."
    (ROOT / "docs/verification/domain-setup-curl.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
