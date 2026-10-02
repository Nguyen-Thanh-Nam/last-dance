"""Start FE :2222 and BE :3333; Ctrl+C stops both child servers."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def servers(*, env_overrides=None, logs=None, use_env_file=True):
    # Check both ports before starting, so an existing service is never stopped.
    for port in (2222, 3333):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env_overrides or {})}
    backend = [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "BE"), "--host", "127.0.0.1", "--port", "3333"]
    if use_env_file and (ROOT / ".env").exists():
        backend += ["--env-file", str(ROOT / ".env")]
    commands = [backend, [sys.executable, str(ROOT / "FE/serve.py"), "--port", "2222"]]
    processes = []
    try:
        for index, command in enumerate(commands):
            processes.append(subprocess.Popen(command, cwd=ROOT, env=env,
                stdout=logs[index] if logs else None, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        deadline = time.monotonic() + 20
        pending = {"http://127.0.0.1:3333/api/health", "http://127.0.0.1:2222/"}
        while pending:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("One of the servers exited during startup; see its log")
            if time.monotonic() >= deadline:
                raise RuntimeError("Servers did not become ready within 20 seconds")
            for url in list(pending):
                try:
                    with urlopen(url, timeout=.5) as response:
                        if response.status == 200:
                            pending.remove(url)
                except OSError:
                    pass
            if pending:
                time.sleep(.1)
        yield processes
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    try:
        with servers() as processes:
            print("FE: http://127.0.0.1:2222\nBE: http://127.0.0.1:3333\nSwagger: http://127.0.0.1:3333/docs\nCtrl+C stops both servers.", flush=True)
            while all(process.poll() is None for process in processes):
                time.sleep(.5)
            raise RuntimeError("A server stopped unexpectedly")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
