"""Airbyte open source, self-hosted inside Sal's app: the official `source-file` connector syncs the shop's
spreadsheets (bookings, vendor price sheets) over the Airbyte protocol (spec / discover / read).

The connector runs in its own isolated Python 3.11 env via `uvx` (its pins conflict with ours), reads each sheet
over HTTPS, and every RECORD message lands in runs/airbyte/<stream>.jsonl. `search_shop_data` searches those
synced records (source="airbyte-oss"). Run: `python -m tools.integrations.airbyte_oss sync`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "airbyte"
CONNECTOR = ["--python", "3.11", "--from", "airbyte-source-file", "source-file"]
REPO_RAW = os.environ.get("SAL_SHEETS_BASE", "https://raw.githubusercontent.com/sudhersankv/sal/main/seed/shop_sheets")
SHEETS = ["bookings", "price_sheet_mission", "price_sheet_bayshore"]


def _uvx() -> list[str]:
    exe = shutil.which("uvx")
    if exe:
        return [exe]
    uv = shutil.which("uv")
    return [uv, "tool", "run"] if uv else []


def _run(cmd: str, config: dict, catalog: dict | None = None, timeout: int = 300) -> list[dict]:
    base = _uvx()
    if not base:
        raise RuntimeError("uv/uvx not found")
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "config.json"
        cfg.write_text(json.dumps(config))
        args = [*base, *CONNECTOR, cmd, "--config", str(cfg)]
        if catalog is not None:
            cat = Path(d) / "catalog.json"
            cat.write_text(json.dumps(catalog))
            args += ["--catalog", str(cat)]
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    msgs = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                msgs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if p.returncode != 0 and not msgs:
        raise RuntimeError(f"source-file {cmd} failed: {p.stderr[-300:]}")
    return msgs


def sync_sheet(name: str) -> int:
    config = {"dataset_name": name, "format": "csv", "url": f"{REPO_RAW}/{name}.csv",
              "provider": {"storage": "HTTPS", "user_agent": False}}
    streams = [m["catalog"]["streams"] for m in _run("discover", config) if m.get("type") == "CATALOG"]
    if not streams:
        raise RuntimeError(f"discover returned no catalog for {name}")
    catalog = {"streams": [{"stream": s, "sync_mode": "full_refresh", "destination_sync_mode": "overwrite"}
                           for s in streams[0]]}
    records = [m["record"]["data"] for m in _run("read", config, catalog) if m.get("type") == "RECORD"]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")
    return len(records)


def sync() -> dict:
    out, t0 = {}, time.time()
    for name in SHEETS:
        try:
            out[name] = sync_sheet(name)
        except Exception as e:  # noqa: BLE001
            out[name] = f"error: {type(e).__name__}: {str(e)[:160]}"
    (OUT / "_sync.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "_sync.json").write_text(json.dumps({"synced_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                "seconds": round(time.time() - t0, 1), "streams": out}))
    return out


def synced() -> bool:
    return any(OUT.glob("*.jsonl"))


def records(stream: str | None = None) -> list[dict]:
    out = []
    for p in sorted(OUT.glob("*.jsonl")):
        name = p.stem
        if stream and name != stream:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            row = json.loads(line)
            fields = {str(k).strip(): ("" if v is None else str(v).strip()) for k, v in row.items()
                      if not str(k).startswith("_ab_")}
            rid = fields.get("id") or fields.get("booking_id") or fields.get("sku") or f"{name}-{i + 1}"
            out.append({"stream": name, "id": rid, "fields": fields})
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "sync":
        print(json.dumps(sync(), indent=1))
    else:
        print(__doc__)
