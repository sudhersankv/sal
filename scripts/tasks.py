"""Cross-platform task runner. `make <t>` == `uv run python scripts/tasks.py <t>`."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable]


def run(*cmd: str, check: bool = True) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(list(cmd), cwd=ROOT, check=check).returncode


def bg(*cmd: str) -> subprocess.Popen:
    print("& ", " ".join(cmd), flush=True)
    return subprocess.Popen(list(cmd), cwd=ROOT, shell=(cmd[0] == "npm"))


def t_setup():
    run("uv", "sync", "--extra", "memory")
    if (ROOT / "ui/web/package.json").exists():
        run("npm", "--prefix", "ui/web", "install")


def t_seed():
    run(*PY, "-m", "seed")


def t_vendors():
    run(*PY, "-m", "uvicorn", "vendors.app:app", "--port", "8101")


def t_tools():
    run(*PY, "-m", "tools.server")


def t_ui():
    procs = [bg(*PY, "-m", "uvicorn", "ui.server.app:app", "--port", "8100")]
    if (ROOT / "ui/web/package.json").exists():
        procs.append(bg("npm", "--prefix", "ui/web", "run", "dev"))
    _wait(procs)


def t_dev():
    procs = [bg(*PY, "-m", "uvicorn", "vendors.app:app", "--port", "8101"),
             bg(*PY, "-m", "uvicorn", "ui.server.app:app", "--port", "8100")]
    if (ROOT / "ui/web/package.json").exists():
        procs.append(bg("npm", "--prefix", "ui/web", "run", "dev"))
    _wait(procs)


def t_bot():
    run(*PY, "-m", "agent.telegram_bot")


def t_mcp():
    run(*PY, "-m", "agent.mcp_public", "--http", "--port", "8103")


def t_week():
    run(*PY, "-m", "sim.run", "--week")


def t_record():
    run(*PY, "-m", "sim.run", "--week", "--run-id", "demo")


def t_demo():
    import os
    os.environ["DEMO_MODE"] = "replay"
    t_ui()


def t_check():
    rc = run("ruff", "check", ".", check=False)
    rc |= run(*PY, "-m", "pytest", "-q", "-x", "--ignore=tests/e2e", check=False)
    if (ROOT / "db/check.py").exists():
        rc |= run(*PY, "-m", "db.check", check=False)
    sys.exit(rc)


def _wait(procs):
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "check"
    fn = globals().get(f"t_{name}")
    if not fn:
        sys.exit(f"unknown task {name}; have: " + ", ".join(k[2:] for k in globals() if k.startswith("t_")))
    fn()
