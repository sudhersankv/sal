"""Statsig variant selection (SPEC §8.3). The sim picks the arm; Sal never chooses its own.

Resolution order for gate `sal_vendor_routing_v2` and dynamic config `sal_policy`:
  1. explicit CLI `--variant on|off`
  2. local override file runs/statsig_override.json (written when the owner approves the SUN rule)
  3. tools.integrations.statsig_client (T2/integrations) if importable
  4. statsig-python-core with STATSIG_SERVER_SECRET (time-boxed)
  5. env SAL_GATE_ROUTING_V2 / SAL_POLICY_STRATEGY, default OFF / rules_aware
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
        os.environ["SAL_POLICY_STRATEGY"] = self.strategy


def _env_bool(name: str) -> bool | None:
    v = os.getenv(name)
    if v is None or v == "":
        return None
    return v.strip().lower() in ("1", "true", "on", "yes")


def _read_override() -> dict | None:
    try:
        return json.loads(OVERRIDE.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_override(gate_on: bool) -> None:
    OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDE.write_text(json.dumps({GATE: gate_on}), encoding="utf-8")


def clear_override() -> None:
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


def _from_integrations() -> tuple[bool, dict] | None:
    try:
        from tools.integrations import statsig_client as sc  # type: ignore
    except Exception:
        return None
    for gate_fn, cfg_fn in (("check_gate", "get_config"), ("check_gate", "get_dynamic_config")):
        g, c = getattr(sc, gate_fn, None), getattr(sc, cfg_fn, None)
        if callable(g):
            gate = bool(_with_timeout(lambda: g(GATE), 8))
            cfg = {}
            if callable(c):
                try:
                    raw = _with_timeout(lambda: c(CONFIG), 8)
                    cfg = dict(getattr(raw, "value", raw) or {})
                except Exception:
                    cfg = {}
            return gate, cfg
    return None


def _from_sdk() -> tuple[bool, dict] | None:
    secret = os.getenv("STATSIG_SERVER_SECRET")
    if not secret:
        return None

    def go():
        from statsig_python_core import Statsig, StatsigOptions, StatsigUser

        s = Statsig(secret, StatsigOptions())
        s.initialize().wait()
        try:
            user = StatsigUser(USER_ID)
            gate = bool(s.check_gate(user, GATE))
            cfg = s.get_dynamic_config(user, CONFIG)
            val = getattr(cfg, "value", None)
            if val is None and hasattr(cfg, "get_value"):
                val = cfg.get_value()
            return gate, dict(val or {})
        finally:
            try:
                s.shutdown().wait()
            except Exception:
                pass

    return _with_timeout(go, 12)


def resolve(cli_variant: str | None = None) -> Variant:
    strategy_env = os.getenv("SAL_POLICY_STRATEGY_DEFAULT") or "rules_aware"
    if cli_variant in ("on", "off"):
        return Variant(gate_routing_v2=cli_variant == "on", strategy=strategy_env, source="cli")
    ov = _read_override()
    remote: tuple[bool, dict] | None = None
    src = "default"
    if os.getenv("SIM_OFFLINE") != "1":
        for name, fn in (("statsig_client", _from_integrations), ("statsig", _from_sdk)):
            try:
                remote = fn()
            except Exception as e:  # noqa: BLE001
                print(f"[sim] {name} read failed: {e!r}; falling back", file=sys.stderr)
                remote = None
            if remote is not None:
                src = name
                break
    gate, cfg = remote if remote is not None else (False, {})
    if remote is None:
        env_gate = _env_bool("SAL_GATE_ROUTING_V2_DEFAULT")
        gate = bool(env_gate) if env_gate is not None else False
        src = "env" if env_gate is not None else "default"
    if ov is not None and GATE in ov:
        # override only ever turns the gate ON after owner approval (Console API may lag / be absent)
        if ov[GATE] and not gate:
            gate, src = True, f"{src}+override"
    strategy = str(cfg.get("strategy") or strategy_env)
    return Variant(gate_routing_v2=gate, strategy=strategy, source=src,
                   config={k: v for k, v in cfg.items() if k != "strategy"})


def enable_gate() -> dict:
    """Turn the gate ON after owner approval. Console API via integrations/HTTP if a key exists; always
    writes the local override so the next run sees it immediately."""
    write_override(True)
    result = {"gate": GATE, "enabled": True, "method": "local_override"}
    try:
        from tools.integrations import statsig_client as sc  # type: ignore

        for fn in ("enable_gate", "set_gate"):
            f = getattr(sc, fn, None)
            if callable(f):
                _with_timeout(lambda: f(GATE, True) if fn == "set_gate" else f(GATE), 10)
                result["method"] = f"statsig_client.{fn}"
                return result
    except Exception as e:  # noqa: BLE001
        print(f"[sim] statsig_client enable failed: {e!r}", file=sys.stderr)
    key = os.getenv("STATSIG_CONSOLE_API_KEY")
    if key and os.getenv("SIM_OFFLINE") != "1":
        try:
            import httpx

            r = httpx.put(f"https://statsigapi.net/console/v1/gates/{GATE}/enable",
                          headers={"STATSIG-API-KEY": key}, timeout=10)
            if r.status_code < 300:
                result["method"] = "console_api"
            else:
                result["console_status"] = r.status_code
        except Exception as e:  # noqa: BLE001
            print(f"[sim] Statsig console enable failed: {e!r}", file=sys.stderr)
    return result
