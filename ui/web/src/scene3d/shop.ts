import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { RectAreaLightUniformsLib } from "three/examples/jsm/lights/RectAreaLightUniformsLib.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { GTAOPass } from "three/examples/jsm/postprocessing/GTAOPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";
import { SMAAPass } from "three/examples/jsm/postprocessing/SMAAPass.js";
import { CSS2DRenderer, CSS2DObject } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import type { FocusTarget, InventoryItem, SalEvent, ShopScene, ShopSceneOptions } from "./types";
import { HEAVY, PartLibrary, kindOf, type PartKind } from "./parts";
import { binLabel, blockWall, cardboard, concrete, makeCanvas, slats, tex } from "./textures";

const GREEN = new THREE.Color(0x22c550);
const AMBER = new THREE.Color(0xf0a020);
const RED = new THREE.Color(0xe5402e);

// ---------------------------------------------------------------- layout
const UNIT_X = [-5.6, -3.45, -1.3, 0.85];
const LEVEL_Y = [0.14, 0.56, 0.98, 1.4, 1.82];
const SHELF_Z = -4.5; // unit center z
const BIN_W = 0.9, BIN_D = 0.5, BIN_H = 0.2;
const COUNTER = new THREE.Vector3(4.4, 0, -0.4);
const DOOR = { x: 7, z: -2.6, w: 3.2, h: 3.2 };
const RECEIVING = new THREE.Vector3(5.9, 0, -2.6);

const DEMO: InventoryItem[] = [
  { sku: "FLT-15400-PLM-A02", name: "Oil filter Civic/CR-V", part_type: "oil filter", qty: 8, min_qty: 6, max_qty: 24 },
  { sku: "FLT-04152-YZZA1", name: "Oil filter Camry 2.5L", part_type: "oil filter", qty: 6, min_qty: 5, max_qty: 20 },
  { sku: "FLT-15208-65F0E", name: "Oil filter Altima 2.5L", part_type: "oil filter", qty: 11, min_qty: 4, max_qty: 20 },
  { sku: "WPR-26", name: "Wiper blade 26 in", part_type: "wiper blade", qty: 3, min_qty: 4, max_qty: 12 },
  { sku: "WPR-22", name: "Wiper blade 22 in", part_type: "wiper blade", qty: 7, min_qty: 4, max_qty: 12 },
  { sku: "CHM-BRAKECLN", name: "Brake cleaner 14 oz", part_type: "brake cleaner", qty: 5, min_qty: 6, max_qty: 24 },
  { sku: "PAD-CIV14-F", name: "Front pads Civic 14-15", part_type: "brake pads", qty: 3, min_qty: 2, max_qty: 8 },
  { sku: "PAD-CAM18-F", name: "Front pads Camry 18-22", part_type: "brake pads", qty: 5, min_qty: 2, max_qty: 8 },
  { sku: "ROT-CIV14-F", name: "Front rotor Civic 14", part_type: "brake rotor", qty: 4, min_qty: 2, max_qty: 6 },
  { sku: "O2-234-4364", name: "O2 sensor downstream", part_type: "oxygen sensor", qty: 0, min_qty: 1, max_qty: 4 },
  { sku: "AFR-234-9005", name: "A/F ratio sensor upstream", part_type: "air/fuel ratio sensor", qty: 2, min_qty: 1, max_qty: 4 },
  { sku: "COIL-UF-247", name: "Ignition coil", part_type: "ignition coil", qty: 6, min_qty: 4, max_qty: 12 },
  { sku: "BELT-6K-880", name: "Serpentine belt 6K880", part_type: "serpentine belt", qty: 3, min_qty: 2, max_qty: 6 },
  { sku: "FLD-COOLANT", name: "Coolant 50/50 1 gal", part_type: "coolant", qty: 4, min_qty: 3, max_qty: 8 },
  { sku: "FLD-ATF-WS", name: "ATF WS 1 gal", part_type: "transmission fluid", qty: 5, min_qty: 3, max_qty: 8 },
  { sku: "ALT-GL-8758", name: "Alternator reman F-150", part_type: "alternator", qty: 1, min_qty: 1, max_qty: 4 },
  { sku: "STR-17880", name: "Starter reman Civic", part_type: "starter", qty: 2, min_qty: 1, max_qty: 4 },
  { sku: "AIR-CA10467", name: "Engine air filter", part_type: "engine air filter", qty: 5, min_qty: 3, max_qty: 10 },
  { sku: "CAB-CF10285", name: "Cabin air filter", part_type: "cabin air filter", qty: 2, min_qty: 3, max_qty: 10 },
  { sku: "LNK-K750", name: "Stabilizer bar link", part_type: "stabilizer bar link", qty: 4, min_qty: 2, max_qty: 8 },
  { sku: "BLB-9006", name: "Headlamp bulb 9006", part_type: "bulb", qty: 8, min_qty: 4, max_qty: 20 },
];

interface Anim { t0: number; dur: number; step: (k: number) => void; done?: () => void }
const ease = (k: number) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);

interface Bin {
  item: InventoryItem;
  kind: PartKind;
  group: THREE.Group;
  hit: THREE.Mesh;
  labelMat: THREE.MeshStandardMaterial;
  labelTex: THREE.CanvasTexture;
  led: THREE.MeshBasicMaterial;
  inst: THREE.InstancedMesh[];
  ghosts: THREE.InstancedMesh[];
  slots: THREE.Matrix4[];
  cap: number;
  pulse: number; // seconds of attention pulse remaining
  pulseColor: THREE.Color;
}

export function createShopScene(container: HTMLElement, opts: ShopSceneOptions = {}): ShopScene {
  const high = opts.quality !== "low";
  const drift = opts.autoDrift !== false;
  RectAreaLightUniformsLib.init();

  // ---------------------------------------------------------------- renderer
  const renderer = new THREE.WebGLRenderer({ antialias: !high, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, high ? 1.5 : 1));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.9;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  if (getComputedStyle(container).position === "static") container.style.position = "relative";
  renderer.domElement.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block;";
  container.appendChild(renderer.domElement);

  const labels = new CSS2DRenderer();
  labels.domElement.style.cssText = "position:absolute;inset:0;pointer-events:none;overflow:hidden;";
  container.appendChild(labels.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x15171a);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envRT = pmrem.fromScene(new RoomEnvironment(), 0.04);
  scene.environment = envRT.texture;
  scene.environmentIntensity = 0.35;

  const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 80);
  const camPos = new THREE.Vector3(1.9, 2.05, 0.9);
  const camTgt = new THREE.Vector3(-2.1, 1.0, -4.5);
  const overview = { pos: camPos.clone(), tgt: camTgt.clone() };
  camera.position.copy(camPos);

  const disposables: { dispose(): void }[] = [envRT];
  const track = <T extends { dispose(): void }>(d: T): T => { disposables.push(d); return d; };
  const std = (p: THREE.MeshStandardMaterialParameters) => track(new THREE.MeshStandardMaterial(p));
  const mesh = (g: THREE.BufferGeometry, m: THREE.Material, cast = true, recv = true) => {
    track(g);
    const o = new THREE.Mesh(g, m); o.castShadow = cast; o.receiveShadow = recv; return o;
  };

  // ---------------------------------------------------------------- room
  const room = new THREE.Group(); scene.add(room);
  const con = concrete(); track(con.map); track(con.rough);
  const floorMat = std({ map: con.map, roughnessMap: con.rough, roughness: 0.55, metalness: 0.0, envMapIntensity: 0.9 });
  const floor = mesh(new THREE.PlaneGeometry(14, 9.5), floorMat, false, true);
  floor.rotation.x = -Math.PI / 2; floor.position.set(0, 0, -0.25); room.add(floor);

  const wallTex = track(blockWall());
  const wallMat = std({ map: wallTex, roughness: 0.9 });
  const back = mesh(new THREE.PlaneGeometry(14, 4.4), wallMat, false, true);
  back.position.set(0, 2.2, -5); room.add(back);
  const left = mesh(new THREE.PlaneGeometry(9.5, 4.4), wallMat, false, true);
  left.rotation.y = Math.PI / 2; left.position.set(-7, 2.2, -0.25); room.add(left);
  // right wall with a door opening (3 panels)
  const rw = (len: number, h: number, z: number, y: number) => {
    const m = mesh(new THREE.PlaneGeometry(len, h), wallMat, false, true);
    m.rotation.y = -Math.PI / 2; m.position.set(7, y, z); room.add(m);
  };
  const dz0 = DOOR.z - DOOR.w / 2, dz1 = DOOR.z + DOOR.w / 2;
  rw(dz0 + 5, 4.4, (dz0 - 5) / 2, 2.2);
  rw(4.5 - dz1, 4.4, (dz1 + 4.5) / 2, 2.2);
  rw(DOOR.w, 4.4 - DOOR.h, DOOR.z, DOOR.h + (4.4 - DOOR.h) / 2);
  // ceiling
  const ceil = mesh(new THREE.PlaneGeometry(14, 9.5), std({ color: 0x2a2c30, roughness: 0.95 }), false, false);
  ceil.rotation.x = Math.PI / 2; ceil.position.set(0, 4.4, -0.25); room.add(ceil);
  // wainscot / safety base along back wall
  const base = mesh(new THREE.BoxGeometry(14, 0.12, 0.02), std({ color: 0x3a3d42, roughness: 0.6 }), false, true);
  base.position.set(0, 0.06, -4.99); room.add(base);
  // painted floor lines: walkway (muted cream) + receiving hatch zone
  const lineMat = std({ color: 0xd8d2bf, roughness: 0.6 });
  const addLine = (w: number, d: number, x: number, z: number) => {
    const m = mesh(new THREE.PlaneGeometry(w, d), lineMat, false, true);
    m.rotation.x = -Math.PI / 2; m.position.set(x, 0.002, z); room.add(m);
  };
  addLine(9.2, 0.07, -2.3, -3.65);
  addLine(0.07, 3.4, 4.6, -2.6); addLine(2.4, 0.07, 5.8, -0.9); addLine(2.4, 0.07, 5.8, -4.3);

  // roll-up door (raised most of the way) + track + daylight outside
  const slatTex = track(slats());
  const doorMat = std({ color: 0xb4b8bc, metalness: 0.7, roughness: 0.38, bumpMap: slatTex, bumpScale: 2, map: slatTex });
  const doorPanel = mesh(new THREE.PlaneGeometry(DOOR.w, 1.0), doorMat, true, true);
  doorPanel.rotation.y = -Math.PI / 2; doorPanel.position.set(6.96, DOOR.h - 0.5, DOOR.z); room.add(doorPanel);
  const drum = mesh(new THREE.CylinderGeometry(0.22, 0.22, DOOR.w + 0.3, 24), std({ color: 0x55595e, metalness: 0.8, roughness: 0.4 }));
  drum.rotation.x = Math.PI / 2; drum.position.set(6.75, DOOR.h + 0.3, DOOR.z); room.add(drum);
  for (const s of [-1, 1]) {
    const tr = mesh(new THREE.BoxGeometry(0.08, DOOR.h, 0.1), std({ color: 0x4a4e53, metalness: 0.8, roughness: 0.45 }));
    tr.position.set(6.94, DOOR.h / 2, DOOR.z + s * (DOOR.w / 2 + 0.05)); room.add(tr);
  }
  const outsideMat = new THREE.MeshBasicMaterial({ color: 0xdfe6ee }); track(outsideMat);
  const outside = new THREE.Mesh(track(new THREE.PlaneGeometry(40, 20)), outsideMat);
  outside.rotation.y = -Math.PI / 2; outside.position.set(16, 6, DOOR.z); room.add(outside);
  const apron = mesh(new THREE.PlaneGeometry(10, 12), std({ color: 0x77787a, roughness: 0.85 }), false, true);
  apron.rotation.x = -Math.PI / 2; apron.position.set(12, 0.0, DOOR.z); room.add(apron);
  const daylight = new THREE.RectAreaLight(0xe8eef6, 5, DOOR.w, DOOR.h - 1);
  daylight.position.set(7.05, (DOOR.h - 1) / 2, DOOR.z); daylight.lookAt(0, (DOOR.h - 1) / 2, DOOR.z); scene.add(daylight);

  // ---------------------------------------------------------------- lights
  scene.add(new THREE.HemisphereLight(0xdfe7ef, 0x2a2622, 0.35));
  const sun = new THREE.DirectionalLight(0xfff4e6, 1.6);
  sun.position.set(4, 7, 3); sun.target.position.set(-1, 0, -3);
  sun.castShadow = true;
  sun.shadow.mapSize.set(high ? 2048 : 1024, high ? 2048 : 1024);
  const sc = sun.shadow.camera; sc.left = -9; sc.right = 9; sc.top = 7; sc.bottom = -7; sc.near = 1; sc.far = 20;
  sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.02; sun.shadow.radius = 3;
  scene.add(sun, sun.target);
  const fixtureMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xf4f7ff, emissiveIntensity: 2.2 }); track(fixtureMat);
  const housingMat = std({ color: 0x8a8d92, metalness: 0.7, roughness: 0.4 });
  for (const [x, z] of [[-4.5, -3.2], [-1.0, -3.2], [2.5, -3.2], [-3, 0.5], [3.6, 0.2]] as [number, number][]) {
    const housing = mesh(new THREE.BoxGeometry(2.4, 0.06, 0.24), housingMat, false, false);
    housing.position.set(x, 3.75, z); room.add(housing);
    const tube = new THREE.Mesh(track(new THREE.BoxGeometry(2.3, 0.02, 0.16)), fixtureMat);
    tube.position.set(x, 3.71, z); room.add(tube);
    for (const s of [-1, 1]) {
      const chain = mesh(new THREE.CylinderGeometry(0.005, 0.005, 0.65, 4), housingMat, false, false);
      chain.position.set(x + s * 1.0, 4.08, z); room.add(chain);
    }
    const ra = new THREE.RectAreaLight(0xf2f5ff, 7, 2.3, 0.18);
    ra.position.set(x, 3.69, z); ra.lookAt(x, 0, z); scene.add(ra);
  }
  const shelfKey = new THREE.SpotLight(0xfff1de, 6, 12, Math.PI / 5, 0.6, 1.4);
  shelfKey.position.set(-1.5, 3.6, -1.2); shelfKey.target.position.set(-2.2, 1.0, -4.6);
  scene.add(shelfKey, shelfKey.target);

  // ---------------------------------------------------------------- shelving
  const upMat = std({ color: 0x2f3338, metalness: 0.6, roughness: 0.45 });
  const beamMat = std({ color: 0x9aa0a6, metalness: 0.9, roughness: 0.35 });
  const deckMat = std({ color: 0xa48863, roughness: 0.8 });
  const binMat = std({ color: 0x4c5662, roughness: 0.55, metalness: 0.0 });
  const shelves = new THREE.Group(); scene.add(shelves);
  {
    const ups: THREE.BufferGeometry[] = [], beams: THREE.BufferGeometry[] = [], decks: THREE.BufferGeometry[] = [];
    for (const ux of UNIT_X) {
      for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
        const g = new THREE.BoxGeometry(0.05, 2.3, 0.05); g.translate(ux + sx * 1.0, 1.15, SHELF_Z + sz * 0.28); ups.push(g);
      }
      for (const ly of LEVEL_Y) {
        for (const sz of [-1, 1]) {
          const g = new THREE.BoxGeometry(2.0, 0.06, 0.035); g.translate(ux, ly - 0.035, SHELF_Z + sz * 0.29); beams.push(g);
        }
        const d = new THREE.BoxGeometry(1.98, 0.018, 0.58); d.translate(ux, ly - 0.009, SHELF_Z); decks.push(d);
      }
    }
    shelves.add(mesh(mergeGeometries(ups)!, upMat), mesh(mergeGeometries(beams)!, beamMat), mesh(mergeGeometries(decks)!, deckMat));
    ups.concat(beams, decks).forEach((g) => g.dispose());
  }
  const binGeo = (() => {
    const t = 0.008, gs: THREE.BufferGeometry[] = [];
    const b = (w: number, h: number, d: number, x: number, y: number, z: number) => { const g = new THREE.BoxGeometry(w, h, d); g.translate(x, y, z); gs.push(g); };
    b(BIN_W, t, BIN_D, 0, t / 2, 0);
    b(t, BIN_H, BIN_D, -BIN_W / 2, BIN_H / 2, 0); b(t, BIN_H, BIN_D, BIN_W / 2, BIN_H / 2, 0);
    b(BIN_W, BIN_H, t, 0, BIN_H / 2, -BIN_D / 2);
    b(BIN_W, BIN_H * 0.55, t, 0, BIN_H * 0.275, BIN_D / 2); // low front lip
    const m = mergeGeometries(gs)!; gs.forEach((g) => g.dispose()); return track(m);
  })();
  const hitGeo = track(new THREE.BoxGeometry(BIN_W, 0.4, BIN_D));
  const hitMat = track(new THREE.MeshBasicMaterial({ visible: false }));
  const labelGeo = track(new THREE.PlaneGeometry(0.42, 0.105));
  const ledGeo = track(new THREE.BoxGeometry(BIN_W - 0.04, 0.012, 0.01));
  const ghostMat = track(new THREE.MeshBasicMaterial({ color: GREEN, transparent: true, opacity: 0.32, depthWrite: false, blending: THREE.AdditiveBlending }));
  const lib = new PartLibrary(); track(lib);

  // filler stock (cardboard cartons) so the room looks lived-in
  const fillerTex = track(cardboard("STOCK"));
  const fillerMat = std({ map: fillerTex, roughness: 0.85 });
  const fillerGeo = track(new RoundedBoxGeometry(0.4, 0.26, 0.42, 2, 0.006));
  const fillers: THREE.InstancedMesh = new THREE.InstancedMesh(fillerGeo, fillerMat, 80);
  fillers.castShadow = fillers.receiveShadow = true; fillers.count = 0; scene.add(fillers);

  const bins = new Map<string, Bin>();
  const slotPos = (u: number, l: number, c: number) => new THREE.Vector3(UNIT_X[u] + (c ? 0.48 : -0.48), LEVEL_Y[l], SHELF_Z + 0.02);
  const slotKey = (u: number, l: number, c: number) => `${u}:${l}:${c}`;
  const usedSlots = new Map<string, string>(); // slot → sku

  function pickSlot(kind: PartKind): [number, number, number] {
    const heavy = HEAVY.includes(kind);
    const order = heavy ? [0, 1, 2, 3, 4] : [2, 3, 1, 4, 0];
    for (const l of order) for (let u = 0; u < UNIT_X.length; u++) for (const c of [0, 1]) {
      if (!usedSlots.has(slotKey(u, l, c))) return [u, l, c];
    }
    return [0, 0, 0];
  }

  function layoutSlots(kind: PartKind): { slots: THREE.Matrix4[]; cap: number } {
    const S = 1.3; const [w, h, d] = lib.model(kind).size.map((v) => v * S);
    const iw = BIN_W - 0.05, id = BIN_D - 0.04;
    const nx = Math.max(1, Math.floor(iw / (w + 0.008)));
    const nz = Math.max(1, Math.floor(id / (d + 0.008)));
    const ny = Math.max(1, Math.min(4, Math.floor(0.34 / h)));
    const slots: THREE.Matrix4[] = [];
    const sx = (nx - 1) * (w + 0.008), sz = (nz - 1) * (d + 0.008);
    for (let y = 0; y < ny; y++) for (let z = nz - 1; z >= 0; z--) for (let x = 0; x < nx; x++) {
      const jitter = ((x * 7 + z * 13 + y * 5) % 7) / 7 - 0.5;
      const m = new THREE.Matrix4().compose(
        new THREE.Vector3(-sx / 2 + x * (w + 0.008) + jitter * 0.004, 0.008 + y * h, -sz / 2 + z * (d + 0.008)),
        new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), jitter * 0.08),
        new THREE.Vector3(S, S, S));
      slots.push(m);
    }
    return { slots, cap: slots.length };
  }

  const shown = (b: Bin, q: number) => {
    q = Math.max(0, q);
    return Math.min(b.cap, b.item.max_qty > 0 && b.item.max_qty > b.cap ? Math.ceil((q / b.item.max_qty) * b.cap) : q);
  };

  function status(it: InventoryItem): "out" | "low" | "ok" {
    if (it.qty <= 0) return "out";
    if (it.qty < it.min_qty) return "low";
    return "ok";
  }

  function drawLabel(b: Bin) {
    const c = binLabel(b.item.sku, b.item.name);
    const g = c.getContext("2d")!;
    const st = status(b.item);
    g.fillStyle = st === "out" ? "#c8321f" : st === "low" ? "#d98a12" : "#2a2a2a";
    g.font = "700 30px 'JetBrains Mono', monospace";
    g.fillText(`${b.item.qty}/${b.item.max_qty}`, 330, 52);
    (b.labelTex.image as HTMLCanvasElement) = c;
    b.labelTex.needsUpdate = true;
  }

  function refreshBin(b: Bin) {
    const n = shown(b, b.item.qty);
    const ng = Math.max(0, shown(b, b.item.qty + (b.item.incoming_qty ?? 0)) - n);
    b.inst.forEach((im) => { for (let i = 0; i < n; i++) im.setMatrixAt(i, b.slots[i]); im.count = n; im.instanceMatrix.needsUpdate = true; });
    b.ghosts.forEach((im) => { for (let i = 0; i < ng; i++) im.setMatrixAt(i, b.slots[n + i]); im.count = ng; im.instanceMatrix.needsUpdate = true; });
    const st = status(b.item);
    const col = (b.item.incoming_qty ?? 0) > 0 ? GREEN : st === "out" ? RED : st === "low" ? AMBER : new THREE.Color(0x4a4f55);
    b.led.color.copy(col);
    drawLabel(b);
  }

  function makeBin(item: InventoryItem): Bin {
    const kind = kindOf(`${item.part_type} ${item.name}`);
    const [u, l, c] = pickSlot(kind);
    usedSlots.set(slotKey(u, l, c), item.sku);
    const group = new THREE.Group(); group.position.copy(slotPos(u, l, c));
    const body = new THREE.Mesh(binGeo, binMat); body.castShadow = body.receiveShadow = true; group.add(body);
    const hit = new THREE.Mesh(hitGeo, hitMat); hit.position.y = 0.2; hit.userData.sku = item.sku; group.add(hit);
    const labelTex = tex(binLabel(item.sku, item.name));
    const labelMat = new THREE.MeshStandardMaterial({ map: labelTex, roughness: 0.6, emissive: 0x000000, emissiveMap: labelTex, emissiveIntensity: 0 });
    const label = new THREE.Mesh(labelGeo, labelMat); label.position.set(0, BIN_H * 0.3, BIN_D / 2 + 0.006); group.add(label);
    const ledMat = new THREE.MeshBasicMaterial({ color: 0x4a4f55 });
    const led = new THREE.Mesh(ledGeo, ledMat); led.position.set(0, -0.05, 0.31); group.add(led);
    const { slots, cap } = layoutSlots(kind);
    const model = lib.model(kind);
    const inst = model.parts.map((p) => { const im = new THREE.InstancedMesh(p.geo, p.mat, cap); im.castShadow = im.receiveShadow = true; im.count = 0; group.add(im); return im; });
    const ghosts = model.parts.map((p) => { const im = new THREE.InstancedMesh(p.geo, ghostMat, cap); im.count = 0; group.add(im); return im; });
    scene.add(group);
    const b: Bin = { item: { ...item }, kind, group, hit, labelMat, labelTex, led: ledMat, inst, ghosts, slots, cap, pulse: 0, pulseColor: AMBER.clone() };
    refreshBin(b);
    return b;
  }

  function freeBin(b: Bin) {
    scene.remove(b.group);
    b.labelTex.dispose(); b.labelMat.dispose(); b.led.dispose();
    b.inst.concat(b.ghosts).forEach((im) => im.dispose());
    for (const [k, v] of usedSlots) if (v === b.item.sku) usedSlots.delete(k);
  }

  function layoutFillers() {
    const m = new THREE.Matrix4(); let i = 0;
    for (let u = 0; u < UNIT_X.length; u++) for (let l = 0; l < LEVEL_Y.length; l++) for (const c of [0, 1]) {
      if (usedSlots.has(slotKey(u, l, c))) continue;
      const p = slotPos(u, l, c);
      for (const dx of [-0.22, 0.22]) {
        if (i >= 80) break;
        const r = ((u * 5 + l * 3 + c + dx * 10) % 5) / 5;
        const s = 0.85 + r * 0.3;
        m.compose(new THREE.Vector3(p.x + dx, p.y + 0.13 * s, p.z - 0.02 + r * 0.05), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), (r - 0.5) * 0.12), new THREE.Vector3(1, s, 1));
        fillers.setMatrixAt(i++, m);
      }
    }
    fillers.count = i; fillers.instanceMatrix.needsUpdate = true;
  }

  function setInventory(items: InventoryItem[]) {
    const seen = new Set<string>();
    for (const it of items) {
      seen.add(it.sku);
      const b = bins.get(it.sku);
      if (b && kindOf(`${it.part_type} ${it.name}`) === b.kind) { b.item = { ...it }; refreshBin(b); }
      else { if (b) freeBin(b); bins.set(it.sku, makeBin(it)); }
    }
    for (const [sku, b] of bins) if (!seen.has(sku)) { freeBin(b); bins.delete(sku); }
    layoutFillers();
  }

  // ---------------------------------------------------------------- counter + receiving
  const counter = new THREE.Group(); counter.position.copy(COUNTER); scene.add(counter);
  {
    const topMat = new THREE.MeshPhysicalMaterial({ color: 0x3b3a38, roughness: 0.35, clearcoat: 0.6, clearcoatRoughness: 0.3 }); track(topMat);
    const bodyMat = std({ color: 0x5a5f66, metalness: 0.6, roughness: 0.45 });
    const top = mesh(new RoundedBoxGeometry(3.0, 0.05, 0.85, 2, 0.01), topMat); top.position.set(0, 1.0, 0); counter.add(top);
    const body = mesh(new THREE.BoxGeometry(2.9, 0.97, 0.7), bodyMat); body.position.set(0, 0.485, -0.05); counter.add(body);
    const kick = mesh(new THREE.BoxGeometry(2.9, 0.1, 0.66), std({ color: 0x1d1f22, roughness: 0.8 })); kick.position.set(0, 0.05, -0.05); counter.add(kick);
    // monitor
    const scr = mesh(new RoundedBoxGeometry(0.62, 0.38, 0.03, 2, 0.008), std({ color: 0x111214, roughness: 0.3, metalness: 0.4 })); scr.position.set(-0.8, 1.38, -0.15); scr.rotation.y = 0.35; counter.add(scr);
    const stand = mesh(new THREE.BoxGeometry(0.05, 0.2, 0.05), std({ color: 0x222326 })); stand.position.set(-0.8, 1.12, -0.17); counter.add(stand);
    // label printer
    const printer = mesh(new RoundedBoxGeometry(0.2, 0.14, 0.24, 2, 0.02), std({ color: 0xe6e6e2, roughness: 0.5 })); printer.position.set(0.55, 1.095, 0.05); counter.add(printer);
    // parts catalog binder + tray
    const tray = mesh(new THREE.BoxGeometry(0.4, 0.04, 0.3), std({ color: 0x2c2f33, roughness: 0.6 })); tray.position.set(0.0, 1.045, 0.1); counter.add(tray);
    // pallet with cartons at receiving
    const pallet = new THREE.Group(); pallet.position.set(RECEIVING.x - 0.2, 0, RECEIVING.z - 1.0);
    const woodMat = std({ color: 0x9c8058, roughness: 0.9 });
    for (let i = 0; i < 5; i++) { const s = mesh(new THREE.BoxGeometry(1.2, 0.02, 0.14), woodMat); s.position.set(0, 0.13, -0.5 + i * 0.25); pallet.add(s); }
    for (const z of [-0.45, 0, 0.45]) { const s = mesh(new THREE.BoxGeometry(1.2, 0.1, 0.1), woodMat); s.position.set(0, 0.07, z); pallet.add(s); }
    const cartonMat = std({ map: track(cardboard("RCV")), roughness: 0.85 });
    for (const [x, y, z, s] of [[-0.3, 0, -0.25, 1], [0.3, 0, -0.25, 1], [-0.3, 0, 0.25, 1], [0.25, 0, 0.25, 0.8], [0, 1, 0, 0.9]] as number[][]) {
      const c = mesh(new RoundedBoxGeometry(0.55 * s, 0.4 * s, 0.45 * s, 2, 0.008), cartonMat);
      c.position.set(x, 0.14 + 0.2 * s + y * 0.4, z); c.rotation.y = (x + z) * 0.2; pallet.add(c);
    }
    scene.add(pallet);
  }

  // wall screen (scoreboard)
  const [scrC, scrG] = makeCanvas(1024, 576);
  const scrTex = track(tex(scrC));
  const scrMat = new THREE.MeshBasicMaterial({ map: scrTex, toneMapped: false }); track(scrMat);
  const screen = new THREE.Mesh(track(new THREE.PlaneGeometry(1.6, 0.9)), scrMat);
  screen.position.set(3.4, 2.7, -4.96); scene.add(screen);
  const bezel = mesh(new THREE.BoxGeometry(1.68, 0.98, 0.04), std({ color: 0x0c0d0f, roughness: 0.4 }), false, false);
  bezel.position.set(3.4, 2.7, -4.99); scene.add(bezel);
  function drawScreen(title: string, lines: string[], accent = false) {
    scrG.fillStyle = "#0b0d10"; scrG.fillRect(0, 0, 1024, 576);
    scrG.fillStyle = "#8b939c"; scrG.font = "500 30px Inter, sans-serif"; scrG.fillText("MISSION STREET AUTO · PARTS", 48, 70);
    scrG.fillStyle = accent ? "#22c550" : "#e8eaed"; scrG.font = "700 52px Inter, sans-serif";
    scrG.fillText(title.slice(0, 34), 48, 160);
    scrG.font = "500 32px 'JetBrains Mono', monospace"; scrG.fillStyle = "#c6ccd2";
    lines.slice(0, 7).forEach((l, i) => scrG.fillText(l.slice(0, 52), 48, 240 + i * 48));
    scrTex.needsUpdate = true;
  }
  function screenFromInventory() {
    const all = [...bins.values()];
    const low = all.filter((b) => status(b.item) !== "ok");
    drawScreen(`${all.length} SKUs on shelf`, [
      `${low.length} below minimum`,
      ...low.slice(0, 5).map((b) => `${b.item.qty <= 0 ? "OUT" : "LOW"}  ${b.item.name}`),
    ]);
  }

  // van outside the receiving door
  const van = new THREE.Group();
  {
    const paint = new THREE.MeshPhysicalMaterial({ color: 0xe9eaec, metalness: 0.2, roughness: 0.32, clearcoat: 1, clearcoatRoughness: 0.08 }); track(paint);
    const glass = new THREE.MeshPhysicalMaterial({ color: 0x0d1116, metalness: 0.1, roughness: 0.05, clearcoat: 1 }); track(glass);
    const body = mesh(new RoundedBoxGeometry(4.8, 2.05, 1.95, 4, 0.14), paint); body.position.set(0, 1.35, 0); van.add(body);
    const nose = mesh(new RoundedBoxGeometry(0.9, 1.1, 1.9, 4, 0.2), paint); nose.position.set(2.75, 0.9, 0); van.add(nose);
    const ws = mesh(new THREE.PlaneGeometry(1.7, 0.75), glass); ws.position.set(2.42, 1.85, 0); ws.rotation.y = Math.PI / 2; ws.rotation.x = 0; van.add(ws);
    const tireMat = std({ color: 0x141414, roughness: 0.9 });
    const rimMat = std({ color: 0x9a9ea3, metalness: 1, roughness: 0.3 });
    for (const x of [-1.6, 2.0]) for (const z of [-0.9, 0.9]) {
      const t = mesh(new THREE.CylinderGeometry(0.4, 0.4, 0.26, 28), tireMat); t.rotation.x = Math.PI / 2; t.position.set(x, 0.4, z); van.add(t);
      const r = mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.27, 20), rimMat); r.rotation.x = Math.PI / 2; r.position.set(x, 0.4, z); van.add(r);
    }
    const stripe = mesh(new THREE.BoxGeometry(4.0, 0.08, 1.97), std({ color: 0x3a4048, roughness: 0.4 })); stripe.position.set(-0.2, 1.05, 0); van.add(stripe);
  }
  const VAN_HOME = new THREE.Vector3(12.2, 0, DOOR.z);
  van.position.copy(VAN_HOME); van.rotation.y = Math.PI; scene.add(van);

  // ---------------------------------------------------------------- post
  let composer: EffectComposer | null = null;
  let smaa: SMAAPass | null = null;
  let bloom: UnrealBloomPass | null = null;
  let gtao: GTAOPass | null = null;
  if (high) {
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    gtao = new GTAOPass(scene, camera, 1, 1);
    gtao.updateGtaoMaterial({ radius: 0.35, distanceExponent: 1.5, thickness: 1, scale: 1.1, samples: 12 });
    gtao.blendIntensity = 0.85;
    composer.addPass(gtao);
    bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.55, 0.5, 0.88);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
    composer.addPass(new ShaderPass({
      uniforms: { tDiffuse: { value: null }, amt: { value: 0.32 } },
      vertexShader: "varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);} ",
      fragmentShader: "uniform sampler2D tDiffuse; uniform float amt; varying vec2 vUv; void main(){ vec4 c=texture2D(tDiffuse,vUv); vec2 d=vUv-0.5; float v=1.0-amt*smoothstep(0.25,0.85,dot(d,d)*2.2); gl_FragColor=vec4(c.rgb*v,c.a);} ",
    }));
    smaa = new SMAAPass(1, 1);
    composer.addPass(smaa);
  }

  // ---------------------------------------------------------------- animation infra
  const clock = new THREE.Clock();
  let now = 0;
  const anims: Anim[] = [];
  const animate = (dur: number, step: (k: number) => void, done?: () => void) => anims.push({ t0: now, dur, step, done });
  const temp = new Set<THREE.Object3D>();
  const tempDispose = (o: THREE.Object3D) => {
    o.removeFromParent(); temp.delete(o);
    o.traverse((c) => {
      const m = c as THREE.Mesh;
      if (m.isMesh && m.userData.own) { m.geometry.dispose(); (m.material as THREE.Material).dispose(); }
      const css = c as CSS2DObject & { isCSS2DObject?: boolean };
      if (css.isCSS2DObject) css.element.remove();
    });
  };
  const addTemp = (o: THREE.Object3D, ttl?: number) => {
    scene.add(o); temp.add(o);
    if (ttl) animate(ttl, () => {}, () => tempDispose(o));
    return o;
  };
  const ownMesh = (g: THREE.BufferGeometry, m: THREE.Material) => { const o = new THREE.Mesh(g, m); o.userData.own = true; return o; };

  // camera tween
  let camAnim: { fromP: THREE.Vector3; fromT: THREE.Vector3; toP: THREE.Vector3; toT: THREE.Vector3; t0: number; dur: number } | null = null;
  let home = overview;
  let lastFocusAt = -100;
  function flyTo(pos: THREE.Vector3, tgt: THREE.Vector3, dur = 1.6) {
    camAnim = { fromP: camPos.clone(), fromT: camTgt.clone(), toP: pos.clone(), toT: tgt.clone(), t0: now, dur };
    lastFocusAt = now;
  }
  function focusBin(b: Bin, dur = 1.6) {
    const p = b.group.position;
    flyTo(new THREE.Vector3(p.x + 0.9, p.y + 0.55, p.z + 2.4), new THREE.Vector3(p.x, p.y + 0.1, p.z), dur);
  }
  const counterView = { pos: new THREE.Vector3(2.0, 2.3, 3.0), tgt: new THREE.Vector3(4.3, 1.5, -0.6) };
  const receivingView = { pos: new THREE.Vector3(3.6, 2.9, 3.0), tgt: new THREE.Vector3(6.4, 0.7, -2.8) };

  function setFocus(t: FocusTarget) {
    if (t === "overview") flyTo(overview.pos, overview.tgt);
    else if (t === "counter") flyTo(counterView.pos, counterView.tgt);
    else if (t === "receiving") flyTo(receivingView.pos, receivingView.tgt);
    else if (t.startsWith("shelf:")) {
      const q = t.slice(6);
      const kind = kindOf(q);
      const b = [...bins.values()].find((x) => x.item.part_type.toLowerCase() === q.toLowerCase()) ?? [...bins.values()].find((x) => x.kind === kind) ?? bins.get(q);
      if (b) focusBin(b);
    }
  }

  // ---------------------------------------------------------------- labels (CSS2D)
  const fontUI = "Inter, system-ui, sans-serif";
  function toast(text: string, at: THREE.Vector3, opts2: { accent?: "green" | "amber" | "red"; sub?: string; ttl?: number } = {}) {
    const el = document.createElement("div");
    const col = opts2.accent === "amber" ? "#f0a020" : opts2.accent === "red" ? "#e5402e" : "#22c550";
    el.style.cssText = `font:500 12px/1.35 ${fontUI};color:#eef1f4;background:rgba(14,16,19,.82);border:1px solid rgba(255,255,255,.08);border-left:3px solid ${col};padding:6px 10px;border-radius:6px;max-width:280px;backdrop-filter:blur(6px);box-shadow:0 6px 24px rgba(0,0,0,.35);transition:opacity .4s,transform .4s;opacity:0;transform:translateY(6px);white-space:normal;`;
    el.innerHTML = `<div>${escapeHtml(text)}</div>${opts2.sub ? `<div style="color:#9aa3ad;font-size:11px;margin-top:2px">${escapeHtml(opts2.sub)}</div>` : ""}`;
    const o = new CSS2DObject(el); o.position.copy(at);
    addTemp(o);
    requestAnimationFrame(() => { el.style.opacity = "1"; el.style.transform = "translateY(0)"; });
    const ttl = opts2.ttl ?? 4.2;
    animate(ttl, () => {}, () => { el.style.opacity = "0"; animate(0.5, () => {}, () => tempDispose(o)); });
  }
  const hoverEl = document.createElement("div");
  hoverEl.style.cssText = `font:500 12px/1.35 ${fontUI};color:#eef1f4;background:rgba(14,16,19,.88);border:1px solid rgba(255,255,255,.1);padding:6px 10px;border-radius:6px;pointer-events:none;white-space:nowrap;`;
  const hoverObj = new CSS2DObject(hoverEl); hoverObj.visible = false; scene.add(hoverObj);

  // ---------------------------------------------------------------- holo vendor cards
  const holoEdgeMat = new THREE.LineBasicMaterial({ color: GREEN, transparent: true, opacity: 0.9 }); track(holoEdgeMat);
  const cardGeo = track(new THREE.PlaneGeometry(0.62, 0.38));
  const cardEdgeGeo = track(new THREE.EdgesGeometry(cardGeo));
  interface Card { sku: string; vendor: string; price: number; obj: THREE.Group; mat: THREE.MeshBasicMaterial; edge: THREE.LineSegments; texr: THREE.CanvasTexture; alive: boolean }
  let cards: Card[] = [];
  function cardCanvas(l: Record<string, unknown>, chosen = false) {
    const [c, g] = makeCanvas(620, 380);
    g.fillStyle = chosen ? "rgba(20,70,38,0.78)" : "rgba(8,26,16,0.55)"; g.fillRect(0, 0, 620, 380);
    g.fillStyle = "rgba(34,197,80,0.12)"; for (let y = 0; y < 380; y += 6) g.fillRect(0, y, 620, 1);
    g.fillStyle = "#9df5b8"; g.font = "600 28px Inter, sans-serif"; g.fillText(String(l.vendor ?? l.vendor_id ?? "Vendor").slice(0, 28), 28, 56);
    g.fillStyle = "#e9fff0"; g.font = "700 44px Inter, sans-serif"; g.fillText(`${String(l.brand ?? "")}`.slice(0, 18), 28, 124);
    g.font = "500 26px 'JetBrains Mono', monospace"; g.fillStyle = "#bfeccc"; g.fillText(String(l.sku ?? "").slice(0, 26), 28, 172);
    g.font = "700 64px Inter, sans-serif"; g.fillStyle = "#ffffff"; g.fillText(`$${Number(l.price ?? 0).toFixed(0)}`, 28, 268);
    g.font = "500 26px Inter, sans-serif"; g.fillStyle = "#9df5b8";
    const eta = Number(l.eta_minutes ?? 0);
    g.fillText(eta ? `ETA ${eta >= 600 ? Math.round(eta / 1440) + " d" : eta + " min"}` : "", 28, 330);
    if (l.score !== undefined) g.fillText(`match ${(Number(l.score) * 100).toFixed(0)}%`, 400, 330);
    return c;
  }
  function clearCards() {
    cards.forEach((c) => { tempDispose(c.obj); c.mat.dispose(); c.texr.dispose(); });
    cards = [];
  }
  function showCards(listings: Record<string, unknown>[]) {
    clearCards();
    const n = Math.min(5, listings.length);
    const base = new THREE.Vector3(COUNTER.x, 1.95, COUNTER.z + 0.1);
    listings.slice(0, n).forEach((l, i) => {
      const t = tex(cardCanvas(l));
      const mat = new THREE.MeshBasicMaterial({ map: t, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false, toneMapped: false });
      const g = new THREE.Group();
      const plane = new THREE.Mesh(cardGeo, mat); g.add(plane);
      const edge = new THREE.LineSegments(cardEdgeGeo, holoEdgeMat.clone()); g.add(edge);
      (edge.material as THREE.Material).userData.own = true;
      const off = i - (n - 1) / 2;
      const target = new THREE.Vector3(base.x + off * 0.68, base.y + Math.abs(off) * -0.06, base.z + Math.abs(off) * -0.12);
      g.position.set(target.x, 1.1, target.z);
      g.rotation.y = -off * 0.12 - 0.35;
      addTemp(g);
      const card: Card = { sku: String(l.sku ?? ""), vendor: String(l.vendor_id ?? ""), price: Number(l.price ?? 0), obj: g, mat, edge, texr: t, alive: true };
      cards.push(card);
      animate(0.9 + i * 0.12, (k) => { const e = ease(k); g.position.y = 1.1 + (target.y - 1.1) * e; mat.opacity = e * 0.95; });
    });
  }
  function findCard(ev: SalEvent): Card | undefined {
    const sku = ev.refs?.sku;
    return cards.find((c) => c.alive && sku && c.sku === sku)
      ?? cards.find((c) => c.alive && ev.refs?.vendor_id === c.vendor && ev.money?.wholesale !== undefined && Math.abs(c.price - ev.money.wholesale) < 0.5);
  }
  function rejectCard(ev: SalEvent) {
    const c = findCard(ev);
    if (!c) return;
    c.alive = false;
    const em = c.edge.material as THREE.LineBasicMaterial;
    em.color.copy(RED);
    const y0 = c.obj.position.y;
    toast(ev.summary ?? "Rejected", c.obj.position.clone().add(new THREE.Vector3(0, 0.3, 0)), { accent: "red", sub: ev.reason, ttl: 3.4 });
    animate(1.6, (k) => { c.mat.opacity = 0.95 * (1 - k); em.opacity = 0.9 * (1 - k); c.obj.position.y = y0 + k * 0.25; c.obj.scale.setScalar(1 - k * 0.15); });
  }
  function chooseCard(ev: SalEvent) {
    const c = findCard(ev);
    cards.forEach((o) => { if (o !== c && o.alive) { o.alive = false; const m0 = o.mat.opacity; animate(0.8, (k) => { o.mat.opacity = m0 * (1 - k); (o.edge.material as THREE.LineBasicMaterial).opacity = 0.9 * (1 - k); }); } });
    if (!c) return;
    const t2 = tex(cardCanvas({ vendor: c.vendor, sku: c.sku, price: c.price, brand: "Chosen" }, true));
    // keep the original card text, brighten it
    t2.dispose();
    const p0 = c.obj.position.clone(), r0 = c.obj.rotation.y;
    const to = new THREE.Vector3(COUNTER.x, 2.0, COUNTER.z + 0.25);
    animate(1.0, (k) => { const e = ease(k); c.obj.position.lerpVectors(p0, to, e); c.obj.rotation.y = r0 * (1 - e) - 0.3 * e; c.obj.scale.setScalar(1 + 0.25 * e); });
    c.mat.color.setRGB(1.25, 1.6, 1.3);
    (c.edge.material as THREE.LineBasicMaterial).color.setRGB(0.4, 3, 0.9);
    toast(ev.summary ?? "Chosen", to.clone().add(new THREE.Vector3(0, 0.38, 0)), { accent: "green", sub: ev.reason });
    animate(9, () => {}, () => { if (cards.includes(c)) clearCards(); });
  }

  // ---------------------------------------------------------------- effects
  function scanSweep() {
    const g = new THREE.PlaneGeometry(0.12, 2.3);
    const m = new THREE.MeshBasicMaterial({ color: GREEN, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
    const beam = ownMesh(g, m); beam.position.set(-6.8, 1.15, SHELF_Z + 0.33);
    const light = new THREE.PointLight(GREEN, 2.5, 2.2, 1.5); beam.add(light);
    addTemp(beam);
    const x0 = -6.8, x1 = 2.1;
    animate(3.2, (k) => {
      beam.position.x = x0 + (x1 - x0) * k;
      m.opacity = 0.5 * Math.sin(Math.PI * k) + 0.05;
      for (const b of bins.values()) {
        const d = Math.abs(b.group.position.x - beam.position.x);
        if (d < 0.5) { b.pulse = Math.max(b.pulse, 0.6); b.pulseColor.copy(GREEN); }
      }
    }, () => tempDispose(beam));
  }

  function partFlight(b: Bin, from: THREE.Vector3, n: number, onArrive: () => void) {
    const model = lib.model(b.kind);
    const to = b.group.position.clone().add(new THREE.Vector3(0, 0.15, 0));
    let landed = 0;
    for (let i = 0; i < n; i++) {
      const g = new THREE.Group();
      model.parts.forEach((p) => g.add(new THREE.Mesh(p.geo, p.mat)));
      g.scale.setScalar(1.6);
      g.position.copy(from);
      const glow = new THREE.PointLight(GREEN, 0.8, 0.8); g.add(glow);
      addTemp(g);
      const delay = i * 0.18;
      animate(1.5 + delay, (k) => {
        const kk = Math.max(0, (k * (1.5 + delay) - delay) / 1.5);
        const e = ease(kk);
        g.position.lerpVectors(from, to, e); g.position.y += Math.sin(Math.PI * e) * 1.4;
        g.rotation.y = e * 4; g.rotation.x = e * 1.5;
        g.scale.setScalar(1.6 - 0.6 * e);
      }, () => { tempDispose(g); landed++; if (landed === n) onArrive(); });
    }
  }

  function parcelAt(pos: THREE.Vector3, drop = 2.2) {
    const g = new RoundedBoxGeometry(0.5, 0.36, 0.42, 2, 0.008);
    const m = new THREE.MeshStandardMaterial({ map: fillerTex, roughness: 0.85 });
    const box = ownMesh(g, m); box.castShadow = true; box.receiveShadow = true;
    box.position.set(pos.x, pos.y + drop, pos.z); addTemp(box);
    const y1 = pos.y + 0.18;
    animate(0.9, (k) => { const e = k * k; box.position.y = y1 + drop * (1 - e); if (k > 0.98) box.position.y = y1; box.rotation.y = (1 - k) * 0.6; });
    return box;
  }

  function vanTrip(onBack?: () => void) {
    const p0 = VAN_HOME.clone();
    animate(2.2, (k) => { const e = ease(k); van.position.set(p0.x + e * 1.5, 0, p0.z - e * 16); van.rotation.y = Math.PI + e * 0.25; },
      () => animate(1.4, () => {}, () => animate(2.4, (k) => {
        const e = ease(k); van.position.set(p0.x + (1 - e) * 1.5, 0, p0.z + 16 * (1 - e)); van.rotation.y = Math.PI - (1 - e) * 0.2;
      }, () => { van.position.copy(p0); van.rotation.y = Math.PI; onBack?.(); })));
  }

  function printLabel(text: string) {
    const [c, g] = makeCanvas(256, 128);
    g.fillStyle = "#f6f5f0"; g.fillRect(0, 0, 256, 128);
    g.fillStyle = "#111"; g.font = "700 22px 'JetBrains Mono', monospace"; g.fillText(text.slice(0, 16), 14, 40);
    for (let i = 0; i < 40; i++) g.fillRect(14 + i * 5.6, 60, (i * 7) % 3 ? 3 : 1.5, 50);
    const t = tex(c);
    const m = new THREE.MeshStandardMaterial({ map: t, roughness: 0.6 });
    const lbl = ownMesh(new THREE.PlaneGeometry(0.16, 0.08), m);
    const p = COUNTER.clone().add(new THREE.Vector3(0.55, 1.12, 0.17));
    lbl.position.copy(p); lbl.rotation.x = -0.6; addTemp(lbl);
    animate(1.2, (k) => { lbl.position.z = p.z + 0.12 * ease(k); lbl.position.y = p.y - 0.03 * ease(k); });
    animate(7, () => {}, () => { t.dispose(); tempDispose(lbl); });
  }

  function badge(text: string, sub?: string) {
    const g = new THREE.Group();
    const ring = ownMesh(new THREE.TorusGeometry(0.18, 0.012, 12, 64), new THREE.MeshBasicMaterial({ color: GREEN, transparent: true, toneMapped: false }));
    const check = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-0.08, 0, 0), new THREE.Vector3(-0.02, -0.06, 0), new THREE.Vector3(0.09, 0.07, 0)]),
      new THREE.LineBasicMaterial({ color: GREEN, transparent: true }));
    check.userData.own = true;
    const disc = ownMesh(new THREE.CircleGeometry(0.17, 48), new THREE.MeshBasicMaterial({ color: GREEN, transparent: true, opacity: 0.15, depthWrite: false }));
    g.add(ring, check, disc);
    g.position.set(COUNTER.x + 0.9, 1.3, COUNTER.z + 0.2);
    addTemp(g);
    const lt = new THREE.PointLight(GREEN, 3, 3); g.add(lt);
    toast(text, g.position.clone().add(new THREE.Vector3(0, 0.75, 0)), { accent: "green", sub });
    animate(4.5, (k) => { g.position.y = 1.3 + ease(Math.min(1, k * 3)) * 0.6; g.rotation.y = Math.sin(now * 2) * 0.4; const o = k > 0.8 ? (1 - k) * 5 : 1; (ring.material as THREE.MeshBasicMaterial).opacity = o; (check.material as THREE.LineBasicMaterial).opacity = o; lt.intensity = 3 * o; }, () => {
      (check.geometry as THREE.BufferGeometry).dispose(); (check.material as THREE.Material).dispose(); tempDispose(g);
    });
  }

  function docScan(ev: SalEvent) {
    const [c, g] = makeCanvas(256, 330);
    g.fillStyle = "#f5f4ef"; g.fillRect(0, 0, 256, 330);
    g.fillStyle = "#222"; g.font = "700 18px Inter, sans-serif"; g.fillText("STATEMENT", 18, 34);
    g.fillStyle = "#777"; for (let i = 0; i < 18; i++) { g.fillRect(18, 56 + i * 14, 120 + ((i * 37) % 90), 5); g.fillRect(210, 56 + i * 14, 28, 5); }
    const t = tex(c);
    const doc = ownMesh(new THREE.PlaneGeometry(0.42, 0.54), new THREE.MeshStandardMaterial({ map: t, roughness: 0.7, side: THREE.DoubleSide }));
    doc.position.set(COUNTER.x - 0.1, 1.65, COUNTER.z + 0.2); doc.rotation.y = -0.35;
    const line = ownMesh(new THREE.PlaneGeometry(0.48, 0.012), new THREE.MeshBasicMaterial({ color: GREEN, toneMapped: false, transparent: true }));
    line.position.z = 0.005; doc.add(line);
    addTemp(doc);
    toast(ev.summary ?? "Statement parsed", doc.position.clone().add(new THREE.Vector3(0, 0.45, 0)), { accent: "green", sub: ev.reason });
    animate(3.6, (k) => { line.position.y = 0.27 - 0.54 * ((k * 2) % 1); (line.material as THREE.MeshBasicMaterial).opacity = k > 0.9 ? (1 - k) * 10 : 1; doc.position.y = 1.65 + Math.sin(now * 1.5) * 0.02; },
      () => { t.dispose(); tempDispose(doc); });
  }

  function ping(at: THREE.Vector3) {
    const m = new THREE.MeshBasicMaterial({ color: GREEN, transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
    const r = ownMesh(new THREE.RingGeometry(0.08, 0.1, 48), m); r.position.copy(at); r.lookAt(camera.position);
    addTemp(r);
    animate(1.2, (k) => { r.scale.setScalar(1 + k * 3); m.opacity = 1 - k; }, () => tempDispose(r));
  }

  // ---------------------------------------------------------------- events
  const roKind = new Map<string, PartKind>();
  const lastChosenBySku = new Map<string, PartKind>();
  function binFor(ev: SalEvent, createIfMissing = false): Bin | undefined {
    const sku = ev.refs?.sku;
    if (sku && bins.has(sku)) return bins.get(sku);
    const ro = ev.refs?.ro_id;
    let kind: PartKind | undefined = (sku && lastChosenBySku.get(sku)) || (ro && roKind.get(ro)) || undefined;
    if (!kind) { const k = kindOf(`${ev.summary ?? ""} ${(ev.data?.part_type as string) ?? ""}`); if (k !== "box") kind = k; }
    if (kind) {
      const b = [...bins.values()].find((x) => x.kind === kind && status(x.item) !== "ok") ?? [...bins.values()].find((x) => x.kind === kind);
      if (b) return b;
    }
    if (createIfMissing && sku) {
      const nb = makeBin({ sku, name: ev.summary?.split(":")[0] ?? sku, part_type: ev.summary ?? "", qty: 0, min_qty: 1, max_qty: 8 });
      bins.set(sku, nb); layoutFillers();
      return nb;
    }
    return undefined;
  }

  const queue: SalEvent[] = [];
  let nextAt = 0;
  function handleEvent(ev: SalEvent) { if (ev && typeof ev.type === "string") queue.push(ev); }

  function run(ev: SalEvent) {
    const d = ev.data ?? {};
    switch (ev.type) {
      case "inventory.checked": {
        flyTo(overview.pos, overview.tgt);
        scanSweep();
        toast(ev.summary ?? "Inventory checked", new THREE.Vector3(-2.3, 2.45, SHELF_Z + 0.4), { accent: "green" });
        break;
      }
      case "stock.low": {
        const b = binFor(ev, true);
        if (!b) break;
        if (typeof d.have === "number") b.item.qty = d.have as number;
        if (typeof d.need === "number") b.item.min_qty = Math.max(b.item.min_qty, d.need as number);
        refreshBin(b); b.pulse = 4; b.pulseColor.copy(b.item.qty <= 0 ? RED : AMBER);
        focusBin(b, 1.2);
        toast(ev.summary ?? "Stock low", b.group.position.clone().add(new THREE.Vector3(0, 0.42, 0.2)), { accent: b.item.qty <= 0 ? "red" : "amber" });
        screenFromInventory();
        break;
      }
      case "restock.planned": {
        const lines = (Array.isArray(d.lines) ? d.lines : []) as { sku?: string; qty?: number }[];
        let first: Bin | undefined;
        for (const l of lines) {
          const b = l.sku ? (bins.get(l.sku) ?? binFor({ type: "x", refs: { sku: l.sku }, summary: l.sku }, true)) : undefined;
          if (!b) continue;
          b.item.incoming_qty = (b.item.incoming_qty ?? 0) + (l.qty ?? 1);
          refreshBin(b); b.pulse = 2.5; b.pulseColor.copy(GREEN);
          first ??= b;
        }
        flyTo(new THREE.Vector3(-1.6, 2.4, 1.2), new THREE.Vector3(-2.3, 1.2, SHELF_Z));
        toast(ev.summary ?? "Restock planned", new THREE.Vector3(-2.3, 2.5, SHELF_Z + 0.4), { accent: "green", sub: ev.reason });
        break;
      }
      case "vendors.compared": {
        const ls = (Array.isArray(d.listings) ? d.listings : []) as Record<string, unknown>[];
        flyTo(counterView.pos, counterView.tgt);
        showCards(ls.length ? ls : [{ vendor: "Vendor A" }, { vendor: "Vendor B" }, { vendor: "Vendor C" }]);
        break;
      }
      case "part.rejected": rejectCard(ev); break;
      case "part.chosen": {
        const k = kindOf(`${ev.summary ?? ""}`);
        if (ev.refs?.ro_id && k !== "box") roKind.set(ev.refs.ro_id, k);
        if (ev.refs?.sku && k !== "box") lastChosenBySku.set(ev.refs.sku, k);
        if (!cards.length) { flyTo(counterView.pos, counterView.tgt); toast(ev.summary ?? "Part chosen", COUNTER.clone().add(new THREE.Vector3(0, 2.1, 0.2)), { accent: "green", sub: ev.reason }); }
        else chooseCard(ev);
        break;
      }
      case "order.placed": {
        const counterOrder = String(d.channel ?? "counter") === "counter";
        flyTo(receivingView.pos, receivingView.tgt);
        printLabel(String(ev.refs?.order_id ?? "ORDER").replace(/^gid:\/\/shopify\/Order\//, "#"));
        toast(ev.summary ?? "Order placed", COUNTER.clone().add(new THREE.Vector3(0.55, 1.5, 0.2)), { accent: "green" });
        if (counterOrder) vanTrip();
        else ping(COUNTER.clone().add(new THREE.Vector3(0.55, 1.3, 0.1)));
        break;
      }
      case "order.delivered": {
        flyTo(receivingView.pos, receivingView.tgt, 1.2);
        const box = parcelAt(RECEIVING.clone().add(new THREE.Vector3(0.2, 0, 0.3)));
        const incoming = [...bins.values()].filter((b) => (b.item.incoming_qty ?? 0) > 0);
        const target = binFor(ev);
        const targets = target && !incoming.includes(target) && ev.refs?.sku && !bins.has(ev.refs.sku) && incoming.length && !roKind.has(ev.refs?.ro_id ?? "") ? incoming : target ? [target] : incoming;
        toast(ev.summary ?? "Delivered", RECEIVING.clone().add(new THREE.Vector3(0, 1.1, 0.6)), { accent: "green" });
        animate(1.3, () => {}, () => {
          animate(0.4, (k) => box.scale.set(1, 1 - k * 0.3, 1));
          targets.forEach((b, i) => {
            const add = Math.max(1, b.item.incoming_qty ?? 1);
            animate(0.2 + i * 0.5, () => {}, () => partFlight(b, box.position.clone().add(new THREE.Vector3(0, 0.3, 0)), Math.min(4, add), () => {
              b.item.qty += add; b.item.incoming_qty = 0; refreshBin(b); b.pulse = 2; b.pulseColor.copy(GREEN); screenFromInventory();
            }));
          });
          if (targets[0]) animate(0.6, () => {}, () => focusBin(targets[0], 1.8));
          animate(6, () => {}, () => { box.visible = false; tempDispose(box); });
        });
        break;
      }
      case "statement.parsed": flyTo(counterView.pos, counterView.tgt); docScan(ev); break;
      case "escalation":
      case "identity.verified":
      case "approval.requested":
      case "approval.received": {
        flyTo(counterView.pos, counterView.tgt);
        const verified = ev.type === "identity.verified" || ev.type === "approval.received";
        if (verified) badge(ev.summary ?? "Verified", ev.reason);
        else toast(ev.summary ?? "Needs owner", COUNTER.clone().add(new THREE.Vector3(0.9, 2.0, 0.2)), { accent: "amber", sub: ev.reason, ttl: 5 });
        break;
      }
      case "chat.message": ping(COUNTER.clone().add(new THREE.Vector3(-0.8, 1.75, -0.1))); toast(ev.summary ?? "Message", COUNTER.clone().add(new THREE.Vector3(-0.8, 2.0, -0.1)), { accent: "green", ttl: 3 }); break;
      case "scorecard.built":
      case "rule.approved":
      case "rule.proposed":
      case "metrics.updated":
      case "sal.summary": {
        const rows: string[] = [];
        if (Array.isArray(d.per_vendor)) for (const v of d.per_vendor as Record<string, unknown>[]) rows.push(`${String(v.vendor_id).padEnd(11)} late ${(Number(v.late_rate) * 100).toFixed(1).padStart(5)}%  cores ${v.missed_core_credits ?? 0}`);
        if (ev.reason) rows.push(ev.reason);
        const ttl = ev.type === "rule.approved" ? `Rule ${ev.refs?.rule_id ?? ""} approved` : ev.type === "scorecard.built" ? "Vendor scorecard" : ev.type === "rule.proposed" ? "Rule proposed" : "Sal";
        drawScreen(ttl, [ev.summary ?? "", ...rows, ...(d.title ? [String(d.title)] : [])], ev.type === "rule.approved");
        if (ev.type !== "metrics.updated") flyTo(new THREE.Vector3(2.6, 2.4, -1.2), new THREE.Vector3(3.4, 2.5, -4.9), 1.4);
        break;
      }
      default: break;
    }
  }

  // ---------------------------------------------------------------- picking
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let hovered: Bin | null = null;
  let downAt: [number, number] | null = null;
  function pick(e: PointerEvent): Bin | null {
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hits = ray.intersectObjects([...bins.values()].map((b) => b.hit), false);
    return hits.length ? bins.get(hits[0].object.userData.sku as string) ?? null : null;
  }
  const onMove = (e: PointerEvent) => {
    const b = pick(e);
    if (b !== hovered) {
      hovered = b;
      renderer.domElement.style.cursor = b ? "pointer" : "";
      opts.onHover?.(b ? b.item.sku : null);
      if (b) {
        const st = status(b.item);
        hoverEl.innerHTML = `<b style="font-family:'JetBrains Mono',monospace">${escapeHtml(b.item.sku)}</b> · ${escapeHtml(b.item.name)}<br><span style="color:${st === "out" ? "#e5402e" : st === "low" ? "#f0a020" : "#9aa3ad"}">qty ${b.item.qty} · min ${b.item.min_qty} · max ${b.item.max_qty}${b.item.incoming_qty ? ` · <span style="color:#22c550">+${b.item.incoming_qty} incoming</span>` : ""}</span>`;
        hoverObj.position.copy(b.group.position).add(new THREE.Vector3(0, 0.45, 0.25));
      }
      hoverObj.visible = !!b;
    }
  };
  const onDown = (e: PointerEvent) => { downAt = [e.clientX, e.clientY]; };
  const onUp = (e: PointerEvent) => {
    if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5) return;
    const b = pick(e);
    opts.onSelect?.(b ? b.item.sku : null);
    if (b) { focusBin(b); b.pulse = 1; b.pulseColor.copy(GREEN); }
  };
  renderer.domElement.addEventListener("pointermove", onMove);
  renderer.domElement.addEventListener("pointerdown", onDown);
  renderer.domElement.addEventListener("pointerup", onUp);

  // ---------------------------------------------------------------- loop
  function resize() {
    const w = Math.max(1, container.clientWidth), h = Math.max(1, container.clientHeight);
    camera.aspect = w / h; camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
    labels.setSize(w, h);
    if (composer) {
      composer.setSize(w, h);
      const pr = renderer.getPixelRatio();
      gtao?.setSize(w * pr, h * pr);
      smaa?.setSize(w * pr, h * pr);
      bloom?.resolution.set(w, h);
    }
  }
  const ro = new ResizeObserver(() => resize()); ro.observe(container);

  let raf = 0;
  let disposed = false;
  const tick = () => {
    if (disposed) return;
    raf = requestAnimationFrame(tick);
    const dt = Math.min(0.05, clock.getDelta());
    now += dt;
    // event queue: one reaction every ~1.1s
    if (queue.length && now >= nextAt) { const ev = queue.shift()!; try { run(ev); } catch (err) { console.warn("[scene3d]", err); } nextAt = now + (queue.length > 6 ? 0.5 : 1.1); }
    for (let i = anims.length - 1; i >= 0; i--) {
      const a = anims[i];
      const k = Math.min(1, (now - a.t0) / a.dur);
      a.step(k);
      if (k >= 1) { anims.splice(i, 1); a.done?.(); }
    }
    // camera
    if (camAnim) {
      const k = Math.min(1, (now - camAnim.t0) / camAnim.dur), e = ease(k);
      camPos.lerpVectors(camAnim.fromP, camAnim.toP, e); camTgt.lerpVectors(camAnim.fromT, camAnim.toT, e);
      if (k >= 1) camAnim = null;
    } else if (now - lastFocusAt > 9 && home === overview) {
      lastFocusAt = now; camAnim = { fromP: camPos.clone(), fromT: camTgt.clone(), toP: overview.pos.clone(), toT: overview.tgt.clone(), t0: now, dur: 2.4 };
    }
    camera.position.copy(camPos);
    if (drift) { camera.position.x += Math.sin(now * 0.11) * 0.35; camera.position.y += Math.sin(now * 0.17) * 0.08; camera.position.z += Math.cos(now * 0.09) * 0.2; }
    camera.lookAt(camTgt);
    // bin pulses
    for (const b of bins.values()) {
      const st = status(b.item);
      const base = st === "out" ? 0.25 : st === "low" ? 0.12 : 0;
      if (b.pulse > 0) b.pulse -= dt;
      const p = b.pulse > 0 ? 0.5 + 0.5 * Math.sin(now * 7) : 0;
      const baseCol = st === "out" ? RED : AMBER;
      if (p > 0) { b.labelMat.emissive.copy(b.pulseColor); b.labelMat.emissiveIntensity = 0.15 + p * 0.9; }
      else { b.labelMat.emissive.copy(baseCol); b.labelMat.emissiveIntensity = base * (0.7 + 0.3 * Math.sin(now * 2.2)); }
    }
    ghostMat.opacity = 0.22 + 0.12 * Math.sin(now * 2.4);
    if (composer) composer.render(); else renderer.render(scene, camera);
    labels.render(scene, camera);
  };

  setInventory(DEMO);
  screenFromInventory();
  resize();
  tick();

  return {
    handleEvent,
    setInventory: (items) => { setInventory(items); screenFromInventory(); },
    setFocus: (t) => { home = t === "overview" ? overview : home; setFocus(t); },
    resize,
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      [...temp].forEach(tempDispose);
      clearCards();
      for (const b of bins.values()) freeBin(b);
      bins.clear();
      fillers.dispose();
      scene.traverse((o) => { const m = o as THREE.Mesh; if (m.isMesh && m.geometry) m.geometry.dispose(); });
      disposables.forEach((d) => d.dispose());
      composer?.dispose();
      gtao?.dispose(); bloom?.dispose(); smaa?.dispose();
      pmrem.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      labels.domElement.remove();
    },
  };
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
