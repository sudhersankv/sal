"""Shared helpers: env loading, input-hash cache, error shape. Never logs secrets."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = ROOT / "runs" / "cache"
SEED = ROOT / "seed"

try:  # python-dotenv is a core dep; tolerate absence anyway
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:  # pragma: no cover
    pass


def env(name: str, default: str = "") -> str:
    v = os.environ.get(name, "")
    v = v.strip() if isinstance(v, str) else ""
    return v or default


def has(*names: str) -> bool:
    return all(env(n) for n in names)


def replay() -> bool:
    return env("DEMO_MODE").lower() == "replay"


def err(code: str, message: str, **extra: Any) -> dict:
    out = {"error": {"code": code, "message": str(message)[:500]}}
    out.update(extra)
    return out


def _default(o: Any) -> Any:
    try:
        import numpy as np

        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.generic):
            return o.item()
    except Exception:
        pass
    if isinstance(o, (bytes, bytearray)):
        return hashlib.sha256(bytes(o)).hexdigest()
    if isinstance(o, Path):
        return str(o)
    return str(o)


def key_for(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=_default)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def cache_dir(service: str) -> Path:
    d = CACHE_ROOT / service
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_get(service: str, key: str) -> Any | None:
    p = CACHE_ROOT / service / f"{key}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_put(service: str, key: str, value: Any) -> None:
    try:
        p = cache_dir(service) / f"{key}.json"
        p.write_text(json.dumps(value, default=_default, indent=1), encoding="utf-8")
    except Exception as e:  # pragma: no cover
        log(f"[{service}] cache write failed: {type(e).__name__}")


def log(msg: str) -> None:
    """stderr only (stdout may be an MCP stdio channel)."""
    print(msg, file=sys.stderr, flush=True)


def safe_exc(e: BaseException) -> str:
    """Exception text with any known secret values redacted."""
    s = f"{type(e).__name__}: {e}"
    for k, v in os.environ.items():
        if v and len(v) >= 8 and any(t in k for t in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
            s = s.replace(v, "***")
    return s[:400]


def cached_call(service: str, key: str, live_fn, fallback_fn=None) -> dict:
    """replay → cache; else live (cache on success) → cache → fallback → error."""
    if replay():
        hit = cache_get(service, key)
        if hit is not None:
            return {**hit, "source": "cache"} if isinstance(hit, dict) else hit
    if live_fn is not None:
        try:
            out = live_fn()
            if isinstance(out, dict) and "error" not in out:
                cache_put(service, key, out)
                return {**out, "source": "live"}
            live_err = out
        except Exception as e:
            live_err = err("live_failed", safe_exc(e))
            log(f"[{service}] live call failed: {live_err['error']['message']}")
        hit = cache_get(service, key)
        if hit is not None:
            return {**hit, "source": "cache"} if isinstance(hit, dict) else hit
    else:
        hit = cache_get(service, key)
        if hit is not None:
            return {**hit, "source": "cache"} if isinstance(hit, dict) else hit
        live_err = err("unavailable", f"{service} not configured")
    if fallback_fn is not None:
        try:
            out = fallback_fn()
            if isinstance(out, dict):
                return {**out, "source": out.get("source", "fallback")}
            return out
        except Exception as e:
            return err("fallback_failed", safe_exc(e))
    return live_err
