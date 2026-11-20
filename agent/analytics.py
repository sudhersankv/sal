"""Amplitude Agent Analytics for Sal (SPEC §8.3, T3 B3).

One Amplitude session per day-run: session_id = run_id, user_id = shop-001, agent "sal".
Instrumented manually from the Claude Agent SDK message stream. Every call is best-effort:
no key -> no-op; failures are logged to stderr and never raise into the run.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

USER_ID = "shop-001"
AGENT_ID = "sal"
PROVIDER = "anthropic"


def _clip(v: Any, n: int = 2000) -> Any:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s[:n]


class SessionTracker:
    def __init__(self, run_id: str, day: str, variant: str, model: str):
        self.run_id, self.day, self.variant, self.model = run_id, day, variant, model
        self.key = os.getenv("AMPLITUDE_AI_API_KEY") or ""
        self.enabled = bool(self.key) and os.getenv("SAL_ANALYTICS", "on") != "off"
        # the sim reuses one run_id for the whole week; Amplitude wants one session per day-run
        self.session_id = run_id if day in run_id.split("-") else f"{run_id}-{day}"
        self.ctx = {"day": day, "variant": variant, "run_id": run_id}
        self.ai = self.session = None
        if not self.enabled:
            return
        try:
            from amplitude_ai import AmplitudeAI

            self.ai = AmplitudeAI(api_key=self.key)
            agent = self.ai.agent(AGENT_ID, user_id=USER_ID, description="Sal, the shop's parts team",
                                  context=self.ctx, env=os.getenv("DEMO_MODE", "live"))
            self.session = agent.session(session_id=self.session_id, user_id=USER_ID, context=self.ctx,
                                         tags=[f"day:{day}", f"variant:{variant}"])
            self.session.__enter__()
        except Exception as e:  # noqa: BLE001
            self._warn("init", e)
            self.ai = self.session = None

    # ------------------------------------------------------------ helpers
    def _warn(self, where: str, e: Exception) -> None:
        print(f"[sal.analytics] {where} failed ({type(e).__name__}: {e})", file=sys.stderr)

    def _do(self, where: str, fn) -> None:
        if self.session is None:
            return
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self._warn(where, e)

    # ------------------------------------------------------------ tracking API
    def user_message(self, content: str) -> None:
        self._do("user_message", lambda: self.session.track_user_message(content))

    def ai_message(self, content: str, tool_names: list[str], latency_ms: float, usage: dict | None,
                   model: str, finish_reason: str | None) -> None:
        u = usage or {}
        kw = dict(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                  cache_read_tokens=u.get("cache_read_input_tokens"),
                  cache_creation_tokens=u.get("cache_creation_input_tokens"),
                  finish_reason=finish_reason, tool_calls=[{"name": n} for n in tool_names] or None)
        self._do("ai_message",
                 lambda: self.session.track_ai_message(content, model, PROVIDER, latency_ms, **kw))

    def tool_call(self, name: str, inp: dict, output: Any, latency_ms: float, success: bool) -> None:
        self._do("tool_call",
                 lambda: self.session.track_tool_call(name, latency_ms, success, input=inp,
                                                      output=_clip(output), tool_owner="sal-tools"))

    def run_cost(self, cost: float | None, usage: dict | None, duration_ms: int, model: str) -> None:
        u = usage or {}
        self._do("run_cost",
                 lambda: self.session.track_run_cost(
                     float(cost or 0.0), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                     model, PROVIDER, latency_ms=duration_ms, finish_reason="end_turn",
                     cache_read_tokens=int(u.get("cache_read_input_tokens") or 0),
                     cache_creation_tokens=int(u.get("cache_creation_input_tokens") or 0)))

    def custom(self, event_type: str, props: dict) -> None:
        """Business events: sal_order_placed, sal_escalation, sal_rule_proposed (with variant)."""
        if self.ai is None:
            return
        try:
            from amplitude import BaseEvent

            self.ai.amplitude.track(BaseEvent(
                event_type=event_type, user_id=USER_ID,
                event_properties={"variant": self.variant, "day": self.day,
                                  "[Agent] Session ID": self.session_id, **props}))
        except Exception as e:  # noqa: BLE001
            self._warn("custom", e)

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
