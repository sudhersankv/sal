import * as THREE from "three";

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  return [c, c.getContext("2d")!];
}

function rng(seed: number) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

export function tex(c: HTMLCanvasElement, srgb = true, repeat?: [number, number]): THREE.CanvasTexture {
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat[0], repeat[1]); }
  return t;
}

/** Polished sealed concrete: color + roughness maps. */
export function concrete(): { map: THREE.CanvasTexture; rough: THREE.CanvasTexture } {
  const S = 1024;
  const [c, g] = canvas(S, S);
  const [r, rg] = canvas(S, S);
  const rand = rng(7);
  g.fillStyle = "#8d8a85"; g.fillRect(0, 0, S, S);
  rg.fillStyle = "#6a6a6a"; rg.fillRect(0, 0, S, S);
  for (let i = 0; i < 2200; i++) {
    const x = rand() * S, y = rand() * S, rad = 6 + rand() * 60;
    const l = 120 + rand() * 30;
    const grd = g.createRadialGradient(x, y, 0, x, y, rad);
    grd.addColorStop(0, `rgba(${l},${l - 3},${l - 7},${0.05 + rand() * 0.07})`);
    grd.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grd; g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
    const rr = 70 + rand() * 90;
    const grr = rg.createRadialGradient(x, y, 0, x, y, rad * 1.5);
    grr.addColorStop(0, `rgba(${rr},${rr},${rr},0.12)`); grr.addColorStop(1, "rgba(0,0,0,0)");
    rg.fillStyle = grr; rg.fillRect(x - rad * 1.5, y - rad * 1.5, rad * 3, rad * 3);
  }
  for (let i = 0; i < 40000; i++) {
    const v = 90 + rand() * 90;
    g.fillStyle = `rgba(${v},${v},${v},0.25)`;
    g.fillRect(rand() * S, rand() * S, 1.5, 1.5);
  }
  // saw-cut control joints
  g.strokeStyle = "rgba(40,38,36,0.55)"; g.lineWidth = 2;
  g.beginPath(); g.moveTo(0, 1); g.lineTo(S, 1); g.moveTo(1, 0); g.lineTo(1, S); g.stroke();
  return { map: tex(c, true, [4, 3]), rough: tex(r, false, [4, 3]) };
}

/** Painted concrete block wall. */
export function blockWall(): THREE.CanvasTexture {
  const W = 1024, H = 512;
  const [c, g] = canvas(W, H);
  const rand = rng(3);
  g.fillStyle = "#8f8d88"; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 9000; i++) {
    const v = 120 + rand() * 40;
    g.fillStyle = `rgba(${v},${v},${v - 4},0.35)`;
    g.fillRect(rand() * W, rand() * H, 2, 2);
  }
  g.strokeStyle = "rgba(120,118,112,0.6)"; g.lineWidth = 3;
  const bh = 64, bw = 128;
  for (let y = 0; y <= H; y += bh) {
    g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
    const off = (y / bh) % 2 ? bw / 2 : 0;
    for (let x = off; x <= W; x += bw) { g.beginPath(); g.moveTo(x, y); g.lineTo(x, y + bh); g.stroke(); }
  }
  return tex(c, true, [3, 2]);
}

/** Corrugated roll-up door slats (grayscale; used as map + bump). */
export function slats(): THREE.CanvasTexture {
  const [c, g] = canvas(64, 512);
  for (let y = 0; y < 512; y += 32) {
    const grd = g.createLinearGradient(0, y, 0, y + 32);
    grd.addColorStop(0, "#9a9c9e"); grd.addColorStop(0.45, "#e0e2e4"); grd.addColorStop(0.9, "#7d8083"); grd.addColorStop(1, "#55585b");
    g.fillStyle = grd; g.fillRect(0, y, 64, 32);
  }
  return tex(c, false, [1, 2]);
}

export function cardboard(label?: string): THREE.CanvasTexture {
  const [c, g] = canvas(256, 256);
  const rand = rng(11);
  g.fillStyle = "#a88560"; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 3000; i++) {
    const v = rand();
    g.fillStyle = v > 0.5 ? "rgba(90,65,40,0.12)" : "rgba(200,170,130,0.12)";
    g.fillRect(rand() * 256, rand() * 256, 3, 1);
  }
  g.fillStyle = "rgba(200,190,170,0.55)"; g.fillRect(0, 118, 256, 20); // tape
  if (label) {
    g.fillStyle = "#f4f2ec"; g.fillRect(40, 160, 176, 64);
    g.fillStyle = "#222"; g.font = "bold 22px Inter, sans-serif"; g.fillText(label.slice(0, 12), 52, 190);
    for (let i = 0; i < 28; i++) g.fillRect(52 + i * 5.5, 200, rand() > 0.5 ? 3 : 1.5, 18);
  }
  return tex(c);
}

/** Bin label card: SKU + name + qty bar. */
export function binLabel(sku: string, name: string): HTMLCanvasElement {
  const [c, g] = canvas(512, 128);
  g.fillStyle = "#d9d6cc"; g.fillRect(0, 0, 512, 128);
  g.fillStyle = "#161616";
  g.font = "600 40px 'JetBrains Mono', monospace";
  g.fillText(sku.length > 18 ? sku.slice(0, 18) : sku, 18, 52);
  g.font = "500 28px Inter, sans-serif";
  g.fillStyle = "#3a3a3a";
  g.fillText(name.length > 30 ? name.slice(0, 29) + "…" : name, 18, 96);
  // barcode
  const rand = rng(sku.length * 97 + sku.charCodeAt(0));
  g.fillStyle = "#111";
  for (let x = 430; x < 500; x += 3) if (rand() > 0.4) g.fillRect(x, 70, rand() > 0.5 ? 2 : 1, 40);
  return c;
}

/** Air filter pleats. */
export function pleats(): THREE.CanvasTexture {
  const [c, g] = canvas(256, 64);
  for (let x = 0; x < 256; x += 8) {
    const grd = g.createLinearGradient(x, 0, x + 8, 0);
    grd.addColorStop(0, "#d8cfb8"); grd.addColorStop(0.5, "#f2ecdc"); grd.addColorStop(1, "#b6ad95");
    g.fillStyle = grd; g.fillRect(x, 0, 8, 64);
  }
  return tex(c);
}

/** Generic card/panel canvas with a text renderer. */
export function makeCanvas(w: number, h: number) { return canvas(w, h); }
