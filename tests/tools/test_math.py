import pytest

from tools import context, impl


@pytest.mark.parametrize("w,retail,rule", [
    (10, 25.0, "R2.1"), (25, 62.5, "R2.1"), (41, 82.0, "R2.2"), (75, 150.0, "R2.2"),
    (100, 170.0, "R2.3"), (200, 340.0, "R2.3"), (260, 390.0, "R2.4"),
])
def test_quote_matrix(w, retail, rule):
    q = impl.compute_quote(w)
    assert (q["retail"], q["tier_rule_id"]) == (retail, rule)


def test_quote_rejects_negative():
    assert "error" in impl.compute_quote(-1)


def test_restock_bundles_brake_cleaner_to_clear_free_shipping():
    context.set_context(day="wed")
    plan = impl.plan_restock()
    assert plan["subtotal_before_bundle"] == 132.0
    assert plan["bundle_added"]["sku"] == "BRK-CLN" and plan["bundle_added"]["order_qty"] == 6
    assert plan["total"] == 153.0 >= plan["free_ship_threshold"]
    qty = {ln["sku"]: ln["order_qty"] for ln in plan["lines"]}
    assert sum(v for k, v in qty.items() if k.startswith("OF-")) == 9 and qty["WIPER-22"] == 4


def test_restock_no_bundle_when_gap_too_big():
    inv = [{"sku": "A", "qty": 0, "min_qty": 0, "max_qty": 10}, {"sku": "B", "qty": 0, "min_qty": 0, "max_qty": 99}]
    cat = {"A": {"price": 10.0}, "B": {"price": 1.0}}
    plan = impl.restock_plan(inv, [{"parts_needed": [{"sku": "A", "qty": 5}]}], cat, 150.0)
    assert plan["total"] == 50.0 and plan["bundle_added"] is None


def test_scorecard_sql_planted_pattern():
    context.set_context(day="sun")
    per = {r["vendor_id"]: r for r in impl.get_vendor_history(part_type="starter,alternator", days=90)["per_vendor"]}
    assert per["bayshore"]["late_rate"] == 0.375
    assert per["bayshore"]["missed_core_credits"] == 2 and per["bayshore"]["missed_core_amount"] == 90.0
    assert per["mission"]["late"] == 0


def test_statement_text_rows_from_doc_text():
    text = ("DATE INVOICE SKU DESCRIPTION QTY AMOUNT CORE CR 2026-10-16 BSI-104468 BSP101887  MOTORCRAFT BRF-1586 "
            "BRAKE PADS, FRONT  1  42.42  0.00 2026-10-22 BSI-104500 BSP100001 DENSO STARTER  1  152.00  45.00")
    rows = impl._text_rows(text)
    assert [(r["invoice_no"], r["amount"], r["core_credit"]) for r in rows] == [
        ("BSI-104468", 42.42, 0.0), ("BSI-104500", 152.0, 45.0)]
