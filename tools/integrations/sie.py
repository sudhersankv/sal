"""Superlinked SIE adapter — every non-agent model call (D-002).

Verified against sie_sdk 0.11.1 (.venv): SIEClient(base_url, api_key=, timeout_s=),
encode(model, items, is_query=, provision_timeout_s=) -> [{"dense"}],
score(model, query_item, items) -> {"scores": [{item_id, score, rank}]},
extract(model, items, labels=|output_schema=, instruction=) -> {"entities"|"data"},
generate(model, prompt, max_new_tokens=, images=) -> {"text"},
chat_completions(model, messages, max_tokens=, response_format=) -> {"choices":[{"message":{"content"}}]},
list_models() -> [{"name","inputs","outputs",...}].
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
from typing import Any

from ._common import cached_call, env, err, has, key_for, log, safe_exc

SERVICE = "sie"
_client = None
_resolved: dict[str, str] = {}
_catalog: list[dict] | None = None

ROLES = {
    # role: (env var, name hints in priority order, required output)
    "embed": ("SIE_EMBED_MODEL", ["qwen3-embedding-4b", "qwen3-embedding", "embedding", "bge-m3", "e5"], "dense"),
    "rerank": ("SIE_RERANK_MODEL", ["qwen3-reranker-4b", "qwen3-reranker", "reranker", "rerank"], "score"),
    "extract": ("SIE_EXTRACT_MODEL", ["gliner2-large", "gliner2", "gliner"], "entities"),
    "llm": ("SIE_LLM_MODEL", ["qwen3-4b-instruct", "qwen3-4b", "instruct", "qwen3"], "text"),
    "vlm": ("SIE_VLM_MODEL", ["qwen2.5-vl", "qwen3-vl", "-vl", "vision", "smolvlm"], "text"),
    "doc": ("SIE_DOC_MODEL", ["docling", "nuextract", "document", "gliner2"], "data"),
}


def available() -> bool:
    return has("SIE_API_KEY")


def _timeout() -> float:
    try:
        return float(env("SIE_PROVISION_TIMEOUT", "60"))
    except ValueError:
        return 60.0


def client():
    global _client
    if _client is None:
        from sie_sdk import SIEClient

        _client = SIEClient(
            env("SIE_BASE_URL", "https://api.superlinked.com"),
            api_key=env("SIE_API_KEY"),
            timeout_s=_timeout() + 30,
        )
    return _client


def _list_catalog() -> list[dict]:
    global _catalog
    if _catalog is None:
        try:
            _catalog = list(client().list_models()) if available() else []
        except Exception as e:
            log(f"[sie] list_models failed: {safe_exc(e)}")
            _catalog = []
    return _catalog


def model(role: str) -> str:
    """Resolved model id for a role: env var, else best match from list_models() (printed once)."""
    if role in _resolved:
        return _resolved[role]
    var, hints, _ = ROLES[role]
    m = env(var)
    if not m and available():
        names = [str(x.get("name", "")) for x in _list_catalog()]
        for h in hints:
            match = next((n for n in names if h in n.lower()), None)
            if match:
                m = match
                break
        if m:
            log(f"[sie] {var} empty; picked '{m}' from list_models()")
    _resolved[role] = m
    return m


def models() -> dict:
    return {r: model(r) for r in ROLES}


# ---------------------------------------------------------------- embed
_DIM = 256


def _hash_embed(text: str) -> list[float]:
    v = [0.0] * _DIM
    t = f"  {text.lower()}  "
    for i in range(len(t) - 2):
        h = int(hashlib.md5(t[i : i + 3].encode()).hexdigest()[:8], 16)
        v[h % _DIM] += 1.0 if (h >> 8) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _norm(vec) -> list[float]:
    v = [float(x) for x in vec]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed(texts: list[str], is_query: bool | None = None) -> dict:
    texts = [str(t) for t in (texts or [])]
    m = model("embed")

    def live():
        res = client().encode(
            m, [{"text": t} for t in texts], is_query=is_query, provision_timeout_s=_timeout()
        )
        res = res if isinstance(res, list) else [res]
        vecs = [_norm(r["dense"]) for r in res]
        return {"vectors": vecs, "model": m, "dim": len(vecs[0]) if vecs else 0}

    def fb():
        vecs = [_hash_embed(t) for t in texts]
        return {"vectors": vecs, "model": "fallback:hash-trigram-256", "dim": _DIM}

    if not texts:
        return {"vectors": [], "model": m, "dim": 0, "source": "fallback"}
    return cached_call(SERVICE, key_for("embed", m, texts, is_query), live if available() and m else None, fb)


# ---------------------------------------------------------------- rerank
_TOK = re.compile(r"[a-z0-9]+")


def _overlap(q: str, d: str) -> float:
    qs, ds = set(_TOK.findall(q.lower())), set(_TOK.findall(d.lower()))
    if not qs or not ds:
        return 0.0
    return len(qs & ds) / math.sqrt(len(qs) * len(ds))


def rerank(query: str, docs: list[str]) -> dict:
    docs = [str(d) for d in (docs or [])]
    m = model("rerank")

    def live():
        res = client().score(
            m,
            {"text": query},
            [{"id": str(i), "text": d} for i, d in enumerate(docs)],
            provision_timeout_s=_timeout(),
        )
        out = []
        for j, s in enumerate(sorted(res["scores"], key=lambda s: -float(s["score"]))):
            out.append({"index": int(s["item_id"]), "score": float(s["score"]), "rank": j})
        return {"results": out, "model": m}

    def fb():
        scored = sorted(((i, _overlap(query, d)) for i, d in enumerate(docs)), key=lambda x: -x[1])
        return {
            "results": [{"index": i, "score": round(s, 4), "rank": r} for r, (i, s) in enumerate(scored)],
            "model": "fallback:token-overlap",
        }

    if not docs:
        return {"results": [], "model": m, "source": "fallback"}
    return cached_call(SERVICE, key_for("rerank", m, query, docs), live if available() and m else None, fb)


# ---------------------------------------------------------------- entities
VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
DTC_RE = re.compile(r"\b([PBCU][0-3][0-9A-F]{3})\b", re.I)
BAY_RE = re.compile(r"\bbay\s*#?\s*(\d+)\b", re.I)
VEH_RE = re.compile(r"\b((?:19|20)\d{2})\s+([A-Z][a-zA-Z\-]+)\s+([A-Z0-9][\w\-]+)")
TIME_RE = re.compile(
    r"\b(?:by|before|at|promised(?: for)?)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|eod|end of day)", re.I
)


def regex_entities(text: str, labels: list[str] | None = None) -> list[dict]:
    labels = [lbl.lower() for lbl in (labels or ["vin", "dtc", "bay", "vehicle", "promise_time"])]
    out: list[dict] = []
    t = text or ""
    if "vin" in labels:
        out += [{"label": "vin", "text": m.group(1).upper(), "score": 1.0} for m in VIN_RE.finditer(t.upper())]
    if "dtc" in labels:
        out += [{"label": "dtc", "text": m.group(1).upper(), "score": 1.0} for m in DTC_RE.finditer(t)]
    if "bay" in labels:
        out += [{"label": "bay", "text": m.group(1), "score": 1.0} for m in BAY_RE.finditer(t)]
    if "vehicle" in labels:
        out += [{"label": "vehicle", "text": " ".join(m.groups()), "score": 0.9} for m in VEH_RE.finditer(t)]
    if "promise_time" in labels:
        out += [{"label": "promise_time", "text": m.group(1), "score": 0.8} for m in TIME_RE.finditer(t)]
    return out


def extract_entities(text: str, labels: list[str]) -> dict:
    m = model("extract")

    def live():
        res = client().extract(m, {"text": text}, labels=list(labels), provision_timeout_s=_timeout())
        res = res[0] if isinstance(res, list) else res
        if res.get("error"):
            return err("extract_item_error", json.dumps(res["error"], default=str))
        ents = [
            {"label": e.get("label"), "text": e.get("text"), "score": float(e.get("score", 0.0))}
            for e in res.get("entities", [])
        ]
        return {"entities": ents, "model": m}

    def fb():
        return {"entities": regex_entities(text, labels), "model": "fallback:regex"}

    return cached_call(SERVICE, key_for("extract", m, text, labels), live if available() and m else None, fb)


# ---------------------------------------------------------------- documents
def _doc_bytes(doc: str | Path | bytes, filename: str | None) -> tuple[bytes, str]:
    if isinstance(doc, (bytes, bytearray)):
        return bytes(doc), (filename or "document.bin")
    p = Path(doc)
    return p.read_bytes(), (filename or p.name)


def _csv_fallback(data: bytes) -> dict:
    text = data.decode("utf-8-sig", errors="replace")
    rows = [
        {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))
    ]
    return {"lines": rows}


def extract_document(
    doc: str | Path | bytes, output_schema: dict, instruction: str = "", filename: str | None = None
) -> dict:
    """Structured extraction from a PDF/CSV/etc via SIE extract(output_schema=)."""
    try:
        data, name = _doc_bytes(doc, filename)
    except Exception as e:
        return err("bad_input", safe_exc(e))
    is_csv = name.lower().endswith(".csv")
    m = model("doc")

    def live():
        res = client().extract(
            m,
            {"document": data},
            output_schema=output_schema,
            instruction=instruction or None,
            provision_timeout_s=_timeout(),
        )
        res = res[0] if isinstance(res, list) else res
        if res.get("error"):
            return err("extract_item_error", json.dumps(res["error"], default=str))
        return {"data": res.get("data") or {}, "model": m, "method": "doc"}

    def fb():
        if is_csv:
            return {"data": _csv_fallback(data), "model": "fallback:csv", "method": "csv"}
        return err("unavailable", "SIE document extraction unavailable and no local parser for this format")

    k = key_for("doc", m, hashlib.sha256(data).hexdigest(), output_schema, instruction)
    return cached_call(SERVICE, k, live if available() and m else None, fb)


def ocr_image(image: str | Path | bytes, instruction: str = "Transcribe all text in this image verbatim.") -> dict:
    """OCR via a vision LLM: generate(prompt, images=[bytes])."""
    try:
        data, _ = _doc_bytes(image, None)
    except Exception as e:
        return err("bad_input", safe_exc(e))
    m = model("vlm")

    def live():
        res = client().generate(
            m, instruction, max_new_tokens=2048, images=[data], temperature=0.0, provision_timeout_s=_timeout()
        )
        return {"text": res.get("text", ""), "model": m}

    k = key_for("ocr", m, hashlib.sha256(data).hexdigest(), instruction)
    return cached_call(SERVICE, k, live if available() and m else None, None)


# ---------------------------------------------------------------- small LLM
def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        mm = re.search(r"\{.*\}", text or "", re.S)
        if mm:
            try:
                return json.loads(mm.group(0))
            except Exception:
                return None
    return None


def llm(messages: list[dict], response_format: dict | None = None, max_tokens: int = 512) -> dict:
    m = model("llm")

    def live():
        res = client().chat_completions(
            m,
            messages,
            max_tokens=max_tokens,
            temperature=0.0,
            response_format=response_format,
            provision_timeout_s=_timeout(),
        )
        text = (res.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        if isinstance(text, list):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        return {"text": text, "json": _parse_json(text) if response_format else None, "model": m}

    k = key_for("llm", m, messages, response_format, max_tokens)
    return cached_call(SERVICE, k, live if available() and m else None, None)


# ---------------------------------------------------------------- warm
def warm() -> dict:
    """Pre-provision every configured model with a tiny request. Never raises."""
    if not available():
        return {"_": "skipped: SIE_API_KEY not set"}
    out: dict[str, str] = {}
    calls = {
        "embed": lambda m: client().encode(m, {"text": "warm"}, provision_timeout_s=_timeout()),
        "rerank": lambda m: client().score(m, {"text": "warm"}, [{"text": "warm"}], provision_timeout_s=_timeout()),
        "extract": lambda m: client().extract(m, {"text": "warm"}, labels=["x"], provision_timeout_s=_timeout()),
        "llm": lambda m: client().chat_completions(
            m, [{"role": "user", "content": "hi"}], max_tokens=1, provision_timeout_s=_timeout()
        ),
        "vlm": lambda m: client().generate(m, "hi", max_new_tokens=1, provision_timeout_s=_timeout()),
        "doc": lambda m: client().extract(m, {"text": "warm"}, output_schema={"type": "object"}, provision_timeout_s=_timeout()),
    }
    for role, fn in calls.items():
        m = model(role)
        if not m:
            out[role] = "skipped: no model"
            continue
        try:
            fn(m)
            out[f"{role}:{m}"] = "ok"
        except Exception as e:
            out[f"{role}:{m}"] = f"error: {safe_exc(e)[:120]}"
    return out
