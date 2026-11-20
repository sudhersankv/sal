"""Amplitude Agent Analytics for Sal (SPEC §8.3, T3 B3).

One Amplitude session per day-run: session_id = run_id, user_id = shop-001, agent "sal".
Instrumented manually from the Claude Agent SDK message stream. Every call is best-effort:
no key -> no-op; SDK failure -> HTTP API fallback with [Agent]-prefixed props; never raises.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

USER_ID = "shop-001"
AGENT_ID = "sal"
PROVIDER = "anthropic"
HTTP_URL = "https://api2.amplitude.com/2/httpapi"


def _clip(v: Any, n: int = 2000) -> Any:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s[:n]


class SessionTracker:
    def __init__(self, run_id: str, day: str, variant: str, model: str):
        self.run_id, self.day, self.variant, self.model = run_id, day, variant, model
        self.key = os.getenv("AMPLITUDE_AI_API_KEY") or ""
        self.enabled = bool(self.key) and os.getenv("SAL_ANALYTICS", "on") != "off"
        self.ctx = {"day": day, "variant": variant, "run_id": run_id}
        self.ai = self.session = None
        self._http: list[dict] = []  # fallback buffer
        if not self.enabled:
            return
        try:
            from amplitude_ai import AmplitudeAI

            self.ai = AmplitudeAI(api_key=self.key)
            agent = self.ai.agent(AGENT_ID, user_id=USER_ID, description="Sal, the shop's parts team",
                                  context=self.ctx, env=os.getenv("DEMO_MODE", "live"))
            self.session = agent.session(session_id=run_id, user_id=USER_ID, context=self.ctx,
                                         tags=[f"day:{day}", f"variant:{variant}"])
            self.session.__enter__()
        except Exception as e:  # noqa: BLE001
            self._warn("init", e)
            self.ai = self.session = None

    # ------------------------------------------------------------ helpers
    def _warn(self, where: str, e: Exception) -> None:
        print(f"[sal.analytics] {where} failed ({type(e).__name__}); using HTTP fallback", file=sys.stderr)

    def _do(self, where: str, fn, http_event: str, props: dict) -> None:
        if not self.enabled:
            return
        if self.session is not None:
            try:
                fn()
                return
            except Exception as e:  # noqa: BLE001
                self._warn(where, e)
        self._http.append({
            "user_id": USER_ID, "event_type": http_event, "time": int(time.time() * 1000),
            "event_properties": {"[Agent] Session ID": self.run_id, "[Agent] Agent ID": AGENT_ID,
                                 "variant": self.variant, "day": self.day,
                                 **{(k if k.startswith("[Agent]") or k in ("variant", "day") else f"[Agent] {k}"): v
                                    for k, v in props.items()}},
        })

    # ------------------------------------------------------------ tracking API
    def user_message(self, content: str) -> None:
        self._do("user_message", lambda: self.session.track_user_message(content),
                 "[Agent] User Message", {"Content": _clip(content)})

    def ai_message(self, content: str, tool_names: list[str], latency_ms: float, usage: dict | None,
                   model: str, finish_reason: str | None) -> None:
        u = usage or {}
        kw = dict(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                  cache_read_tokens=u.get("cache_read_input_tokens"),
                  cache_creation_tokens=u.get("cache_creation_input_tokens"),
                  finish_reason=finish_reason, tool_calls=[{"name": n} for n in tool_names] or None)
        self._do("ai_message",
                 lambda: self.session.track_ai_message(content, model, PROVIDER, latency_ms, **kw),
                 "[Agent] AI Response", {"Content": _clip(content), "Model Name": model,
                                         "Latency Ms": latency_ms, "Tool Calls": tool_names})

    def tool_call(self, name: str, inp: dict, output: Any, latency_ms: float, success: bool) -> None:
        self._do("tool_call",
                 lambda: self.session.track_tool_call(name, latency_ms, success, input=inp,
                                                      output=_clip(output), tool_owner="sal-tools"),
                 "[Agent] Tool Call", {"Tool Name": name, "Latency Ms": latency_ms, "Success": success,
                                       "Tool Input": _clip(inp, 1000)})

    def run_cost(self, cost: float | None, usage: dict | None, duration_ms: int, model: str) -> None:
        u = usage or {}
        self._do("run_cost",
                 lambda: self.session.track_run_cost(
                     float(cost or 0.0), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                     model, PROVIDER, latency_ms=duration_ms, finish_reason="end_turn",
                     cache_read_tokens=int(u.get("cache_read_input_tokens") or 0),
                     cache_creation_tokens=int(u.get("cache_creation_input_tokens") or 0)),
                 "[Agent] AI Response", {"Cost USD": cost, "Latency Ms": duration_ms, "Model Name": model})

    def custom(self, event_type: str, props: dict) -> None:
        """Business events: sal_order_placed, sal_escalation, sal_rule_proposed (with variant)."""
        if not self.enabled:
            return
        ev = {"user_id": USER_ID, "event_type": event_type, "time": int(time.time() * 1000),
              "event_properties": {"variant": self.variant, "day": self.day,
                                   "[Agent] Session ID": self.run_id, **props}}
        if self.ai is not None:
            try:
                from amplitude import BaseEvent

                self.ai.amplitude.track(BaseEvent(event_type=event_type, user_id=USER_ID,
                                                  event_properties=ev["event_properties"]))
                return
            except Exception as e:  # noqa: BLE001
                self._warn("custom", e)
        self._http.append(ev)

    def end(self, result: Any) -> None:
        if not self.enabled:
            return
        try:
            self.custom("sal_run_completed", {"ok": getattr(result, "ok", None),
                                              "tool_calls": len(getattr(result, "tool_calls", []) or []),
                                              "escalations": getattr(result, "escalations", 0),
                                              "cost_usd": getattr(result, "cost_usd", None)})
            if self.session is not None:
                try:
                    self.session.__exit__(None, None, None)
                except Exception as e:  # noqa: BLE001
                    self._warn("session_end", e)
        finally:
            try:
                if self.ai is not None:
                    self.ai.flush()
            except Exception as e:  # noqa: BLE001
                self._warn("flush", e)
            self._flush_http()

    def _flush_http(self) -> None:
        if not self._http:
            return
        try:
            import httpx

            httpx.post(HTTP_URL, json={"api_key": self.key, "events": self._http}, timeout=5)
        except Exception as e:  # noqa: BLE001
            print(f"[sal.analytics] HTTP fallback failed ({type(e).__name__})", file=sys.stderr)
        self._http = []
