"""Cognee Cloud memory (SPEC §8.6), async API wrapped sync.

Verified in cognee 1.6.10: `cognee.serve(url=, api_key=) -> CloudClient`; `CloudClient.remember(data, dataset_name=)`,
`CloudClient.recall(query_text, datasets=[...], top_k=)`; `cognee.disconnect()`.
Fallback: db.client facts table if it exposes add_fact/search_facts, else runs/cache/cognee/facts.jsonl + keyword recall.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time

from ._common import cache_dir, cached_call, env, has, key_for, log, safe_exc

SERVICE = "cognee"
_TOK = re.compile(r"[a-z0-9]+")


def available() -> bool:
    return has("COGNEE_URL", "COGNEE_API_KEY")


def _dataset() -> str:
    return env("COGNEE_DATASET", "sal_shop_001")


def _run(coro_fn, timeout: float = 90):
    """Run an async fn to completion even if called from inside a running loop (MCP server)."""
    result: dict = {}

    def target():
        try:
            result["v"] = asyncio.run(asyncio.wait_for(coro_fn(), timeout))
        except BaseException as e:  # noqa: BLE001
            result["e"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout + 5)
    if "e" in result:
        raise result["e"]
    if "v" not in result:
        raise TimeoutError("cognee call timed out")
    return result["v"]


async def _with_client(fn):
    import cognee

    client = await cognee.serve(url=env("COGNEE_URL"), api_key=env("COGNEE_API_KEY"))
    try:
        return await fn(client)
    finally:
        try:
            await cognee.disconnect()
        except Exception:
            pass


# ---------------------------------------------------------------- fallback store
def _db():
    try:
        from db import client as dbc  # type: ignore

        if hasattr(dbc, "add_fact") and hasattr(dbc, "search_facts"):
            return dbc
    except Exception:
        pass
    return None


def _jsonl():
    return cache_dir(SERVICE) / "facts.jsonl"


def _local_remember(text: str, tags: list[str]) -> dict:
    dbc = _db()
    if dbc is not None:
        try:
            dbc.add_fact(text=text, tags=tags)
            return {"ok": True, "source": "fallback", "store": "db"}
        except Exception as e:
            log(f"[cognee] db fallback failed: {safe_exc(e)}")
    with _jsonl().open("a", encoding="utf-8") as f:
        f.write(json.dumps({"text": text, "tags": tags, "ts": time.time()}) + "\n")
    return {"ok": True, "source": "fallback", "store": "jsonl"}


def _local_recall(query: str, top_k: int) -> list[dict]:
    dbc = _db()
    if dbc is not None:
        try:
            return list(dbc.search_facts(query, top_k))
        except Exception:
            pass
    p = _jsonl()
    if not p.exists():
        return []
    q = set(_TOK.findall(query.lower()))
    scored = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        toks = set(_TOK.findall(rec["text"].lower())) | {t.lower() for t in rec.get("tags", [])}
        s = len(q & toks)
        if s:
            scored.append({"text": rec["text"], "tags": rec.get("tags", []), "score": float(s)})
    scored.sort(key=lambda r: -r["score"])
    return scored[:top_k]


# ---------------------------------------------------------------- API
def remember(text: str, tags: list[str] | None = None) -> dict:
    tags = list(tags or [])
    # Always keep a local copy so recall works offline/replay.
    _local_remember(text, tags)
    if not available():
        return {"ok": True, "source": "fallback"}
    body = text if not tags else f"{text}\n[tags: {', '.join(tags)}]"
    try:
        _run(lambda: _with_client(lambda c: c.remember(body, dataset_name=_dataset())))
        return {"ok": True, "source": "live"}
    except Exception as e:
        log(f"[cognee] remember failed: {safe_exc(e)}")
        return {"ok": True, "source": "fallback", "warning": safe_exc(e)[:120]}


def _norm_results(res) -> list[dict]:
    out = []
    for r in res or []:
        if isinstance(r, str):
            out.append({"text": r, "tags": [], "score": None})
        elif isinstance(r, dict):
            txt = r.get("text") or r.get("search_result") or r.get("content") or json.dumps(r, default=str)[:500]
            if isinstance(txt, list):
                txt = " ".join(str(x) for x in txt)
            out.append({"text": str(txt), "tags": r.get("tags", []), "score": r.get("score")})
        else:
            out.append({"text": str(r), "tags": [], "score": None})
    return out


def recall(query: str, top_k: int = 5) -> dict:
    def live():
        res = _run(lambda: _with_client(lambda c: c.recall(query, datasets=[_dataset()], top_k=top_k)))
        return {"facts": _norm_results(res)[:top_k]}

    def fb():
        return {"facts": _local_recall(query, top_k)}

    return cached_call(SERVICE, key_for("recall", query, top_k), live if available() else None, fb)
