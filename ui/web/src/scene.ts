// Line-art shop (SPEC §11.1): EdgesGeometry + LineSegments on primitives.
// Grayscale everywhere; the only colored, moving thing is Sal's accent.
import * as THREE from "three";
import type { SalEvent } from "./types";

const C = {
  dim: 0x2a2b30,
  base: 0x5d5e64,
  hi: 0xb3b3b5,
  text: 0xdddddd,
  accent: 0x22c550,
};

type Tween = { start: number; dur: number; fn: (k: number) => void; done?: () => void };

const ease = (k: number) => 1 - Math.pow(1 - k, 3);
const easeInOut = (k: number) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

function mat(color: number, opacity = 1) {
  return new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
}
function edges(geom: THREE.BufferGeometry, m: THREE.LineBasicMaterial) {
  return new THREE.LineSegments(new THREE.EdgesGeometry(geom, 20), m);
}
function box(w: number, h: number, d: number, m: THREE.LineBasicMaterial) {
  return edges(new THREE.BoxGeometry(w, h, d), m);
}
function poly(points: [number, number, number][], m: THREE.LineBasicMaterial, closed = false) {
  const g = new THREE.BufferGeometry().setFromPoints(points.map((p) => new THREE.Vector3(...p)));
  return closed ? new THREE.LineLoop(g, m) : new THREE.Line(g, m);
}
function circle(r: number, m: THREE.LineBasicMaterial, seg = 40) {
  const pts: [number, number, number][] = [];
  for (let i = 0; i < seg; i++) {
    const a = (i / seg) * Math.PI * 2;
    pts.push([Math.cos(a) * r, 0, Math.sin(a) * r]);
  }
  return poly(pts, m, true);
}
function setColor(o: THREE.Object3D, color: number) {
  o.traverse((c) => {
    const m = (c as THREE.LineSegments).material as THREE.LineBasicMaterial | undefined;
    if (m && "color" in m) m.color.setHex(color);
  });
}
function cloneMats(o: THREE.Object3D) {
  o.traverse((c) => {
    const l = c as THREE.LineSegments;
    if (l.material) l.material = (l.material as THREE.Material).clone();
  });
}

type Label = { el: HTMLDivElement; obj?: THREE.Object3D; pos: THREE.Vector3; until?: number };
type Car = { group: THREE.Group; bay: number; ro: string; tag: Label; done: boolean };
type Bin = { frame: THREE.LineSegments; fill: THREE.LineSegments; level: number; sku?: string; pos: THREE.Vector3 };

const BAY_X = [-10, -5.5, -1, 3.5];
const BAY_Z = -1.2;
const LANE_Z = 5.2;
const DOOR = new THREE.Vector3(14, 0, LANE_Z);
const GATE_X = 23;

export class ShopScene {
  renderer: THREE.WebGLRenderer;
  scene = new THREE.Scene();
  camera: THREE.PerspectiveCamera;
  tweens: Tween[] = [];
  labels: Label[] = [];
  cars: Car[] = [];
  bins: Bin[] = [];
  lifts: THREE.Object3D[] = [];
  van!: THREE.Group;
  vanState: "gate" | "door" | "moving" = "gate";
  doorSlats!: THREE.Group;
  officeLight!: THREE.Mesh;
  officeRing!: THREE.Line;
  salScreen!: THREE.LineSegments;
  board!: { mesh: THREE.Mesh; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; pivot: THREE.Group };
  boardState = { mode: "rules" as "rules" | "scorecard" | "proposed" | "approved", title: "", lines: [] as string[], gate: false, bars: [] as { k: string; v: number }[] };
  counterPos = new THREE.Vector3(9.5, 1.4, 1.5);
  officePos = new THREE.Vector3(10, 1.6, -6.8);
  shelfPos = new THREE.Vector3(-8, 2.2, -8);
  t = 0;
  instant = false;
  private last = performance.now();

  constructor(private canvas: HTMLCanvasElement, private labelsEl: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 1);
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.1, 500);
    this.build();
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement!);
    requestAnimationFrame(this.loop);
  }

  // ------------------------------------------------------------ build
  private build() {
    const s = this.scene;
    // floor
    const grid = new THREE.GridHelper(28, 28, C.dim, 0x141518);
    grid.scale.set(1, 1, 18 / 28);
    s.add(grid);
    s.add(poly([[-14, 0, -9], [14, 0, -9], [14, 0, 9], [-14, 0, 9]], mat(C.base), true));
    // walls (back full, sides as hairlines)
    s.add(poly([[-14, 0, -9], [-14, 7, -9], [14, 7, -9], [14, 0, -9]], mat(C.base)));
    s.add(poly([[-14, 7, -9], [-14, 7, 9], [-14, 0, 9]], mat(C.dim)));
    s.add(poly([[14, 7, -9], [14, 7, 2.6], [14, 0, 2.6]], mat(C.dim)));
    s.add(poly([[14, 0, 7.8], [14, 7, 7.8], [14, 7, 9], [14, 0, 9]], mat(C.dim)));

    // lifts
    BAY_X.forEach((x, i) => {
      const g = new THREE.Group();
      g.position.set(x, 0, BAY_Z);
      const m = mat(C.base);
      const p1 = box(0.35, 4.2, 0.35, m); p1.position.set(-1.45, 2.1, 0);
      const p2 = box(0.35, 4.2, 0.35, m); p2.position.set(1.45, 2.1, 0);
      const arms = new THREE.Group();
      const a1 = box(2.6, 0.1, 0.25, m); a1.position.set(0, 0, -1.2);
      const a2 = box(2.6, 0.1, 0.25, m); a2.position.set(0, 0, 1.2);
      arms.add(a1, a2);
      arms.position.y = 0.25;
      arms.name = "arms";
      g.add(p1, p2, arms);
      // bay outline on floor
      g.add(poly([[-2, 0.01, -2.8], [2, 0.01, -2.8], [2, 0.01, 2.8], [-2, 0.01, 2.8]], mat(C.dim), true));
      s.add(g);
      this.lifts.push(g);
      this.addLabel(new THREE.Vector3(x, 0, BAY_Z + 3.3), `BAY ${i + 1}`, "dim");
    });

    // shelf with bins (back-left)
    const shelf = new THREE.Group();
    shelf.position.set(-8, 0, -8.1);
    shelf.add(box(8, 4.6, 1.1, mat(C.base)).translateY(2.3));
    for (const y of [1.5, 3.0]) shelf.add(poly([[-4, y, 0.55], [4, y, 0.55]], mat(C.base)));
    for (let r = 0; r < 3; r++) {
      for (let c = 0; c < 6; c++) {
        const bx = -3.3 + c * 1.32, by = 0.5 + r * 1.5;
        const frame = box(1.1, 0.8, 0.8, mat(C.hi));
        frame.position.set(bx, by, 0);
        const fill = box(0.9, 0.6, 0.6, mat(C.dim));
        fill.position.set(bx, by - 0.3 + 0.3, 0);
        const level = 0.55 + ((r * 7 + c * 3) % 5) * 0.1;
        fill.scale.y = level;
        fill.position.y = by - 0.3 + 0.3 * level;
        shelf.add(frame, fill);
        this.bins.push({ frame, fill, level, pos: new THREE.Vector3(-8 + bx, by, -8.1) });
      }
    }
    s.add(shelf);
    this.addLabel(new THREE.Vector3(-8, 4.9, -8.1), "SHELF", "dim");

    // counter + Sal's terminal
    const counter = new THREE.Group();
    counter.position.set(9.5, 0, 1.5);
    counter.add(box(4.2, 1.1, 1.3, mat(C.base)).translateY(0.55));
    this.salScreen = box(0.9, 0.6, 0.06, mat(C.accent));
    this.salScreen.position.set(0.6, 1.45, 0);
    counter.add(this.salScreen);
    counter.add(box(0.15, 0.3, 0.15, mat(C.accent)).translateY(1.25).translateX(0.6));
    s.add(counter);
    this.addLabel(new THREE.Vector3(9.5, 0, 2.9), "COUNTER · SAL", "dim");

    // office (back-right)
    const office = new THREE.Group();
    office.position.set(10, 0, -6.8);
    office.add(box(6, 3.2, 4, mat(C.base)).translateY(1.6));
    office.add(poly([[-2.2, 1.2, 2.01], [-0.4, 1.2, 2.01], [-0.4, 2.6, 2.01], [-2.2, 2.6, 2.01]], mat(C.dim), true));
    office.add(poly([[0.6, 0, 2.01], [0.6, 2.4, 2.01], [1.8, 2.4, 2.01], [1.8, 0, 2.01]], mat(C.dim)));
    office.add(box(1.8, 0.8, 0.9, mat(C.dim)).translateY(0.4).translateX(-1.2));
    this.officeLight = new THREE.Mesh(new THREE.SphereGeometry(0.18, 12, 8), new THREE.MeshBasicMaterial({ color: 0x3a3b40 }));
    this.officeLight.position.set(0, 3.0, 0);
    office.add(this.officeLight);
    this.officeRing = circle(0.5, mat(C.accent, 0));
    this.officeRing.position.set(0, 3.0, 0);
    office.add(this.officeRing);
    s.add(office);
    this.addLabel(new THREE.Vector3(10, 3.6, -4.8), "OWNER", "dim");

    // scoreboard on back wall
    const canvas = document.createElement("canvas");
    canvas.width = 1024; canvas.height = 440;
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    const pivot = new THREE.Group();
    pivot.position.set(1.5, 4.6, -8.95);
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(9.2, 3.95), new THREE.MeshBasicMaterial({ map: tex, transparent: true }));
    pivot.add(mesh);
    pivot.add(box(9.4, 4.13, 0.08, mat(C.base)));
    s.add(pivot);
    this.board = { mesh, canvas, tex, pivot };
    this.boardState = { mode: "rules", title: "SHOP RULES · SENSO", lines: ["R1 · over $200 → owner", "R4 · no ValuMax sensors", "R5 · urgent = local counter"], gate: false, bars: [] };
    this.drawBoard();
    document.fonts?.ready.then(() => this.drawBoard());

    // roll-up door (right wall)
    const door = new THREE.Group();
    door.position.set(14, 0, (2.6 + 7.8) / 2);
    door.add(poly([[0, 0, -2.6], [0, 4.2, -2.6], [0, 4.2, 2.6], [0, 0, 2.6]], mat(C.hi)));
    this.doorSlats = new THREE.Group();
    for (let i = 0; i < 9; i++) this.doorSlats.add(poly([[0, 0.2 + i * 0.45, -2.5], [0, 0.2 + i * 0.45, 2.5]], mat(C.base)));
    door.add(this.doorSlats);
    s.add(door);

    // road + vendor gate
    for (const z of [LANE_Z - 1.6, LANE_Z + 1.6]) s.add(poly([[14, 0, z], [GATE_X + 4, 0, z]], mat(C.dim)));
    for (let x = 15; x < GATE_X + 3; x += 2) s.add(poly([[x, 0, LANE_Z], [x + 0.9, 0, LANE_Z]], mat(C.dim)));
    const gate = new THREE.Group();
    gate.position.set(GATE_X, 0, LANE_Z);
    gate.add(box(0.3, 3.4, 0.3, mat(C.base)).translateY(1.7).translateZ(-2));
    gate.add(box(0.3, 3.4, 0.3, mat(C.base)).translateY(1.7).translateZ(2));
    gate.add(box(0.2, 0.5, 4.3, mat(C.base)).translateY(3.4));
    s.add(gate);
    this.addLabel(new THREE.Vector3(GATE_X, 4, LANE_Z), "VENDORS", "dim");

    // van
    this.van = this.makeVan();
    this.van.position.set(GATE_X - 2, 0, LANE_Z);
    s.add(this.van);
  }

  private makeVan() {
    const g = new THREE.Group();
    const m = mat(C.hi);
    g.add(box(3.6, 1.8, 1.8, m).translateY(1.25).translateX(0.4));
    g.add(box(1.2, 1.2, 1.8, m).translateY(0.95).translateX(-2.0));
    for (const x of [-1.6, 1.4]) for (const z of [-0.85, 0.85]) {
      const w = edges(new THREE.CylinderGeometry(0.36, 0.36, 0.25, 14), mat(C.base));
      w.rotation.x = Math.PI / 2; w.position.set(x, 0.36, z); g.add(w);
    }
    return g;
  }

  private makeCar() {
    const g = new THREE.Group();
    const m = mat(C.text);
    const body = box(1.8, 0.8, 4.2, m); body.position.y = 0.7;
    const cab = box(1.6, 0.65, 2.1, m); cab.position.set(0, 1.42, -0.2);
    g.add(body, cab);
    for (const z of [-1.35, 1.35]) for (const x of [-0.9, 0.9]) {
      const w = edges(new THREE.CylinderGeometry(0.36, 0.36, 0.26, 14), mat(C.base));
      w.rotation.z = Math.PI / 2; w.position.set(x, 0.36, z); g.add(w);
    }
    return g;
  }

  // ------------------------------------------------------------ infra
  resize() {
    const p = this.canvas.parentElement!;
    const w = p.clientWidth, h = p.clientHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(h, 1);
    // keep the whole floor + road in frame on narrow stages
    this.camera.fov = this.camera.aspect < 1.5 ? 36 : 30;
    this.camera.updateProjectionMatrix();
  }

  tween(dur: number, fn: (k: number) => void, done?: () => void, delay = 0) {
    if (this.instant) { fn(1); done?.(); return; }
    this.tweens.push({ start: performance.now() + delay, dur, fn, done });
  }

  finishAll() {
    const ts = this.tweens; this.tweens = [];
    for (const t of ts) { t.fn(1); t.done?.(); }
    // follow-ups queued by done() run instantly too
    if (this.tweens.length) this.finishAll();
  }

  addLabel(pos: THREE.Vector3, text: string, cls = "", obj?: THREE.Object3D, ttl?: number) {
    const el = document.createElement("div");
    el.className = `tag3d ${cls}`;
    el.textContent = text;
    if (cls === "dim") { el.style.color = "#89898d"; el.style.borderColor = "transparent"; el.style.background = "transparent"; }
    this.labelsEl.appendChild(el);
    const l: Label = { el, obj, pos: pos.clone(), until: ttl && !this.instant ? performance.now() + ttl : undefined };
    if (ttl && this.instant) { el.remove(); return l; }
    this.labels.push(l);
    return l;
  }
  removeLabel(l: Label) {
    l.el.remove();
    this.labels = this.labels.filter((x) => x !== l);
  }

  project(v: THREE.Vector3) {
    const p = v.clone().project(this.camera);
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    return { x: (p.x * 0.5 + 0.5) * w, y: (-p.y * 0.5 + 0.5) * h, visible: p.z < 1 };
  }

  private loop = (now: number) => {
    requestAnimationFrame(this.loop);
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    this.t += dt;
    // slow orbit
    const a = 0.1 + Math.sin(this.t * 0.06) * 0.1;
    const target = new THREE.Vector3(4.5, 0, 1.5);
    const r = 42;
    this.camera.position.set(target.x + Math.sin(a) * r, 27, target.z + Math.cos(a) * r);
    this.camera.lookAt(target);
    // tweens
    const live: Tween[] = [];
    const ts = this.tweens; this.tweens = [];
    for (const tw of ts) {
      if (now < tw.start) { live.push(tw); continue; }
      const k = Math.min(1, (now - tw.start) / tw.dur);
      tw.fn(k);
      if (k >= 1) tw.done?.(); else live.push(tw);
    }
    this.tweens.push(...live);
    // sal screen breathes
    (this.salScreen.material as THREE.LineBasicMaterial).opacity = 0.65 + 0.35 * Math.sin(this.t * 2.2);
    (this.salScreen.material as THREE.LineBasicMaterial).transparent = true;
    this.renderer.render(this.scene, this.camera);
    // labels
    const tmp = new THREE.Vector3();
    for (const l of [...this.labels]) {
      if (l.until && now > l.until) { this.removeLabel(l); continue; }
      if (l.obj) l.obj.getWorldPosition(tmp).add(l.pos); else tmp.copy(l.pos);
      const p = this.project(tmp);
      l.el.style.left = `${p.x}px`;
      l.el.style.top = `${p.y}px`;
      l.el.style.opacity = p.visible ? "" : "0";
    }
  };

  // ------------------------------------------------------------ effects
  pulse(pos: THREE.Vector3, color = C.accent, r = 2.2, dur = 1200) {
    if (this.instant) return;
    const ring = circle(1, mat(color, 1));
    ring.position.copy(pos);
    this.scene.add(ring);
    this.tween(dur, (k) => {
      const e = ease(k);
      ring.scale.setScalar(0.2 + e * r);
      (ring.material as THREE.LineBasicMaterial).opacity = 1 - k;
    }, () => { this.scene.remove(ring); ring.geometry.dispose(); });
  }

  flyBox(from: THREE.Vector3, to: THREE.Vector3, dur = 1400, size = 0.45, arc = 3, after?: () => void) {
    if (this.instant) { after?.(); return; }
    const b = box(size, size, size, mat(C.accent));
    this.scene.add(b);
    this.tween(dur, (k) => {
      const e = easeInOut(k);
      b.position.lerpVectors(from, to, e);
      b.position.y += Math.sin(Math.PI * e) * arc;
      b.rotation.y = e * Math.PI * 2;
    }, () => { this.scene.remove(b); after?.(); });
  }

  scanLine(center: THREE.Vector3, w: number, h: number, dur = 1400) {
    if (this.instant) return;
    const l = poly([[-w / 2, 0, 0], [w / 2, 0, 0]], mat(C.accent));
    l.position.copy(center);
    this.scene.add(l);
    this.tween(dur, (k) => {
      l.position.y = center.y - h / 2 + h * k;
      (l.material as THREE.LineBasicMaterial).opacity = 1 - Math.abs(k - 0.5) * 0.8;
      (l.material as THREE.LineBasicMaterial).transparent = true;
    }, () => this.scene.remove(l));
  }

  openDoor(hold = 1600) {
    this.tween(600, (k) => { this.doorSlats.position.y = ease(k) * 3.6; this.doorSlats.scale.y = 1 - ease(k) * 0.85; }, () => {
      this.tween(600, (k) => { this.doorSlats.position.y = 3.6 * (1 - ease(k)); this.doorSlats.scale.y = 0.15 + ease(k) * 0.85; }, undefined, hold);
    });
  }

  toast?: (text: string, sal: boolean) => void;

  // ------------------------------------------------------------ boards
  drawBoard() {
    const { canvas } = this.board, s = this.boardState;
    const g = canvas.getContext("2d")!;
    g.clearRect(0, 0, canvas.width, canvas.height);
    g.fillStyle = "#050607"; g.fillRect(0, 0, canvas.width, canvas.height);
    g.fillStyle = "#89898d"; g.font = "500 32px 'JetBrains Mono', monospace";
    g.fillText(s.title, 40, 62);
    if (s.gate) {
      g.fillStyle = "#22c550"; g.textAlign = "right";
      g.fillText("● sal_vendor_routing_v2 ON", canvas.width - 40, 58);
      g.textAlign = "left";
    }
    g.strokeStyle = "#2c2d31"; g.lineWidth = 2; g.beginPath(); g.moveTo(40, 80); g.lineTo(canvas.width - 40, 80); g.stroke();
    if (s.mode === "scorecard") {
      s.bars.forEach((b, i) => {
        const y = 140 + i * 90;
        g.fillStyle = "#dddddd"; g.font = "400 46px 'Inter Tight', sans-serif"; g.fillText(b.k, 40, y);
        g.strokeStyle = "#5d5e64"; g.strokeRect(330, y - 34, 540, 38);
        g.fillStyle = b.v > 0.2 ? "#dddddd" : "#5d5e64"; g.fillRect(330, y - 34, 540 * Math.min(1, b.v / 0.5), 38);
        g.fillStyle = "#dddddd"; g.font = "500 30px 'JetBrains Mono', monospace"; g.fillText(`${(b.v * 100).toFixed(1)}%`, 900, y);
      });
      return this.board.tex.needsUpdate = true, undefined;
    }
    const big = s.mode === "approved" || s.mode === "proposed";
    g.fillStyle = s.mode === "approved" ? "#22c550" : "#dddddd";
    g.font = big ? "400 76px 'Inter Tight', sans-serif" : "400 58px 'Inter Tight', sans-serif";
    s.lines.forEach((ln, i) => g.fillText(ln, 40, (big ? 180 : 160) + i * (big ? 92 : 80)));
    if (s.mode === "proposed") {
      g.setLineDash([12, 10]); g.strokeStyle = "#89898d"; g.strokeRect(24, 100, canvas.width - 48, canvas.height - 124); g.setLineDash([]);
    }
    this.board.tex.needsUpdate = true;
  }

  flipBoard(update: () => void) {
    if (this.instant) { update(); this.drawBoard(); return; }
    const p = this.board.pivot;
    this.tween(350, (k) => { p.rotation.x = (Math.PI / 2) * ease(k); }, () => {
      update(); this.drawBoard();
      this.tween(450, (k) => { p.rotation.x = (Math.PI / 2) * (1 - ease(k)); });
    });
  }

  // ------------------------------------------------------------ helpers
  private binFor(sku?: string) {
    if (sku) {
      const found = this.bins.find((b) => b.sku === sku);
      if (found) return found;
      const free = this.bins.find((b) => !b.sku);
      if (free) { free.sku = sku; return free; }
    }
    return this.bins[7];
  }
  private setBin(b: Bin, level: number, accent: boolean) {
    const from = b.level;
    b.level = level;
    const by = b.frame.position.y;
    this.tween(900, (k) => {
      const v = from + (level - from) * ease(k);
      b.fill.scale.y = Math.max(0.02, v);
      b.fill.position.y = by - 0.3 + 0.3 * Math.max(0.02, v);
    });
    if (accent) {
      setColor(b.frame, C.accent);
      if (!this.instant) this.tween(2600, (k) => {
        (b.frame.material as THREE.LineBasicMaterial).opacity = 0.4 + 0.6 * Math.abs(Math.cos(k * Math.PI * 4));
        (b.frame.material as THREE.LineBasicMaterial).transparent = true;
      }, () => { (b.frame.material as THREE.LineBasicMaterial).opacity = 1; });
    } else setColor(b.frame, C.hi);
  }
  private carFor(ro?: string) {
    return this.cars.find((c) => c.ro === ro) ?? this.cars[this.cars.length - 1];
  }

  driveVan(to: number, dur: number, after?: () => void) {
    const from = this.van.position.x;
    this.vanState = "moving";
    this.tween(dur, (k) => { this.van.position.x = from + (to - from) * easeInOut(k); }, after);
  }

  // ------------------------------------------------------------ events
  onDay(_day: string) {
    // finished cars drive out at a day change
    for (const car of this.cars.filter((c) => c.done)) this.carLeaves(car);
  }

  private carLeaves(car: Car) {
    this.cars = this.cars.filter((c) => c !== car);
    this.removeLabel(car.tag);
    const g = car.group, lift = this.lifts[car.bay];
    const arms = lift.getObjectByName("arms")!;
    this.tween(700, (k) => { const y = 1.6 * (1 - ease(k)); g.position.y = y; arms.position.y = 0.25 + y; }, () => {
      this.openDoor(1800);
      this.tween(1000, (k) => { g.position.z = BAY_Z + (LANE_Z - BAY_Z) * easeInOut(k); g.rotation.y = (Math.PI / 2) * ease(k); }, () => {
        const sx = g.position.x;
        this.tween(1400, (k) => { g.position.x = sx + (DOOR.x + 6 - sx) * easeInOut(k); }, () => this.scene.remove(g));
      });
    });
  }

  handle(ev: SalEvent, instant = false) {
    this.instant = instant;
    try { this.apply(ev); } finally { this.instant = false; }
  }

  private apply(ev: SalEvent) {
    const refs = ev.refs ?? {}, data = ev.data ?? {};
    const sal = ev.actor === "sal";
    switch (ev.type) {
      case "repair_order.created": {
        const used = new Set(this.cars.map((c) => c.bay));
        let bay = typeof data.bay === "number" ? (data.bay as number) - 1 : -1;
        if (bay < 0 || bay > 3 || used.has(bay)) bay = [0, 1, 2, 3].find((b) => !used.has(b)) ?? 0;
        const old = this.cars.find((c) => c.bay === bay);
        if (old) { this.scene.remove(old.group); this.removeLabel(old.tag); this.cars = this.cars.filter((c) => c !== old); }
        const g = this.makeCar();
        cloneMats(g);
        this.scene.add(g);
        const bx = BAY_X[bay];
        const tag = this.addLabel(new THREE.Vector3(0, 3.0, 0), `${refs.ro_id ?? "RO"} · ${String(data.vehicle ?? "").replace(/^\d{4} /, "") || "car"}`, "", g);
        const car: Car = { group: g, bay, ro: String(refs.ro_id ?? ev.id), tag, done: false };
        this.cars.push(car);
        const arms = this.lifts[bay].getObjectByName("arms")!;
        g.position.set(DOOR.x + 5, 0, LANE_Z); g.rotation.y = Math.PI / 2;
        this.openDoor(2400);
        this.tween(1500, (k) => { g.position.x = DOOR.x + 5 + (bx - DOOR.x - 5) * easeInOut(k); }, () => {
          this.tween(1100, (k) => { g.position.z = LANE_Z + (BAY_Z - LANE_Z) * easeInOut(k); g.rotation.y = (Math.PI / 2) * (1 - ease(k)); }, () => {
            this.tween(900, (k) => { const y = 1.6 * ease(k); g.position.y = y; arms.position.y = 0.25 + y; });
          });
        }, 300);
        break;
      }
      case "part.identified": {
        const car = this.carFor(refs.ro_id as string);
        if (car) {
          const p = car.group.position.clone();
          this.tween(1, () => {}, () => { this.pulse(car.group.position.clone().setY(car.group.position.y + 0.8), C.accent, 2.6); this.scanLine(car.group.position.clone().setY(1.6 + 0.9), 2.2, 1.8); }, 0);
          void p;
          setColor(car.group, C.accent);
          this.tween(1600, () => {}, () => setColor(car.group, C.text));
        }
        break;
      }
      case "context.retrieved": {
        const kind = String(data.kind ?? "");
        const src = (ev.sources ?? [])[0]?.name;
        // context streams into Sal's counter terminal
        const from = kind === "memory" || src === "Cognee" ? this.officePos.clone().setY(3) : kind === "rules" ? this.board.pivot.position.clone() : new THREE.Vector3(GATE_X, 3, LANE_Z);
        this.flyBox(from, this.counterPos, 1100, 0.25, 1.5, () => this.pulse(this.counterPos, C.accent, 1.6, 900));
        break;
      }
      case "vendors.compared":
        this.pulse(this.counterPos, C.accent, 3, 1400);
        break;
      case "part.chosen":
      case "quote.sent":
      case "approval.requested":
      case "payment.recorded":
      case "sal.summary":
        this.pulse(this.counterPos, sal ? C.accent : C.hi, 2.2);
        break;
      case "approval.received":
        this.pulse(this.counterPos, C.hi, 2.2);
        if (ev.actor === "owner") this.officeCalm();
        break;
      case "order.placed": {
        if (data.channel === "shopify" || (ev.sources ?? []).some((s) => s.name === "Shopify" && /Order/.test(s.ref ?? ""))) {
          // parcel drops onto the shelf
          const lines = (data.lines as { sku: string }[] | undefined) ?? [];
          const target = (lines[0] && this.bins.find((b) => b.sku === lines[0].sku)) || this.bins.find((b) => b.sku) || this.bins[13];
          const top = new THREE.Vector3(target.pos.x, 5.4, target.pos.z + 0.6);
          const parcel = box(1.0, 0.6, 0.7, mat(C.accent));
          parcel.position.set(top.x, 14, top.z);
          this.scene.add(parcel);
          this.tween(1300, (k) => { parcel.position.y = 14 - (14 - top.y) * (k < 1 ? k * k : 1); }, () => {
            this.pulse(top, C.accent, 1.8);
            // restock: every tracked bin fills
            for (const b of this.bins.filter((x) => x.sku)) this.setBin(b, 0.95, false);
            this.tween(2200, () => {}, () => setColor(parcel, C.hi), 1200);
          });
          this.addLabel(top.clone().setY(6.4), "SHOPIFY PARCEL", "sal", undefined, 4500);
        } else {
          // van departs vendor gate, arrives at the shop door
          const go = () => this.driveVan(DOOR.x + 2.6, 2600, () => { this.vanState = "door"; this.openDoor(1200); });
          if (this.vanState !== "gate") { this.van.position.x = GATE_X - 2; }
          this.addLabel(new THREE.Vector3(0, 3, 0), String(refs.order_id ?? "order"), "", this.van, 5000);
          go();
        }
        break;
      }
      case "order.delivered": {
        const car = this.carFor(refs.ro_id as string);
        const start = this.van.position.clone().setY(1.6);
        if (car) {
          const to = car.group.position.clone().setY(car.group.position.y + 1.2);
          this.openDoor(1500);
          this.flyBox(start, to, 1700, 0.45, 3.5, () => { this.pulse(to, C.accent, 2); car.done = true; car.tag.el.classList.add("sal"); car.tag.el.textContent += " · part in"; });
        }
        const bin = this.binFor(refs.sku as string);
        this.setBin(bin, Math.min(1, bin.level + 0.2), false);
        this.tween(1, () => {}, () => this.driveVan(GATE_X - 2, 2400, () => (this.vanState = "gate")), 1800);
        break;
      }
      case "inventory.checked":
        this.scanLine(this.shelfPos.clone().setZ(-7.4), 8.2, 4.6, 1800);
        break;
      case "stock.low": {
        const b = this.binFor(refs.sku as string);
        const have = Number(data.have ?? 0), need = Number(data.need ?? 1);
        this.setBin(b, Math.max(0.03, Math.min(0.4, have / Math.max(need, 1) * 0.5)), true);
        break;
      }
      case "restock.planned":
        for (const b of this.bins.filter((x) => x.sku)) this.pulse(b.pos.clone().setZ(-7.2), C.accent, 0.8, 900);
        break;
      case "escalation":
        this.officeAlert();
        this.addLabel(new THREE.Vector3(10, 4.5, -6.8), "NEEDS OWNER", "owner", undefined, 6000);
        break;
      case "identity.verified":
        this.badgeCheck();
        break;
      case "statement.parsed":
        this.docScan();
        break;
      case "scorecard.built": {
        const per = (data.per_vendor as { vendor_id: string; late_rate: number }[] | undefined) ?? [];
        this.flipBoard(() => {
          this.boardState.mode = "scorecard";
          this.boardState.title = "VENDOR SCORECARD · 90 DAYS";
          this.boardState.bars = per.map((p) => ({ k: p.vendor_id[0].toUpperCase() + p.vendor_id.slice(1), v: p.late_rate }));
        });
        break;
      }
      case "rule.proposed":
        this.flipBoard(() => {
          this.boardState.mode = "proposed";
          this.boardState.title = `PROPOSED ${refs.rule_id ?? ""} · AWAITING OWNER`;
          this.boardState.lines = wrap(String(data.title ?? ev.summary.replace(/^Proposed:\s*/, "")), 22);
        });
        this.officeAlert();
        break;
      case "rule.approved":
        this.officeCalm();
        this.flipBoard(() => {
          this.boardState.mode = "approved";
          this.boardState.title = `NEW RULE ${refs.rule_id ?? ""} · APPROVED`;
          this.boardState.lines = wrap(String(data.title ?? ev.summary.replace(/^Owner approved [^:]*:\s*/, "")), 22);
        });
        break;
      case "gate.enabled":
        this.boardState.gate = (data.value as boolean | undefined) !== false;
        this.drawBoard();
        this.pulse(this.board.pivot.position.clone().setZ(-8.6), C.accent, 3);
        break;
      case "memory.saved":
        this.flyBox(this.counterPos, this.officePos.clone().setY(3), 1100, 0.22, 1.5);
        break;
      case "metrics.updated":
        this.pulse(this.board.pivot.position.clone().setY(2.6).setZ(-8.6), C.hi, 2.5);
        break;
      case "error":
        this.pulse(this.counterPos, C.hi, 3);
        break;
    }
  }

  officeAlert() {
    const m = this.officeLight.material as THREE.MeshBasicMaterial;
    m.color.setHex(C.accent);
    const ring = this.officeRing.material as THREE.LineBasicMaterial;
    if (this.instant) return;
    this.tween(5200, (k) => {
      const s = Math.abs(Math.sin(k * Math.PI * 6));
      ring.opacity = s * (1 - k * 0.3);
      this.officeRing.scale.setScalar(1 + s * 1.8);
    }, () => { ring.opacity = 0; });
  }
  officeCalm() {
    (this.officeLight.material as THREE.MeshBasicMaterial).color.setHex(0x3a3b40);
  }

  badgeCheck() {
    const g = new THREE.Group();
    g.position.set(10, 4.9, -4.7);
    g.add(poly([[-0.7, -0.9, 0], [0.7, -0.9, 0], [0.7, 0.9, 0], [-0.7, 0.9, 0]], mat(C.accent), true));
    g.add(circle(0.28, mat(C.accent), 24).rotateX(Math.PI / 2).translateY(0).translateZ(-0.35));
    g.add(poly([[-0.4, -0.45, 0], [0.4, -0.45, 0]], mat(C.accent)));
    const check = poly([[-0.35, -0.05, 0.02], [-0.08, -0.32, 0.02], [0.45, 0.35, 0.02]], mat(C.accent));
    check.position.set(0.9, 0.7, 0);
    g.add(check);
    this.scene.add(g);
    this.officeCalm();
    if (this.instant) { setColor(g, C.base); this.scene.remove(g); return; }
    g.scale.setScalar(0.01);
    this.tween(600, (k) => g.scale.setScalar(0.01 + ease(k)), () => {
      this.pulse(g.position, C.accent, 2.4);
      this.tween(800, (k) => { g.position.y = 4.9 - 1.5 * ease(k); g.scale.setScalar(1 - ease(k) * 0.99); }, () => this.scene.remove(g), 2600);
    });
    this.addLabel(new THREE.Vector3(10, 6.2, -4.7), "IDENTITY VERIFIED · PERSONA", "sal", undefined, 3600);
  }

  docScan() {
    const page = new THREE.Group();
    page.add(poly([[-0.6, -0.8, 0], [0.6, -0.8, 0], [0.6, 0.8, 0], [-0.6, 0.8, 0]], mat(C.accent), true));
    for (let i = 0; i < 6; i++) page.add(poly([[-0.42, 0.55 - i * 0.22, 0], [i % 2 ? 0.2 : 0.42, 0.55 - i * 0.22, 0]], mat(C.hi)));
    if (this.instant) return;
    const from = new THREE.Vector3(GATE_X - 4, 2.5, LANE_Z), mid = new THREE.Vector3(DOOR.x - 1, 3.5, LANE_Z), to = new THREE.Vector3(10, 2.2, -4.6);
    page.position.copy(from);
    page.scale.setScalar(1.4);
    this.scene.add(page);
    this.openDoor(1400);
    this.tween(1200, (k) => page.position.lerpVectors(from, mid, easeInOut(k)), () => {
      this.tween(1300, (k) => { page.position.lerpVectors(mid, to, easeInOut(k)); page.rotation.y = -0.4 * k; }, () => {
        this.scanLine(to.clone().add(new THREE.Vector3(0, 0, 0.05)), 1.9, 2.3, 1500);
        this.addLabel(to.clone().setY(4.0), "STATEMENT · SIE EXTRACT", "sal", undefined, 3200);
        this.tween(700, (k) => page.scale.setScalar(1.4 * (1 - k) + 0.01), () => this.scene.remove(page), 1700);
      });
    });
  }
}

function wrap(s: string, n: number) {
  const words = s.split(/\s+/), out: string[] = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > n) { out.push(cur.trim()); cur = w; } else cur += " " + w;
  }
  if (cur.trim()) out.push(cur.trim());
  return out.slice(0, 3);
}
