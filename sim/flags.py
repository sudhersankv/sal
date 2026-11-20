"""Statsig variant selection (SPEC §8.3). The sim picks the arm; Sal never chooses its own.

Read via tools/integrations/statsig_client (real gate + dynamic config; honours its SAL_GATE_ROUTING /
SAL_POLICY_STRATEGY env overrides). `--variant on|off` sets SAL_GATE_ROUTING for the run. When the owner
approves the SUN rule, `enable_gate()` flips the gate in the Statsig Console (STATSIG_CONSOLE_API_KEY) and
records runs/statsig_override.json so the next run sees ON even before the console change propagates.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = "sal_vendor_routing_v2"
CONFIG = "sal_policy"
USER_ID = "shop-001"
OVERRIDE = ROOT / "runs" / "statsig_override.json"


@dataclass
class Variant:
    gate_routing_v2: bool = False
    strategy: str = "rules_aware"  # cheapest | rules_aware
    source: str = "default"
    config: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return "gate_on" if self.gate_routing_v2 else "gate_off"

    @property
    def arm(self) -> str:
        """What brain's run_day(variant=...) takes: "on" | "off"."""
        return "on" if self.gate_routing_v2 else "off"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["name"] = self.name
        d[GATE] = self.gate_routing_v2
        d[CONFIG] = {"strategy": self.strategy, **self.config}
        return d

    def export_env(self) -> None:
        """Tools' policy guard (rule 3) and brain read these in-process / in subprocesses."""
        os.environ["SAL_VARIANT"] = self.name
        os.environ["SAL_GATE_ROUTING_V2"] = "1" if self.gate_routing_v2 else "0"


def _read_override() -> dict | None:
    try:
        return json.loads(OVERRIDE.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_override(gate_on: bool) -> None:
    OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDE.write_text(json.dumps({GATE: gate_on}), encoding="utf-8")


def clear_override() -> None:
    if os.environ.get("SAL_GATE_ROUTING") == "on" and not os.getenv("SAL_GATE_ROUTING_PINNED"):
        os.environ.pop("SAL_GATE_ROUTING", None)
    try:
        OVERRIDE.unlink()
    except FileNotFoundError:
        pass


def _with_timeout(fn, seconds: float):
    box: dict = {}

    def target():
        try:
            box["v"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if "e" in box:
        raise box["e"]
    if "v" not in box:
        raise TimeoutError(f"statsig call exceeded {seconds}s")
    return box["v"]


def _from_statsig() -> tuple[bool, dict, str] | None:
    """Real gate + dynamic config via tools/integrations/statsig_client (honours SAL_GATE_ROUTING overrides)."""
    from tools.integrations import statsig_client as sc

    gate = bool(_with_timeout(lambda: sc.check_gate(GATE, USER_ID), 20))
    cfg = dict(_with_timeout(lambda: sc.get_config(CONFIG, USER_ID), 20) or {})
    src = "override" if os.getenv("SAL_GATE_ROUTING") else ("statsig" if sc.available() else "fallback")
    return gate, cfg, src


def resolve(cli_variant: str | None = None) -> Variant:
    if cli_variant in ("on", "off"):
        os.environ["SAL_GATE_ROUTING"] = cli_variant  # statsig_client + policy guard honour it
    gate, cfg, src = False, {}, "default"
    try:
        gate, cfg, src = _from_statsig()
    except Exception as e:  # noqa: BLE001
        print(f"[sim] statsig read failed: {e!r}", file=sys.stderr)
    ov = _read_override()
    if ov and ov.get(GATE) and not gate:  # owner approved on SUN; console flip may lag
        gate, src = True, f"{src}+approved"
    if cli_variant in ("on", "off"):
        src = "cli"
    strategy = str(cfg.get("strategy") or "rules_aware")
    return Variant(gate_routing_v2=gate, strategy=strategy, source=src,
                   config={k: v for k, v in cfg.items() if k != "strategy"})


def enable_gate() -> dict:
    """Owner approved the routing rule: flip gate ON in Statsig (Console API) and for this process + tools."""
    write_override(True)
    os.environ["SAL_GATE_ROUTING"] = "on"
    result = {"gate": GATE, "enabled": True, "method": "local"}
    key = os.getenv("STATSIG_CONSOLE_API_KEY")
    if key:
        try:
            import httpx

            r = httpx.put(f"https://statsigapi.net/console/v1/gates/{GATE}/enable",
                          headers={"STATSIG-API-KEY": key}, timeout=15)
            result["method"] = "console_api" if r.status_code < 300 else f"console_http_{r.status_code}"
        except Exception as e:  # noqa: BLE001
            result["method"] = f"console_error:{e.__class__.__name__}"
    return result
