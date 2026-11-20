// Standalone dev page: mounts the parts room full-screen and replays the fixture week.
import "@fontsource/inter/500.css";
import "@fontsource/inter/700.css";
import "@fontsource/jetbrains-mono/500.css";
import fixture from "../../../fixtures/sample_week.jsonl?raw";
import { createShopScene } from "./index";
import type { SalEvent } from "./types";

const q = new URLSearchParams(location.search);
const hud = document.getElementById("hud")!;
const room = createShopScene(document.getElementById("room")!, {
  quality: q.get("quality") === "low" ? "low" : "high",
  onSelect: (sku) => { if (sku) hud.textContent = `selected ${sku}`; },
});
const events: SalEvent[] = fixture.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l) as SalEvent);
const speed = Number(q.get("speed") ?? "1") || 1;
const start = Number(q.get("from") ?? "0");
let i = start;
(window as unknown as { room: typeof room }).room = room;
if (q.get("replay") !== "0") {
  const step = () => {
    if (i >= events.length) i = 0;
    const ev = events[i++];
    hud.textContent = `${ev.day ?? ""} ${ev.type} · ${ev.summary ?? ""}`;
    room.handleEvent(ev);
    setTimeout(step, 2600 / speed);
  };
  setTimeout(step, 1500);
} else hud.textContent = "idle";
