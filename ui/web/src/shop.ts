// 3D parts room behind the scene3d API (AGENT_UX.md):
//   createShopScene(container, {quality}) -> { handleEvent, setInventory, onSelect, setFocus, resize, dispose }
// This adapter wraps the line-art ShopScene (lifts/bays hidden: parts only) until the realistic
// `./scene3d` lands; the swap is the one import in app.ts.
import * as THREE from "three";
import { ShopScene } from "./scene";
import type { SalEvent } from "./types";

export type ShopFocus = "overview" | `shelf:${string}` | "counter" | "receiving";
export type InventoryItem = { sku: string; name: string; part_type: string; qty: number; min_qty: number | null; max_qty: number | null; status: string };
export type ShopHandle = {
  handleEvent(ev: SalEvent): void;
  setInventory(items: InventoryItem[]): void;
  onSelect(cb: (sku: string) => void): void;
  setFocus(f: ShopFocus): void;
  resize(): void;
  dispose(): void;
};

type BinLike = { frame: THREE.LineSegments; fill: THREE.LineSegments; level: number; sku?: string; pos: THREE.Vector3 };

export function createShopScene(container: HTMLElement, _opts: { quality?: "low" | "high" } = {}): ShopHandle {
  const canvas = document.createElement("canvas");
  const labels = document.createElement("div");
  labels.className = "labels";
  container.append(canvas, labels);
  const scene = new ShopScene(canvas, labels);
  // parts room: no lifts, bays or cars
  for (const l of scene.lifts) l.visible = false;
  for (const l of [...scene.labels]) if (/^BAY/.test(l.el.textContent ?? "")) scene.removeLabel(l);
  const bins = (scene as unknown as { bins: BinLike[] }).bins;
  let select: ((sku: string) => void) | null = null;

  const ray = new THREE.Raycaster();
  ray.params.Line = { threshold: 0.15 };
  canvas.addEventListener("click", (e) => {
    if (!select) return;
    const r = canvas.getBoundingClientRect();
    const p = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(p, scene.camera);
    const hit = ray.intersectObjects(bins.map((b) => b.frame), false)[0];
    const bin = hit && bins.find((b) => b.frame === hit.object);
    if (bin?.sku) select(bin.sku);
  });

  return {
    handleEvent: (ev) => {
      if (ev.type === "repair_order.created" || ev.type === "part.identified") return; // no cars in the parts room
      scene.handle(ev);
    },
    setInventory: (items) => {
      items.slice(0, bins.length).forEach((it, i) => {
        const b = bins[i];
        b.sku = it.sku;
        const max = it.max_qty || Math.max(it.qty, 1) * 2;
        const lvl = Math.max(0.03, Math.min(1, it.qty / max));
        b.level = lvl;
        const by = b.frame.position.y;
        b.fill.scale.y = lvl;
        b.fill.position.y = by - 0.3 + 0.3 * lvl;
        (b.frame.material as THREE.LineBasicMaterial).color.setHex(it.status === "ok" ? 0xb3b3b5 : 0x22c550);
      });
    },
    onSelect: (cb) => { select = cb; },
    setFocus: () => {},
    resize: () => scene.resize(),
    dispose: () => {
      scene.renderer.dispose();
      canvas.remove();
      labels.remove();
    },
  };
}
