# scene3d: Sal's parts room (realistic 3D inventory view)

Owned by `scene3d`. A real-time three.js stockroom for *Mission Street Auto* (fictional): steel boltless
shelving with labeled bins of procedural parts, a parts counter with receiving area, and a roll-up
receiving door. The parts are the heroes; each bin's stack height shows qty. Green `#22c550` is
reserved for Sal's actions (holograms, ghosts of incoming parts, scan sweeps).

## Mount (for `ui`)

```ts
import { createShopScene } from "./scene3d";
import type { SalEvent, InventoryItem, ShopScene } from "./scene3d";

const room: ShopScene = createShopScene(el, {
  quality: "high",                       // "low" = no post-processing
  onSelect: (sku) => sku && openItem(sku), // click on a bin
  onHover: (sku) => {},                    // optional
});
room.setInventory(await (await fetch("/api/inventory")).json()); // InventoryItem[] (call again on refresh)
es.onmessage = (m) => room.handleEvent(JSON.parse(m.data) as SalEvent);
room.setFocus("shelf:oil filter");      // 'overview' | 'counter' | 'receiving' | `shelf:${part_type}`
room.dispose();                         // on unmount; frees GPU resources
```

- `el` is any sized element; the scene appends a canvas + label layer, fills it, and auto-resizes
  (ResizeObserver). `resize()` is there if you need to force it.
- Without `setInventory`, a realistic demo inventory is shown (so the view is never empty).
- Bin status: normal (neutral), low = qty < min_qty (amber), out = qty 0 (red),
  incoming = `incoming_qty > 0` (green ghost parts stacked on top).
- Events are queued so bursts animate in order.

## Dev page

`npm --prefix ui/web run dev` → http://localhost:5173/scene3d.html replays `ui/fixtures/sample_week.jsonl`.
Query params: `?quality=low`, `?speed=2`.

## Event reactions

| type | reaction |
|---|---|
| inventory.checked | green scan-light sweep across the shelves |
| stock.low | bin (refs.sku) pulses amber; qty set from data.have |
| restock.planned | green ghost parts appear in bins to be refilled |
| vendors.compared | holographic vendor cards over the counter |
| part.rejected | matching card dissolves with the reason |
| part.chosen | chosen card glows green |
| order.placed | a box label prints at the counter; counter orders: van leaves the receiving door; shopify: parcel queued |
| order.delivered | parcel arrives at receiving, opens, parts fly into their bin, fill rises |
| statement.parsed | document scans at the counter |
| escalation / identity.verified / approval.* | badge-check hologram |
| chat.message | small ping over the counter |
| scorecard.built / rule.* / metrics.updated | wall screen updates |

## Assets

All geometry, materials and textures are procedural (canvas-generated); environment light is three's
`RoomEnvironment` through PMREM. No external models, HDRIs, brands or logos.
