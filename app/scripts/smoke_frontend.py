"""Read-only curl checks for the running BankDash frontend and split API ports."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise RuntimeError("curl is required")
    checks = []
    with tempfile.TemporaryDirectory(prefix="surface-fe-curl-") as temporary:
        body_file = Path(temporary) / "body"
        header_file = Path(temporary) / "headers"

        def request(port, route, expected=200, method="GET", headers=(), payload=None):
            command = [curl, "--fail-with-body", "--silent", "--show-error", "--noproxy", "*",
                       "--max-time", "15", "-X", method, "-D", str(header_file),
                       "-o", str(body_file), "-w", "%{http_code}"]
            for header in headers:
                command.extend(["-H", header])
            if payload is not None:
                data = Path(temporary) / "payload.json"
                data.write_text(json.dumps(payload), encoding="utf-8")
                command.extend(["-H", "Content-Type: application/json", "--data-binary", "@" + str(data)])
            command.append(f"http://127.0.0.1:{port}{route}")
            response = subprocess.run(command, capture_output=True, text=True)
            assert response.returncode in (0, 22), response.stderr
            assert response.stdout == str(expected), (port, route, response.stdout, response.stderr)
            checks.append({"method": method, "port": port, "path": route, "status": expected})
            return body_file.read_bytes(), header_file.read_text(encoding="utf-8").casefold()

        index, headers = request(2222, "/")
        assert b'My inventory' in index and b'./config.js' in index
        assert b'id="domainSetupForm"' in index and b'id="setupDomain"' in index
        assert "no-cache" in headers
        for filename in ("styles.css", "extra.css", "app.js", "config.js"):
            body, _ = request(2222, "/" + filename)
            assert body == (ROOT / "FE" / filename).read_bytes(), filename
        for asset in sorted((ROOT / "FE/assets").iterdir()):
            if asset.is_file():
                body, _ = request(2222, "/assets/" + asset.name)
                assert body and body == asset.read_bytes(), asset.name
        body, _ = request(3333, "/")
        assert json.loads(body)["service"] == "Surface Map AI backend"
        body, _ = request(3333, "/openapi.json")
        assert "/api/projects/setup" in json.loads(body)["paths"]
        request(3333, "/api/projects/setup", 422, "POST", payload={"domain": "localhost"})
        request(2222, "/api/projects", 404)
        request(2222, "/.env", 404)
        request(3333, "/static/app.js", 404)
        for origin in ("http://127.0.0.1:2222", "http://localhost:2222"):
            _, headers = request(3333, "/api/projects", method="OPTIONS", headers=(
                "Origin: " + origin, "Access-Control-Request-Method: POST",
                "Access-Control-Request-Headers: content-type"))
            assert "access-control-allow-origin: " + origin in headers
        _, headers = request(3333, "/api/projects", 400, "OPTIONS", (
            "Origin: http://outside.example:2222", "Access-Control-Request-Method: POST"))
        assert "access-control-allow-origin:" not in headers
    output = ROOT / "docs/verification/figma-frontend-curl.json"
    output.write_text(json.dumps({"result": "passed", "curl_requests": len(checks),
        "scope": "FE assets, BE schema/health/CORS and rejected setup input; no project changes", "checks": checks},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(checks)} read-only curl checks; FE :2222, BE :3333; all local assets match disk.")


if __name__ == "__main__":
    main()
