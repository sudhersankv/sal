"""`python -m tools.integrations.smoke` — service | key? | live call ok? | fallback in use. Never prints secrets."""

from __future__ import annotations

import sys

from . import airbyte, amplitude, cognee, nhtsa, persona, senso, shopify, sie, statsig_client

LIVE = "--no-live" not in sys.argv


def _row(name, mod, probe):
    key = mod.available()
    live, fb, note = "-", "yes", ""
    if key and LIVE:
        try:
            ok, note = probe()
            live = "ok" if ok else "FAIL"
            fb = "no" if ok else "yes"
        except Exception as e:  # noqa: BLE001
            live, note = "FAIL", type(e).__name__
    elif name == "nhtsa" and LIVE:
        try:
            ok, note = probe()
            live, fb = ("ok", "no") if ok else ("FAIL", "cache")
        except Exception as e:  # noqa: BLE001
            live, note = "FAIL", type(e).__name__
    return (name, "yes" if key else "no", live, fb, note)


def _sie():
    r = sie.embed(["smoke test"])
    return r.get("source") == "live", f"embed={sie.model('embed') or '?'}"


def _senso():
    r = senso.search_context("no-buy list")
    return r.get("source") == "live", f"{len(r.get('passages', []))} passages"


def _persona():
    r = persona.create_inquiry("smoke test", 0.0)
    return r.get("method") == "persona", r.get("status", "")


def _airbyte():
    r = airbyte.search_shop_data("oil change", "bookings", 3)
    return r.get("source") == "airbyte", f"{len(r.get('records', []))} records"


def _shopify():
    return bool(shopify.get_token()), "token"


def _cognee():
    r = cognee.recall("Bayshore late deliveries", 2)
    return r.get("source") == "live", f"{len(r.get('facts', []))} facts"


def _statsig():
    v = statsig_client.variant()
    return v["source"] == "live", f"gate={v['gate_routing_v2']} strategy={v['strategy']}"


def _amplitude():
    r = amplitude.track("sal_smoke", {"ok": True})
    amplitude.flush()
    return r.get("source") == "live", ""


def _nhtsa():
    r = nhtsa.decode_vin("19XFB2F59EE000000")  # 2014 Civic pattern; decode only needs WMI/VDS/year
    return "error" not in r and r.get("source") == "live", f"{r.get('year')} {r.get('make')} {r.get('model')} ({r.get('source', r.get('error'))})"


def main() -> None:
    rows = [
        _row("sie", sie, _sie),
        _row("senso", senso, _senso),
        _row("persona", persona, _persona),
        _row("airbyte", airbyte, _airbyte),
        _row("shopify", shopify, _shopify),
        _row("cognee", cognee, _cognee),
        _row("statsig", statsig_client, _statsig),
        _row("amplitude", amplitude, _amplitude),
        _row("nhtsa", nhtsa, _nhtsa),
    ]
    hdr = ("service", "key?", "live call ok?", "fallback in use", "note")
    w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(5)]
    line = lambda r: " | ".join(str(c).ljust(w[i]) for i, c in enumerate(r))  # noqa: E731
    print(line(hdr))
    print("-+-".join("-" * x for x in w))
    for r in rows:
        print(line(r))
    statsig_client.shutdown()


if __name__ == "__main__":
    main()
