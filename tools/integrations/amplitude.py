"""Amplitude custom events (brain owns Agent Analytics session instrumentation via amplitude_ai).

Uses the `amplitude` analytics SDK bundled with amplitude-ai: Amplitude(api_key).track(BaseEvent(...)), flush().
Fallback: append to runs/cache/amplitude/events.jsonl.
"""

from __future__ import annotations

import json
import time

from ._common import cache_dir, env, has, log, safe_exc

_client = None


def available() -> bool:
    return has("AMPLITUDE_AI_API_KEY")


def _amp():
    global _client
    if _client is None and available():
        try:
            from amplitude import Amplitude

            _client = Amplitude(env("AMPLITUDE_AI_API_KEY"))
        except Exception as e:
            log(f"[amplitude] init failed: {safe_exc(e)}")
    return _client


def track(event_type: str, properties: dict | None = None, user_id: str = "shop-001", session_id: str | None = None) -> dict:
    props = dict(properties or {})
    if session_id:
        props.setdefault("run_id", session_id)
    rec = {"event_type": event_type, "user_id": user_id, "event_properties": props, "time": int(time.time() * 1000)}
    try:
        with (cache_dir("amplitude") / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass
    a = _amp()
    if a is None:
        return {"ok": True, "source": "fallback"}
    try:
        from amplitude import BaseEvent

        a.track(BaseEvent(event_type=event_type, user_id=user_id, event_properties=props))
        return {"ok": True, "source": "live"}
    except Exception as e:
        log(f"[amplitude] track failed: {safe_exc(e)}")
        return {"ok": False, "source": "fallback", "error": {"code": "track_failed", "message": safe_exc(e)[:120]}}


def flush() -> None:
    if _client is not None:
        try:
            _client.flush()
        except Exception:
            pass
