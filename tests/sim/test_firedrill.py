"""Firedrill driver protocol + template rendering."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_library_files_are_json():
    for p in (ROOT / "firedrill/library").glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["name"]
    dana = json.loads((ROOT / "firedrill/library/persona_dana_ruiz.json").read_text(encoding="utf-8"))
    assert "$150" in " ".join(dana["constraints"])


def test_prepare_renders(tmp_path, monkeypatch):
    from firedrill import prepare

    monkeypatch.setattr(prepare, "BUILD", tmp_path)
    prepare.main(["descriptor", "--identity", "a" * 64])
    d = json.loads((tmp_path / "descriptor.json").read_text(encoding="utf-8"))
    assert d["driver"]["profile"] == "jsonl-process.v1" and len(d["driver"]["adapter_sha256"]) == 64
    prepare.main(["plan", "--identity", "a" * 64, "--descriptor-sha", "b" * 64, "--uv", "/usr/bin/uv"])
    plan = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert plan["services"][0]["readiness"] == {"kind": "stdout", "pattern": "READY"}
    prepare.main(["scenario", "--persona", "p:1:x", "--valumax", "v:1:x", "--cap", "c:2:y", "--cutoff", "t:1:z"])
    sc = json.loads((tmp_path / "scenario_monday.json").read_text(encoding="utf-8"))
    assert sc["evaluations"][1]["revision"] == 2
    prepare.main(["world", "--scenario", "s:1:d"])


def test_driver_protocol(tmp_path):
    env = {**os.environ, "SIM_STUB_AGENT": "1", "SIM_OFFLINE": "1", "SIM_LOCAL_EMIT": "1",
           "SIM_NO_UI_POST": "1", "SIM_APPROVE_DELAY": "0"}
    steps = [{"id": "s1", "session": "pytest-drill", "kind": "message", "input": "Civic in bay 2, P0141"},
             {"id": "s2", "session": "pytest-drill", "kind": "message", "input": "why?"}]
    p = subprocess.run([sys.executable, "-m", "firedrill.driver"], cwd=ROOT, env=env, timeout=120,
                       input="\n".join(json.dumps(s) for s in steps) + "\n", capture_output=True, text=True)
    lines = p.stdout.splitlines()
    assert lines[0] == "READY"
    replies = [json.loads(x) for x in lines[1:]]
    assert [r["id"] for r in replies] == ["s1", "s2"]
    assert "valumax_ordered=no" in replies[0]["output"]
    import shutil

    shutil.rmtree(ROOT / "runs" / "fd-pytest-drill", ignore_errors=True)
