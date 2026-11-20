"""The shop's rule docs (SPEC §8.1): seeded into Senso and mirrored to seed/senso_docs/*.md."""
from __future__ import annotations

RULES = [
    ("R1", "Spend cap", "Any single order over $200 needs the shop owner's approval, with the owner's identity "
     "verified (Persona) before the order is placed."),
    ("R2", "Markup matrix", "Wholesale to retail: up to $25 x2.5; $25-75 x2.0; $75-200 x1.7; over $200 x1.5."),
    ("R3", "Margin target", "Weekly parts margin must stay at or above 45%."),
    ("R4", "No-buy list", "Do not buy brand ValuMax (economy brand) for sensors, after repeated comebacks."),
    ("R5", "Urgent jobs", "Car on a lift: buy from a local counter only; the vendor's promise time must beat the "
     "bay's promise time to the customer."),
    ("R6", "Restocks", "Restocks go to the online channel when possible; bundle shop supplies to clear the "
     "free-shipping threshold when the order is within $25 of it."),
    ("R7", "Preferred O2 sensor brands", "For oxygen and air/fuel sensors prefer Denso, NTK, then Bosch."),
    ("R8", "Customer cards", "Never pay with a customer's card on file without the customer's explicit approval."),
]

DOCS: list[tuple[str, str, str]] = [  # (slug, title, text)
    ("shop-mandate", "Shop mandate", """Mission Street Auto: Sal's mandate (set by the owner)

Sal is the parts department for Mission Street Auto, a 4-bay independent shop in San Francisco.
Sal sources parts per repair order, keeps consumables stocked ahead of bookings, and manages vendors.

Standing rules:
- R1 Spend cap: any single order over $200 needs the shop owner's approval, with the owner's identity verified (Persona) before the order is placed.
- R2 Markup matrix: see "Markup matrix".
- R3 Margin target: weekly parts margin at or above 45%.
- R4 No-buy list: see "No-buy list" (ValuMax sensors).
- R5 Urgent jobs: see "Urgent job rules".
- R6 Restocks: see "Restock rules".
- R7 Preferred brands: see "Preferred brands by part type".
- R8 Never pay with a customer's card on file without the customer's explicit approval.

Every decision Sal makes must cite its source: a rule here, a ledger row, or a vendor record."""),
    ("markup-matrix", "Markup matrix", """Markup matrix (rule R2)

Retail price to the customer = wholesale cost x multiplier, by wholesale tier:
- Wholesale up to $25.00: x2.5
- Wholesale $25.01 to $75.00: x2.0
- Wholesale $75.01 to $200.00: x1.7
- Wholesale over $200.00: x1.5

Example: a $41.00 O2 sensor quotes at $82.00 retail (x2.0). Labor is quoted separately from the repair order.
Weekly parts margin target (R3): at or above 45%."""),
    ("no-buy-list", "No-buy list", """No-buy list (rule R4)

- ValuMax (economy brand): do NOT buy for any sensor (oxygen sensors, air/fuel sensors, ABS sensors, cam/crank sensors).
  Reason: repeated comebacks on ValuMax downstream O2 sensors (2 comebacks in the last 90 days). A comeback costs the shop the labor twice.
- ValuMax for non-sensor parts: allowed only for shop supplies, never on a customer car under warranty.

Enforced in code: the order tools reject a no-buy brand and escalate to the owner."""),
    ("urgent-job-rules", "Urgent job rules", """Urgent job rules (rule R5)

When a car is on a lift (bay occupied) the job is urgent:
- Buy from a local counter vendor only (Mission Auto Supply or Bayshore Parts Co.). Online orders (2-day ship) are not allowed for urgent jobs.
- The vendor's delivery promise must beat the bay's promise time to the customer, with at least 2 hours to spare for the install.
- If no counter can deliver in time, escalate to the owner; do not quietly miss the promise.
- Quote the customer (R2 markup) and get their approval before ordering. Never pay with a customer's card on file without explicit approval (R8)."""),
    ("restock-rules", "Restock rules", """Restock rules (rule R6)

- Every Wednesday morning Sal checks the next 7 days of bookings against shelf inventory.
- Order quantity per item = parts needed by bookings in the next 7 days + min shelf quantity - quantity on hand (never negative).
- Restocks go to the online channel (PartsDepot Online) when possible: cheaper, and nothing is waiting on the part.
- PartsDepot ships free at $150. If the restock is within $25 of $150, bundle shop supplies we always use (brake cleaner, shop towels, bulbs) to clear free shipping instead of paying shipping.
- Single order over $200 still needs owner approval (R1)."""),
    ("vendor-mission", "Vendor profile — Mission Auto Supply", """Vendor profile: Mission Auto Supply (vendor_id mission)

- Type: local counter, van delivery 45-70 minutes. Order cutoff 5:30 PM.
- Pricing: about 10-15% above Bayshore on most lines.
- Reliability: on time about 95% over the last 90 days.
- Core credits: applied on the invoice at return.
- Account: Net 30. Part numbering: MAS- SKUs, line code + part number (e.g. DEN-2344429).
- Good for: urgent jobs, starters and alternators, anything with a core."""),
    ("vendor-bayshore", "Vendor profile — Bayshore Parts Co.", """Vendor profile: Bayshore Parts Co. (vendor_id bayshore)

- Type: local counter, quotes 30-60 minute delivery. Order cutoff 4:30 PM.
- Pricing: usually the cheapest counter in the area. Carries the ValuMax economy line.
- Reliability: watch starters and alternators (ships from their warehouse, often late).
- Core credits: issued on the monthly statement, not on the invoice. Check every statement.
- Account: Net 30. Part numbering: BSP SKUs, line code + space + part number (e.g. "NGK 25012")."""),
    ("vendor-partsdepot", "Vendor profile — PartsDepot Online", """Vendor profile: PartsDepot Online (vendor_id partsdepot)

- Type: online store (Shopify), 2-day ground shipping. Order cutoff 3:00 PM for same-day dispatch.
- Pricing: usually cheapest overall, best on filters, wipers, fluids and shop supplies.
- Free shipping on orders of $150 or more.
- Not for urgent jobs (R5): a car on a lift cannot wait 2 days.
- Account: Net 30. SKUs: PD-<line>-<part number>."""),
    ("preferred-brands", "Preferred brands by part type", """Preferred brands by part type (rule R7)

- Oxygen sensors and air/fuel sensors: Denso, NTK, then Bosch. Never ValuMax (R4).
- Starters and alternators: OE-supplier remanufactured (Denso, Bosch, Motorcraft for Ford, ACDelco for GM).
- Brake pads: Akebono (ceramic) or Wagner. Rotors: Bosch or Wagner.
- Belts: Gates. Chassis/steering: Moog.
- Filters and fluids: OE (Honda, Toyota, Nissan, Motorcraft, ACDelco) or Bosch/Denso.
- Wipers: Bosch ICON."""),
]
