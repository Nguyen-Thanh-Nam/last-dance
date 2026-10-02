"""Run pytest with a fresh temporary directory, avoiding stale Windows temp ACLs."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="surface-pytest-") as temporary:
        result = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--basetemp",
                                 str(Path(temporary) / "cases"), *sys.argv[1:]], cwd=ROOT)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
