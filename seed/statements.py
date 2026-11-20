"""Bayshore November statement for FRI bill parsing (D-003): CSV, text PDF, and a PNG "scan".

Lines = every Bayshore invoice in the statement period. `core_credit` = core credit applied on the
statement; the two planted misses show 0.00 where a $45 core was returned -> reconciliation finds $90.
Join key: statement invoice_no == orders.external_ref.
"""
from __future__ import annotations

import csv
from pathlib import Path

from seed import expected as X
from seed.generate import build_catalog, build_history

OUT = Path(__file__).with_name("statements")
COLS = ["date", "invoice_no", "sku", "desc", "qty", "amount", "core_credit"]
HEADER = ["BAYSHORE PARTS CO.", "1450 Bayshore Blvd, San Francisco CA (fictional)",
          "STATEMENT OF ACCOUNT", "Account: MISSION STREET AUTO  #MSA-2231",
          f"Statement date: {X.STATEMENT_DATE}   Period: {X.STATEMENT_PERIOD[0]} to {X.STATEMENT_PERIOD[1]}",
          "Terms: Net 30. Core credits for returned cores are applied on this statement."]


def lines() -> list[dict]:
    cat = build_catalog()
    desc = {c["sku"]: c["description"].split(" | ")[0] for c in cat if c["vendor_id"] == "bayshore"}
    h = build_history(cat)
    ol = {r["order_id"]: r for r in h["order_lines"]}
    ph = {r["order_id"]: r for r in h["purchase_history"]}
    out = []
    lo, hi = X.STATEMENT_PERIOD
    for o in h["orders"]:
        d = o["placed_at"][:10]
        if o["vendor_id"] != "bayshore" or not (lo <= d <= hi):
            continue
        line = ol[o["order_id"]]
        out.append(dict(date=d, invoice_no=o["external_ref"], sku=line["sku"], desc=desc[line["sku"]][:44],
                        qty=line["qty"], amount=f"{o['total']:.2f}",
                        core_credit=f"{ph[o['order_id']]['core_credit_received']:.2f}"))
    return out


def totals(rows) -> tuple[float, float, float]:
    charges = sum(float(r["amount"]) for r in rows)
    credits = sum(float(r["core_credit"]) for r in rows)
    return charges, credits, charges - credits


def text_lines(rows) -> list[str]:
    t = list(HEADER) + [""]
    t.append(f"{'DATE':<11}{'INVOICE':<11}{'SKU':<11}{'DESCRIPTION':<45}{'QTY':>4}{'AMOUNT':>10}{'CORE CR':>9}")
    for r in rows:
        t.append(f"{r['date']:<11}{r['invoice_no']:<11}{r['sku']:<11}{r['desc']:<45}{r['qty']:>4}"
                 f"{r['amount']:>10}{r['core_credit']:>9}")
    c, cr, due = totals(rows)
    t += ["", f"{'Charges':>82}{c:>10.2f}", f"{'Core credits':>82}{-cr:>10.2f}", f"{'BALANCE DUE':>82}{due:>10.2f}"]
    return t


def write_csv(rows, path: Path):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


def write_pdf(text: list[str], path: Path):
    """Minimal hand-written PDF (Courier, extractable text). Landscape letter."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")
    body = ["BT", "/F1 7.5 Tf", "9 TL", "30 580 Td"] + [f"({esc(s)}) '" for s in text] + ["ET"]
    stream = "\n".join(body).encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 792 612] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def write_png(text: list[str], path: Path):
    """A slightly rotated, noisy greyscale 'scan' of the statement."""
    import random

    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    try:
        font = ImageFont.truetype("cour.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    w, h = 1250, 60 + 24 * len(text) + 60
    img = Image.new("L", (w, h), 248)
    d = ImageDraw.Draw(img)
    for i, s in enumerate(text):
        d.text((40, 40 + 24 * i), s, fill=25, font=font)
    rng = random.Random(42)
    px = img.load()
    for _ in range(w * h // 60):
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = rng.randint(150, 230)
    img = img.rotate(0.6, resample=Image.BICUBIC, fillcolor=240).filter(ImageFilter.GaussianBlur(0.5))
    img.save(path, optimize=True)


def main():
    OUT.mkdir(exist_ok=True)
    rows = lines()
    text = text_lines(rows)
    stem = "bayshore_2026-11"
    write_csv(rows, OUT / f"{stem}.csv")
    write_pdf(text, OUT / f"{stem}.pdf")
    write_png(text, OUT / f"{stem}_scan.png")
    missing = [r for r in rows if r["core_credit"] == "0.00" and "STARTER" in r["desc"] or
               r["core_credit"] == "0.00" and "ALTERNATOR" in r["desc"]]
    print(f"statements: {len(rows)} lines, {len(missing)} cores without credit -> seed/statements/{stem}.*")


if __name__ == "__main__":
    main()
