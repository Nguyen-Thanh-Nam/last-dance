"""Real curl checks for FE :2222, BE :3333, all APIs and CORS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from smoke_api import run
from start_dev import ROOT, servers


def check_split_ports(temporary):
    result = run("http://127.0.0.1:3333", temporary)
    curl = shutil.which("curl.exe") or shutil.which("curl")
    checks = []

    def request(port, path, *, method="GET", headers=(), expected=200):
        header_file = Path(temporary) / "split-headers.txt"
        body_file = Path(temporary) / "split-body.txt"
        command = [curl, "--silent", "--show-error", "--noproxy", "*", "--max-time", "20",
                   "-X", method, "-D", str(header_file), "-o", str(body_file), "-w", "%{http_code}"]
        for header in headers:
            command += ["-H", header]
        command += [f"http://127.0.0.1:{port}{path}"]
        response = subprocess.run(command, capture_output=True, text=True, check=True)
        assert int(response.stdout) == expected, (port, path, response.stdout)
        checks.append({"port": port, "method": method, "path": path, "status": expected})
        print(f"PASS {method} :{port}{path}: {expected}", flush=True)
        return body_file.read_text(encoding="utf-8"), header_file.read_text(encoding="utf-8").casefold()

    index, _ = request(2222, "/")
    assert "Surface Map AI" in index and './config.js' in index and '/static/' not in index
    for filename in ("styles.css", "extra.css", "app.js", "config.js"):
        body, _ = request(2222, "/" + filename)
        if filename == "config.js":
            assert "'3333'" in body
    request(2222, "/api/projects", expected=404)
    request(3333, "/static/app.js", expected=404)
    for origin in ("http://127.0.0.1:2222", "http://localhost:2222"):
        _, headers = request(3333, "/api/projects", method="OPTIONS", headers=(
            "Origin: " + origin, "Access-Control-Request-Method: POST", "Access-Control-Request-Headers: content-type"))
        assert "access-control-allow-origin: " + origin in headers
    _, headers = request(3333, "/api/projects", method="OPTIONS", headers=(
        "Origin: http://outside.example:2222", "Access-Control-Request-Method: POST"), expected=400)
    assert "access-control-allow-origin:" not in headers
    result["split_port_checks"] = checks
    result["split_curl_requests"] = len(checks)
    result["total_curl_checks"] = result["curl_requests"] + len(checks)
    result["frontend_url"] = "http://127.0.0.1:2222"
    result["backend_url"] = "http://127.0.0.1:3333"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--external", action="store_true", help="Check already-running isolated test servers")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/verification/split-curl-results.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="surface-split-curl-") as temporary:
        if args.external:
            result = check_split_ports(temporary)
        else:
            with (Path(temporary) / "backend.log").open("w", encoding="utf-8") as backend_log, (Path(temporary) / "frontend.log").open("w", encoding="utf-8") as frontend_log:
                with servers(logs=[backend_log, frontend_log], use_env_file=False, env_overrides={
                    "DATABASE_PATH": str(Path(temporary) / "split.db"), "AI_PROVIDER": "rules-demo",
                    "ENABLE_RDAP": "false", "ALLOW_PRIVATE_LAB": "false", "REQUEST_DELAY_SECONDS": "0",
                    "CORS_ORIGINS": "http://127.0.0.1:2222,http://localhost:2222"}):
                    result = check_split_ports(temporary)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"PASS: {result['total_curl_checks']} curl checks; {result['api_route_count']} API routes; FE :2222, BE :3333", flush=True)


if __name__ == "__main__":
    main()
