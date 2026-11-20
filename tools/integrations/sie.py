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
    "llm": ("SIE_LLM_MODEL", [], "text"),
    "ocr": ("SIE_OCR_MODEL", [], "data"),
    "vlm": ("SIE_VLM_MODEL", [], "data"),
    "doc": ("SIE_DOC_MODEL", [], "data"),
}


# Live-verified defaults (2026-11-20): GLM relay answers in ~1s; docling parses PDFs in <1s;
# docling:ocr reads scans in ~6s; LightOnOCR cold-provisions (minutes) so it's second in line for OCR.
DEFAULTS = {
    "llm": "zai-org/GLM-5.3-Flash:relay",
    "doc": "docling",
    "ocr": "docling:ocr",
    "vlm": "lightonai/LightOnOCR-3-4B:markdown",
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
    m = env(var, DEFAULTS.get(role, ""))
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


# ---------------------------------------------------------------- small LLM
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def _strip_reasoning(text: str) -> str:
    text = _THINK.sub("", text or "")
    if "</think>" in text:  # opening tag eaten by the chat template
        text = text.split("</think>", 1)[1]
    return text.strip()


def _parse_json(text: str) -> Any:
    t = re.sub(r"^`{3}(?:json)?\s*|\s*`{3}$", "", (text or "").strip())
    try:
        return json.loads(t)
    except Exception:
        mm = re.search(r"[\{\[].*[\}\]]", t, re.S)
        if mm:
            try:
                return json.loads(mm.group(0))
            except Exception:
                return None
    return None


def _llm_timeout() -> float:
    try:
        return float(env("SIE_LLM_TIMEOUT", "180"))
    except ValueError:
        return 180.0


def llm(messages: list[dict], response_format: dict | None = None, max_tokens: int = 1024) -> dict:
    """chat_completions on SIE_LLM_MODEL (default GLM-5.3-Flash relay, a reasoning model).

    Verified live: the relay rejects reasoning_effort / chat_template_kwargs.enable_thinking / thinking, and
    reasoning tokens count against max_tokens, so we floor max_tokens at 512 and strip any <think> block.
    """
    m = model("llm")
    max_tokens = max(512, int(max_tokens))

    def live():
        res = client().chat_completions(
            m,
            messages,
            max_tokens=max_tokens,
            temperature=0.0,
            response_format=response_format,
            provision_timeout_s=_timeout(),
            read_timeout_s=_llm_timeout(),
        )
        ch = (res.get("choices") or [{}])[0]
        text = ch.get("message", {}).get("content") or ""
        if isinstance(text, list):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        text = _strip_reasoning(text)
        if not text:
            return err("empty_completion", f"finish_reason={ch.get('finish_reason')}; raise max_tokens")
        return {
            "text": text,
            "json": _parse_json(text) if response_format else None,
            "model": m,
            "finish_reason": ch.get("finish_reason"),
        }

    k = key_for("llm", m, messages, response_format, max_tokens)
    return cached_call(SERVICE, k, live if available() and m else None, None)


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


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")


def _extract_text(m: str, item: dict, provision_timeout_s: float) -> str:
    res = client().extract(m, item, provision_timeout_s=provision_timeout_s)
    res = res[0] if isinstance(res, list) else res
    if res.get("error"):
        raise RuntimeError(json.dumps(res["error"], default=str)[:300])
    d = res.get("data") or {}
    return str(d.get("markdown") or d.get("text") or "")


def document_text(doc: str | Path | bytes, filename: str | None = None) -> dict:
    """PDF/DOCX/CSV/etc → text via SIE docling extract(Item(document=bytes)). Images go through ocr_image()."""
    try:
        data, name = _doc_bytes(doc, filename)
    except Exception as e:
        return err("bad_input", safe_exc(e))
    if name.lower().endswith(IMAGE_EXT):
        return ocr_image(data)
    m = model("doc")

    def live():
        text = _extract_text(m, {"document": data}, _timeout())
        if not text.strip():
            return err("empty_text", f"{m} returned no text")
        return {"text": text, "model": m}

    k = key_for("doctext", m, hashlib.sha256(data).hexdigest())
    return cached_call(SERVICE, k, live if available() and m else None, None)


def ocr_image(image: str | Path | bytes, instruction: str = "") -> dict:
    """Scan → text: SIE extract(Item(images=[bytes])) on docling:ocr (~6s), then LightOnOCR (cold; long timeout)."""
    try:
        data, _ = _doc_bytes(image, None)
    except Exception as e:
        return err("bad_input", safe_exc(e))
    chain = [(model("ocr"), _timeout()), (model("vlm"), float(env("SIE_VLM_TIMEOUT", "300")))]
    chain = [(m, t) for m, t in chain if m]

    def live():
        errors = []
        for m, t in chain:
            try:
                text = _extract_text(m, {"images": [data]}, t)
                if text.strip():
                    return {"text": text, "model": m}
                errors.append(f"{m}: empty")
            except Exception as e:
                errors.append(f"{m}: {safe_exc(e)[:120]}")
                log(f"[sie] ocr via {m} failed: {errors[-1]}")
        return err("ocr_failed", "; ".join(errors))

    k = key_for("ocr2", [m for m, _ in chain], hashlib.sha256(data).hexdigest())
    return cached_call(SERVICE, k, live if available() and chain else None, None)


def extract_document(
    doc: str | Path | bytes, output_schema: dict, instruction: str = "", filename: str | None = None
) -> dict:
    """Structured extraction: docling (or OCR for images) → text → llm() with a json_schema response_format.

    Returns {"data": dict, "model": "<text model>+<llm>", "method": "doc"|"ocr"|"csv", "text_chars", "source"}.
    """
    try:
        data, name = _doc_bytes(doc, filename)
    except Exception as e:
        return err("bad_input", safe_exc(e))
    is_img = name.lower().endswith(IMAGE_EXT)
    if not available():
        if name.lower().endswith(".csv"):
            return {"data": _csv_fallback(data), "model": "fallback:csv", "method": "csv", "source": "fallback"}
        return err("unavailable", "SIE_API_KEY not set")
    t = ocr_image(data) if is_img else document_text(data, name)
    if "error" in t:
        return t
    ocr_hint = (
        "\nThe DOCUMENT is noisy OCR of a scan: silently fix obvious OCR errors (I/1, O/0, S/5, ':' for '.', "
        "missing spaces, stray dots) using the patterns of the other rows; if a row's date/ids are missing, "
        "infer them from neighbouring rows. Do not deliberate at length; answer directly."
        if is_img
        else "\nAnswer directly without lengthy deliberation."
    )
    prompt = (
        (instruction or "Extract the structured data described by the JSON schema.")
        + ocr_hint
        + "\nReturn ONLY JSON matching this schema (numbers as numbers, no commentary):\n"
        + json.dumps(output_schema)
        + "\n\nDOCUMENT:\n"
        + t["text"]
    )
    rf = {"type": "json_schema", "json_schema": {"name": "extraction", "schema": output_schema}}
    r = llm([{"role": "user", "content": prompt}], response_format=rf, max_tokens=int(env("SIE_DOC_MAX_TOKENS", "16384")))
    if "error" in r:
        return r
    if not isinstance(r.get("json"), dict):
        return err("bad_json", (r.get("text") or "")[:200])
    src = "cache" if "cache" in (t.get("source"), r.get("source")) else r.get("source", "live")
    return {
        "data": r["json"],
        "model": f"{t['model']}+{r['model']}",
        "method": "ocr" if is_img else "doc",
        "text_chars": len(t["text"]),
        "source": src,
    }


STATEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"},
        "statement_date": {"type": "string", "description": "YYYY-MM-DD"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "invoice_no": {"type": "string"},
                    "sku": {"type": "string"},
                    "desc": {"type": "string"},
                    "qty": {"type": "integer"},
                    "amount": {"type": "number"},
                    "core_credit": {"type": "number", "description": "core credit applied on this line, 0 if none"},
                },
                "required": ["date", "invoice_no", "sku", "desc", "qty", "amount", "core_credit"],
            },
        },
        "total": {"type": "number"},
    },
    "required": ["statement_date", "lines", "total"],
}
STATEMENT_INSTRUCTION = (
    "This is a parts vendor statement of account. Extract every invoice line in order. "
    "core_credit is the core credit amount shown for that line (0.00 if blank). total is the statement total due."
)


def _num(x, cast=float):
    try:
        return cast(float(str(x).replace("$", "").replace(",", "") or 0))
    except (TypeError, ValueError):
        return cast(0)


def parse_statement(path: str | Path) -> dict:
    """Vendor statement (pdf / png scan / csv) → parse_vendor_statement contract shape (minus vendor_id)."""
    p = Path(path)
    if p.suffix.lower() == ".csv" and not available():
        lines = _csv_fallback(p.read_bytes())["lines"]
        for ln in lines:
            ln["qty"] = _num(ln.get("qty"), int)
            ln["amount"] = _num(ln.get("amount"))
            ln["core_credit"] = _num(ln.get("core_credit"))
        total = round(sum(x["amount"] - x["core_credit"] for x in lines), 2)
        return {"statement_date": None, "lines": lines, "total": total, "model": "fallback:csv", "method": "csv",
                "source": "fallback"}
    r = extract_document(p, STATEMENT_SCHEMA, STATEMENT_INSTRUCTION)
    if "error" in r:
        return r
    d = r["data"]
    lines = [
        {
            "date": str(ln.get("date", "")),
            "invoice_no": str(ln.get("invoice_no", "")),
            "sku": str(ln.get("sku", "")),
            "desc": str(ln.get("desc", "")),
            "qty": _num(ln.get("qty") or 1, int),
            "amount": _num(ln.get("amount")),
            "core_credit": _num(ln.get("core_credit")),
        }
        for ln in d.get("lines") or []
        if isinstance(ln, dict)
    ]
    return {
        "statement_date": d.get("statement_date"),
        "vendor_name": d.get("vendor_name"),
        "lines": lines,
        "total": _num(d.get("total")),
        "model": r["model"],
        "method": r["method"],
        "source": r["source"],
    }


# ---------------------------------------------------------------- warm
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
)


def warm(provision_timeout_s: float = 600) -> dict:
    """Fire every configured model once (provision_timeout_s=600) so serverless pools are hot. Never raises."""
    if not available():
        return {"_": "skipped: SIE_API_KEY not set"}
    import time

    pt = provision_timeout_s
    calls = {
        "embed": lambda m: client().encode(m, {"text": "warm"}, provision_timeout_s=pt),
        "rerank": lambda m: client().score(m, {"text": "warm"}, [{"text": "warm"}], provision_timeout_s=pt),
        "extract": lambda m: client().extract(m, {"text": "VIN 1HGCM82633A004352"}, labels=["vin"], provision_timeout_s=pt),
        "llm": lambda m: client().chat_completions(
            m, [{"role": "user", "content": "Reply: ok"}], max_tokens=512, provision_timeout_s=pt
        ),
        "doc": lambda m: client().extract(m, {"document": b"warm,1\n"}, provision_timeout_s=pt),
        "ocr": lambda m: client().extract(m, {"images": [_TINY_PNG]}, provision_timeout_s=pt),
        "vlm": lambda m: client().extract(m, {"images": [_TINY_PNG]}, provision_timeout_s=pt),
    }
    out: dict[str, str] = {}
    for role, fn in calls.items():
        m = model(role)
        if not m:
            out[role] = "skipped: no model"
            continue
        t0 = time.time()
        try:
            fn(m)
            out[f"{role}:{m}"] = f"ok {time.time() - t0:.1f}s"
        except Exception as e:
            out[f"{role}:{m}"] = f"error after {time.time() - t0:.1f}s: {safe_exc(e)[:120]}"
        log(f"[sie warm] {role}:{m} -> {out[f'{role}:{m}']}")
    return out


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "warm"
    if cmd == "warm":
        print(json.dumps(warm(), indent=1))
    elif cmd == "models":
        print(json.dumps(models(), indent=1))
    elif cmd == "statement" and len(sys.argv) > 2:
        print(json.dumps(parse_statement(sys.argv[2]), indent=1))
    else:
        print("usage: python -m tools.integrations.sie [warm|models|statement <path>]")
