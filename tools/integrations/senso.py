"""Senso REST adapter (SPEC §8.1): X-API-Key; POST /org/search, /org/search/context, /org/kb/raw (+ poll)."""

from __future__ import annotations

import re
import time
from pathlib import Path

import httpx

from ._common import SEED, cache_dir, cached_call, env, err, has, key_for, safe_exc

SERVICE = "senso"
DOCS_DIR = SEED / "senso_docs"


def available() -> bool:
    return has("SENSO_API_KEY")


def _base() -> str:
    return env("SENSO_BASE_URL", "https://apiv2.senso.ai/api/v1").rstrip("/")


def _headers() -> dict:
    return {"X-API-Key": env("SENSO_API_KEY"), "Content-Type": "application/json"}


def _passages(results: list) -> list[dict]:
    return [
        {
            "content_id": r.get("content_id"),
            "title": r.get("title"),
            "chunk_text": r.get("chunk_text"),
            "score": r.get("score"),
        }
        for r in results or []
    ]


# ---------------------------------------------------------------- fallback
_TOK = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "for", "of", "to", "and", "or", "in", "on", "is", "what", "are", "rules", "rule", "my", "our"}


def _local_docs() -> list[dict]:
    docs = []
    dirs = [DOCS_DIR, cache_dir(SERVICE) / "added"]
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            text = p.read_text(encoding="utf-8", errors="replace")
            first = text.strip().splitlines()[0] if text.strip() else p.stem
            title = first.lstrip("# ").strip() or p.stem
            docs.append({"content_id": f"local:{p.stem}", "title": title, "text": text})
    return docs


def _chunks(text: str) -> list[str]:
    parts = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    return parts or [text]


def _local_search(query: str, max_results: int) -> list[dict]:
    q = {t for t in _TOK.findall(query.lower()) if t not in _STOP}
    hits = []
    for d in _local_docs():
        title_toks = set(_TOK.findall(d["title"].lower()))
        for ch in _chunks(d["text"]):
            toks = set(_TOK.findall(ch.lower()))
            s = len(q & toks) + 2 * len(q & title_toks)
            # crude stemming: "sensors" ~ "sensor"
            s += sum(1 for t in q if t.endswith("s") and t[:-1] in toks)
            if s > 0:
                hits.append({"content_id": d["content_id"], "title": d["title"], "chunk_text": ch[:1200], "score": float(s)})
    hits.sort(key=lambda h: -h["score"])
    return hits[:max_results]


# ---------------------------------------------------------------- API
def search(query: str, max_results: int = 5) -> dict:
    def live():
        r = httpx.post(f"{_base()}/org/search", headers=_headers(), json={"query": query, "max_results": max_results}, timeout=45)
        if r.status_code >= 400:
            return err(f"http_{r.status_code}", r.text[:300])
        j = r.json()
        return {"answer": j.get("answer") or "", "passages": _passages(j.get("results"))}

    def fb():
        ps = _local_search(query, max_results)
        answer = ps[0]["chunk_text"] if ps else ""
        return {"answer": answer, "passages": ps}

    return cached_call(SERVICE, key_for("search", query, max_results), live if available() else None, fb)


def search_context(query: str, max_results: int = 5) -> dict:
    def live():
        r = httpx.post(
            f"{_base()}/org/search/context", headers=_headers(), json={"query": query, "max_results": max_results}, timeout=45
        )
        if r.status_code >= 400:
            return err(f"http_{r.status_code}", r.text[:300])
        return {"passages": _passages(r.json().get("results"))}

    def fb():
        return {"passages": _local_search(query, max_results)}

    return cached_call(SERVICE, key_for("context", query, max_results), live if available() else None, fb)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "doc"


def _local_add(title: str, text: str) -> dict:
    d = cache_dir(SERVICE) / "added"
    d.mkdir(parents=True, exist_ok=True)
    slug = _slug(title)
    (d / f"{slug}.md").write_text(f"# {title}\n\n{text}\n", encoding="utf-8")
    return {"content_id": f"local:{slug}", "status": "complete", "source": "fallback"}


def add_doc(title: str, text: str, wait: bool = True, timeout_s: float = 60) -> dict:
    """POST /org/kb/raw → 202 {kb_node_id}; poll GET /org/kb/nodes/{id}. 409 = identical text exists."""
    if not available():
        return _local_add(title, text)
    try:
        r = httpx.post(f"{_base()}/org/kb/raw", headers=_headers(), json={"title": title, "text": text}, timeout=45)
        if r.status_code == 409:
            cid = None
            try:
                cid = (r.json() or {}).get("content_id") or (r.json() or {}).get("kb_node_id")
            except Exception:
                pass
            return {"content_id": cid or f"dup:{_slug(title)}", "status": "duplicate", "source": "live"}
        if r.status_code == 402:
            out = _local_add(title, text)
            out["warning"] = "senso credits exhausted (402); stored locally"
            return out
        if r.status_code >= 400:
            out = _local_add(title, text)
            out["warning"] = f"senso http_{r.status_code}; stored locally"
            return out
        j = r.json() or {}
        node = j.get("kb_node_id") or j.get("id") or j.get("content_id")
        status = "processing"
        if wait and node:
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                g = httpx.get(f"{_base()}/org/kb/nodes/{node}", headers=_headers(), timeout=30)
                if g.status_code < 400:
                    gj = g.json() or {}
                    content = gj.get("content") or {}
                    st = content.get("processing_status") or gj.get("processing_status")
                    if st == "complete":
                        status = "complete"
                        node = content.get("id") or gj.get("content_id") or node
                        break
                    if st == "failed":
                        status = "failed"
                        break
                time.sleep(2)
        return {"content_id": node, "status": status, "source": "live"}
    except Exception as e:
        out = _local_add(title, text)
        out["warning"] = f"senso error: {safe_exc(e)[:120]}; stored locally"
        return out


def local_docs_dir() -> Path:
    return DOCS_DIR
