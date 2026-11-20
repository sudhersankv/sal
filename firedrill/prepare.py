"""Render Firedrill files from firedrill/templates/ into firedrill/build/ (git-ignored).

Hashes and library ids only exist after the human signs in, so each step takes what the previous
`firedrill` command printed. See firedrill/README.md for the full sequence.

    python -m firedrill.prepare descriptor --identity <identity_sha256>
    python -m firedrill.prepare plan --identity <identity_sha256> --descriptor-sha <digest from register>
    python -m firedrill.prepare scenario --persona ID:REV:DIGEST --valumax ID:REV:DIGEST \
                                         --cap ID:REV:DIGEST --cutoff ID:REV:DIGEST
    python -m firedrill.prepare world --scenario ID:REV:DIGEST
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMPLATES = HERE / "templates"
BUILD = HERE / "build"


def adapter_sha256() -> str:
    return hashlib.sha256((HERE / "driver.py").read_bytes()).hexdigest()


def render(name: str, values: dict[str, str]) -> Path:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    if "{{" in text:
        missing = sorted({t.split("}}")[0] for t in text.split("{{")[1:]})
        sys.exit(f"{name}: unfilled placeholders {missing}")
    json.loads(text)  # must be valid JSON
    BUILD.mkdir(exist_ok=True)
    out = BUILD / name
    out.write_text(text, encoding="utf-8")
    print(out)
    return out


def ref(s: str, prefix: str) -> dict[str, str]:
    try:
        rid, rev, digest = s.split(":", 2)
        int(rev)
    except ValueError:
        sys.exit(f"--{prefix.lower()} must be ID:REVISION:DIGEST (from `firedrill library show`), got {s!r}")
    return {f"{prefix}_ID": rid, f"{prefix}_REVISION": rev, f"{prefix}_DIGEST": digest}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="firedrill.prepare", description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("descriptor")
    d.add_argument("--identity", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--identity", required=True)
    p.add_argument("--descriptor-sha", required=True)
    p.add_argument("--uv", default=shutil.which("uv") or "uv", help="absolute path to uv (plans run with no shell)")
    s = sub.add_parser("scenario")
    for flag in ("persona", "valumax", "cap", "cutoff"):
        s.add_argument(f"--{flag}", required=True)
    w = sub.add_parser("world")
    w.add_argument("--scenario", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "descriptor":
        render("descriptor.json", {"IDENTITY_SHA256": a.identity, "ADAPTER_SHA256": adapter_sha256()})
    elif a.cmd == "plan":
        render("plan.json", {"IDENTITY_SHA256": a.identity, "DESCRIPTOR_SHA256": a.descriptor_sha,
                             "ROOT_PATH": ROOT.as_posix(), "UV_PATH": a.uv})
    elif a.cmd == "scenario":
        vals = {**ref(a.persona, "PERSONA"), **ref(a.valumax, "EVAL_VALUMAX"), **ref(a.cap, "EVAL_CAP"),
                **ref(a.cutoff, "EVAL_CUTOFF")}
        render("scenario_monday.json", vals)
    elif a.cmd == "world":
        render("world.json", ref(a.scenario, "SCENARIO"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
