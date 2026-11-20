# Demo script (SPEC §10)

Simulated week of **Mon Nov 16 – Sun Nov 22, 2026**. Shop: "Mission Street Auto" (fictional), 4 bays.

### MON 09:12 — urgent buy (target: ~14 events)
1. `repair_order.created` (actor tech): "Civic in bay 2, P0141, VIN …, customer promised by 3 PM" → SIE extract → RO-1042.
2. `part.identified`: decode VIN (NHTSA) → 2014 Civic 1.8L; P0141 → **downstream** O2 sensor (bank 1 sensor 2), OEM part no from `fitments`.
3. `context.retrieved` ×3: Senso rules (R4, R5, R7), NHTSA complaints for the car (context only), SingleStore brand history (ValuMax 2 comebacks), Cognee facts.
4. `vendors.compared`: Mission, Bayshore, PartsDepot listings; SIE verdicts (one Bayshore listing is the *upstream* sensor → `different`).
5. `part.rejected`: ValuMax @ Bayshore $33 — R4 no-buy + 2 comebacks (sources Senso, SingleStore).
6. `part.rejected`: Denso @ PartsDepot $38 — 2-day ship violates R5.
7. `part.rejected` (or not offered): Bayshore NTK — ETA 3:10 PM > promise.
8. `part.chosen`: Denso @ Mission $41, ETA 10:20.
9. `quote.sent` / `approval.requested`: $41 → $82 (R2 ×2.0) + labor line (fixed, from RO) to car owner via Firedrill Gmail.
10. `approval.received` (actor car_owner): approved.
11. `order.placed`: Mission order, `money.wholesale=41`.
12. `payment.recorded`: Firedrill Stripe test payment for the approved total.
13. `order.delivered` (sim advances clock) → `sal.summary`: one paragraph + meters update.

### WED 07:30 — proactive restock (no trigger)
1. `inventory.checked` → `get_bookings(7)` → `plan_restock`.
2. `stock.low` ×3 (oil filters for Civic/CR-V/Camry, wipers).
3. `restock.planned`: 9 filters + 4 wipers; total $132 → adds brake cleaner ×6 to clear $150 free shipping (R6) → `reason` cites R6.
4. `order.placed` on **Shopify** (real order GID, admin URL) → `sal.summary`.

### SUN 18:00 — gets smarter
1. `scorecard.built`: SQL over 90 days → Bayshore late 37.5% on starters/alternators, 2 missed core credits ($90).
2. `context.retrieved`: Cognee recall of observed facts.
3. `rule.proposed`: "Route starters & alternators to Mission Auto Supply" with evidence (SingleStore + Cognee sources) and projected savings.
4. Owner approves (UI button / sim) → `rule.approved` (written to Senso, remembered in Cognee) → `gate.enabled` (`sal_vendor_routing_v2` ON).
5. Sim replays a starter job with gate OFF vs ON → `metrics.updated`: on-time %, expected late-penalty cost, escalations. Amplitude shows both variants.

### Stretch FRI 16:00 — statement reconciliation
Bayshore statement (PDF/CSV) → line items → join `purchase_history` → 2 missing core credits → `escalation` "dispute drafted" (not sent).

### Expected escalation demo (optional 10s)
TUE: F-150 alternator $260 → R1 spend cap → `escalation` → owner approves in UI → order placed.
