"""Statsig: gate sal_vendor_routing_v2 + dynamic config sal_policy (SPEC §8.3).

Verified in statsig-python-core 0.24.2: Statsig(secret, StatsigOptions()).initialize().wait();
check_gate(StatsigUser(user_id), name) -> bool; get_dynamic_config(user, name).value -> dict;
log_event(user, event_name, value, metadata); shutdown().wait().
Console API (optional): https://statsigapi.net/console/v1/{gates|dynamic_configs}, header STATSIG-API-KEY.
Env overrides always win: SAL_GATE_ROUTING=on|off, SAL_POLICY_STRATEGY=cheapest|rules_aware.
"""

from __future__ import annotations

import httpx

from ._common import env, has, log, safe_exc

GATE = "sal_vendor_routing_v2"
CONFIG = "sal_policy"
CONSOLE = "https://statsigapi.net/console/v1"
_sdk = None
_failed = False


def available() -> bool:
    return has("STATSIG_SERVER_SECRET")


def _statsig():
    global _sdk, _failed
    if _sdk is not None or _failed or not available():
        return _sdk
    try:
        from statsig_python_core import Statsig, StatsigOptions

        s = Statsig(env("STATSIG_SERVER_SECRET"), StatsigOptions())
        s.initialize().wait()
        _sdk = s
    except Exception as e:
        _failed = True
        log(f"[statsig] init failed: {safe_exc(e)}")
    return _sdk


def _user(user_id: str):
    from statsig_python_core import StatsigUser

    return StatsigUser(user_id)


def check_gate(name: str = GATE, user_id: str = "shop-001") -> bool:
    ov = env("SAL_GATE_ROUTING").lower()
    if name == GATE and ov in ("on", "off", "true", "false", "1", "0"):
        return ov in ("on", "true", "1")
    s = _statsig()
    if s is None:
        return False
    try:
        return bool(s.check_gate(_user(user_id), name))
    except Exception as e:
        log(f"[statsig] check_gate failed: {safe_exc(e)}")
        return False


def get_config(name: str = CONFIG, user_id: str = "shop-001") -> dict:
    default = {"strategy": "rules_aware"} if name == CONFIG else {}
    ov = env("SAL_POLICY_STRATEGY")
    if name == CONFIG and ov:
        return {**default, "strategy": ov}
    s = _statsig()
    if s is None:
        return default
    try:
        val = s.get_dynamic_config(_user(user_id), name).value or {}
        return {**default, **val}
    except Exception as e:
        log(f"[statsig] get_config failed: {safe_exc(e)}")
        return default


def variant(user_id: str = "shop-001") -> dict:
    src = "override" if (env("SAL_GATE_ROUTING") or env("SAL_POLICY_STRATEGY")) else ("live" if _statsig() else "fallback")
    return {"gate_routing_v2": check_gate(GATE, user_id), "strategy": get_config(CONFIG, user_id).get("strategy"), "source": src}


def log_event(name: str, value=None, metadata: dict | None = None, user_id: str = "shop-001") -> None:
    s = _statsig()
    if s is None:
        return
    try:
        md = {k: str(v) for k, v in (metadata or {}).items()}
        s.log_event(_user(user_id), name, value, md)
    except Exception as e:
        log(f"[statsig] log_event failed: {safe_exc(e)}")


def ensure_console_objects() -> dict:
    """Create the gate + dynamic config if missing (needs STATSIG_CONSOLE_API_KEY)."""
    if not has("STATSIG_CONSOLE_API_KEY"):
        return {"skipped": "STATSIG_CONSOLE_API_KEY not set"}
    h = {"STATSIG-API-KEY": env("STATSIG_CONSOLE_API_KEY"), "Content-Type": "application/json"}
    out = {}
    specs = [
        ("gates", GATE, {"name": GATE, "description": "Sal: route starters/alternators to the reliable vendor (Sunday rule)"}),
        (
            "dynamic_configs",
            CONFIG,
            {"name": CONFIG, "description": "Sal policy strategy", "defaultValue": {"strategy": "rules_aware"}},
        ),
    ]
    for kind, name, body in specs:
        try:
            g = httpx.get(f"{CONSOLE}/{kind}/{name}", headers=h, timeout=20)
            if g.status_code == 200:
                out[name] = "exists"
                continue
            r = httpx.post(f"{CONSOLE}/{kind}", headers=h, json=body, timeout=20)
            out[name] = "created" if r.status_code < 300 else f"http_{r.status_code}"
        except Exception as e:
            out[name] = f"error: {safe_exc(e)[:80]}"
    return out


def shutdown() -> None:
    global _sdk
    if _sdk is not None:
        try:
            _sdk.shutdown().wait()
        except Exception:
            pass
        _sdk = None
