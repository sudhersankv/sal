"""Thin adapter over tools/integrations/* (owned by teammate `integrations`).

`call("senso", ("search",), query)` imports tools.integrations.senso lazily, calls the first function name
that exists, and returns its result, or None on any failure (module missing, network, bad key). Callers then
use their local fallback. Keeps the server bootable before integrations land.
"""
from __future__ import annotations

import importlib
import logging
import os
from typing import Any

log = logging.getLogger("sal-tools.backends")
_NOT_FOUND = object()


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
    except Exception:
        pass


_load_env()


def call(module: str, names: tuple[str, ...], *args, **kwargs) -> Any:
    if os.environ.get("SAL_TOOLS_OFFLINE") == "1":
        return None
    try:
        mod = importlib.import_module(f"tools.integrations.{module}")
    except Exception as e:  # noqa: BLE001
        log.debug("integration %s unavailable: %s", module, e)
        return None
    for n in names:
        fn = getattr(mod, n, _NOT_FOUND)
        if fn is _NOT_FOUND or not callable(fn):
            continue
        try:
            res = fn(*args, **kwargs)
            if hasattr(res, "__await__"):
                import asyncio
                res = asyncio.run(res) if not _in_loop() else _run_in_thread(res)
            return res
        except Exception as e:  # noqa: BLE001
            log.warning("integration %s.%s failed: %s", module, n, e)
            return None
    return None


def _in_loop() -> bool:
    import asyncio
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _run_in_thread(coro):
    import asyncio
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result(timeout=60)
