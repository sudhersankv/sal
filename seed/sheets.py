"""Write the shop's spreadsheets (Airbyte source, D-007) to seed/shop_sheets/*.csv."""
from __future__ import annotations

import csv
from pathlib import Path

from seed.generate import build_bookings, build_catalog

OUT = Path(__file__).with_name("shop_sheets")
PRICE_COLS = ["sku", "vendor_part_no", "brand", "oem_part_no", "description", "price", "core_charge",
              "qty_on_hand", "eta_minutes"]


def write(out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    cat = build_catalog()
    paths = []
    p = out / "bookings.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["booking_id", "date", "service_code", "vehicle", "parts_needed"])
        for b in build_bookings(cat):
            w.writerow([b["booking_id"], b["date"], b["service_code"], b["vehicle"],
                        "; ".join(f"{x['sku']} x{x['qty']}" for x in b["parts_needed"])])
    paths.append(p)
    for vid in ("mission", "bayshore"):
        p = out / f"price_sheet_{vid}.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=PRICE_COLS, extrasaction="ignore")
            w.writeheader()
            for r in cat:
                if r["vendor_id"] == vid:
                    w.writerow(r)
        paths.append(p)
    return paths


def main():
    for p in write():
        print("wrote", p.relative_to(OUT.parent.parent))


if __name__ == "__main__":
    main()
