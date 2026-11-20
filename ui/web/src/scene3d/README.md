# scene3d: realistic 3D shop view

Owned by `scene3d`. A real-time three.js interior of *Mission Street Auto* (fictional 4-bay shop)
that reacts to Sal's events. Green `#22c550` is reserved for Sal's actions.

## Mount (for `ui`)

```ts
import { createShopScene } from "./scene3d";
import type { SalEvent, ShopScene } from "./scene3d";

const shop: ShopScene = createShopScene(document.getElementById("shop")!, { quality: "high" });
eventSource.onmessage = (m) => shop.handleEvent(JSON.parse(m.data) as SalEvent);
shop.setFocus("counter");      // optional manual camera focus
window.addEventListener("resize", () => shop.resize()); // also auto-resizes via ResizeObserver
// on unmount:
shop.dispose();
```

- Container: any sized element (`position: relative` recommended); the scene appends a canvas
  and a CSS2D label layer and fills the container.
- `quality: "low"` disables post-processing (SSAO/bloom/SMAA) and lowers shadow resolution.
- Events are queued internally so bursts don't stomp each other.

## Dev page

`npm --prefix ui/web run dev` → http://localhost:5173/scene3d.html replays `ui/fixtures/sample_week.jsonl`.
Query params: `?quality=low`, `?speed=2`.

## Event reactions

| type | reaction |
|---|---|
| repair_order.created | car drives in through the roll-up door onto bay `data.bay` (or next free), lift rises, RO label |
| vendors.compared | 3 holographic vendor cards above the counter |
| part.rejected | matching card (by vendor/price) dissolves with reason |
| part.chosen | chosen card glows green |
| order.placed counter | delivery van departs and returns |
| order.placed shopify | parcel drops onto the shelf |
| stock.low | shelf bin pulses amber |
| order.delivered | bin fills, part flies to the car on the lift |
| escalation / identity.verified / approval.* | office light pulses, badge hologram |
| statement.parsed | document scan in the office |
| scorecard.built / rule.approved / rule.proposed | wall screen updates |
| chat.message | speech-bubble ping at the office |

## Assets

All geometry, materials and textures are procedural (canvas-generated). No external models or HDRIs;
environment lighting uses three's `RoomEnvironment` via PMREM. No third-party brands or car designs.
