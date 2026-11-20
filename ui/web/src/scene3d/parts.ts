import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { cardboard, pleats } from "./textures";

export type PartKind =
  | "oil_filter" | "o2_sensor" | "brake_pads" | "rotor" | "wiper" | "coil" | "belt" | "bulb"
  | "jug" | "aerosol" | "alternator" | "starter" | "air_filter" | "link" | "box";

export function kindOf(text: string): PartKind {
  const t = text.toLowerCase();
  if (/oil filter|oil_filter/.test(t)) return "oil_filter";
  if (/cabin|air filter|air_filter|engine air/.test(t)) return "air_filter";
  if (/\bo2\b|o2_|oxygen|air\/fuel|afr|lambda/.test(t)) return "o2_sensor";
  if (/rotor|disc/.test(t)) return "rotor";
  if (/brake cleaner|brakleen|cleaner|aerosol|spray/.test(t)) return "aerosol";
  if (/pad/.test(t)) return "brake_pads";
  if (/wiper/.test(t)) return "wiper";
  if (/coil|spark|plug|ignition/.test(t)) return "coil";
  if (/belt/.test(t)) return "belt";
  if (/bulb|lamp/.test(t)) return "bulb";
  if (/fluid|coolant|antifreeze|atf|motor oil/.test(t)) return "jug";
  if (/alternator/.test(t)) return "alternator";
  if (/starter/.test(t)) return "starter";
  if (/link|stabilizer|sway/.test(t)) return "link";
  if (/filter/.test(t)) return "oil_filter";
  return "box";
}

export const HEAVY: PartKind[] = ["alternator", "starter", "rotor", "jug"];

export interface PartModel {
  parts: { geo: THREE.BufferGeometry; mat: THREE.Material }[];
  /** footprint w (x), h (y), d (z) in meters */
  size: [number, number, number];
}

export class PartLibrary {
  mats: Record<string, THREE.Material>;
  private cache = new Map<PartKind, PartModel>();
  private disposables: { dispose(): void }[] = [];

  constructor() {
    const std = (p: THREE.MeshStandardMaterialParameters) => new THREE.MeshStandardMaterial(p);
    const phys = (p: THREE.MeshPhysicalMaterialParameters) => new THREE.MeshPhysicalMaterial(p);
    const cb = cardboard("PARTS");
    const pl = pleats();
    this.disposables.push(cb, pl);
    this.mats = {
      steel: std({ color: 0xb9bdc2, metalness: 1, roughness: 0.32 }),
      darkSteel: std({ color: 0x45484c, metalness: 0.85, roughness: 0.45 }),
      castIron: std({ color: 0x6a6b6c, metalness: 0.9, roughness: 0.5 }),
      alu: std({ color: 0xc4c8cc, metalness: 1, roughness: 0.4 }),
      rubber: std({ color: 0x151515, roughness: 0.92 }),
      friction: std({ color: 0x2c2a27, roughness: 0.97 }),
      blackPlastic: std({ color: 0x1c1d1f, roughness: 0.5 }),
      filterPaint: phys({ color: 0x23395e, metalness: 0.4, roughness: 0.35, clearcoat: 1, clearcoatRoughness: 0.15 }),
      blackPaint: phys({ color: 0x1a1a1a, metalness: 0.3, roughness: 0.4, clearcoat: 0.6 }),
      copper: std({ color: 0xb06a3a, metalness: 1, roughness: 0.35 }),
      hdpe: phys({ color: 0xe9e6dc, roughness: 0.55, sheen: 0.2 }),
      cap: std({ color: 0x2b2b2d, roughness: 0.6 }),
      can: std({ color: 0xd0d2d4, metalness: 0.9, roughness: 0.28 }),
      canBand: phys({ color: 0x31363c, metalness: 0.5, roughness: 0.35, clearcoat: 1 }),
      bulbBox: std({ color: 0xeeeeea, roughness: 0.7 }),
      cardboard: std({ map: cb, roughness: 0.85 }),
      pleats: std({ map: pl, roughness: 0.9 }),
    };
  }

  model(kind: PartKind): PartModel {
    let m = this.cache.get(kind);
    if (!m) { m = this.build(kind); this.cache.set(kind, m); }
    return m;
  }

  private build(kind: PartKind): PartModel {
    const M = this.mats;
    const parts: { geo: THREE.BufferGeometry; mat: THREE.Material }[] = [];
    const add = (mat: THREE.Material, ...geos: THREE.BufferGeometry[]) => {
      const list = geos.map((g) => {
        const n = g.index ? g.toNonIndexed() : g;
        // keep a common attribute set (position, normal, uv)
        for (const k of Object.keys(n.attributes)) if (!["position", "normal", "uv"].includes(k)) n.deleteAttribute(k);
        if (!n.attributes.uv) n.setAttribute("uv", new THREE.Float32BufferAttribute(new Float32Array(n.attributes.position.count * 2), 2));
        return n;
      });
      const merged = list.length === 1 ? list[0] : mergeGeometries(list, false)!;
      parts.push({ geo: merged, mat });
    };
    const cyl = (r1: number, r2: number, h: number, seg = 32) => new THREE.CylinderGeometry(r1, r2, h, seg);
    const at = (g: THREE.BufferGeometry, x: number, y: number, z: number, rx = 0, ry = 0, rz = 0) => {
      g.applyMatrix4(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(rx, ry, rz)));
      g.translate(x, y, z); return g;
    };
    const rbox = (w: number, h: number, d: number, r: number): THREE.BufferGeometry => new RoundedBoxGeometry(w, h, d, 3, r);
    let size: [number, number, number] = [0.2, 0.12, 0.15];
    const H = Math.PI / 2;
    switch (kind) {
      case "oil_filter": {
        const h = 0.088, r = 0.038;
        const body = new THREE.LatheGeometry([
          new THREE.Vector2(0.0, 0), new THREE.Vector2(r - 0.006, 0), new THREE.Vector2(r, 0.006),
          new THREE.Vector2(r, h - 0.01), new THREE.Vector2(r - 0.004, h - 0.002), new THREE.Vector2(r - 0.008, h),
        ], 40);
        add(M.filterPaint, body);
        add(M.darkSteel, at(cyl(0.033, 0.033, 0.004), 0, h + 0.001, 0));
        add(M.rubber, at(new THREE.TorusGeometry(0.027, 0.003, 8, 32), 0, h + 0.004, 0, H));
        add(M.steel, at(cyl(0.01, 0.01, 0.006, 16), 0, h + 0.004, 0));
        size = [0.084, 0.095, 0.084];
        break;
      }
      case "o2_sensor": {
        add(M.steel, at(cyl(0.013, 0.013, 0.014, 6), 0, 0.016, 0, 0, 0, H),
          at(cyl(0.009, 0.009, 0.03, 20), -0.022, 0.016, 0, 0, 0, H),
          at(cyl(0.0065, 0.006, 0.02, 16), -0.045, 0.016, 0, 0, 0, H));
        add(M.rubber, at(new THREE.TorusGeometry(0.028, 0.0028, 8, 40), 0.04, 0.004, 0, H),
          at(new THREE.TorusGeometry(0.024, 0.0028, 8, 40), 0.04, 0.009, 0, H));
        add(M.blackPlastic, at(rbox(0.024, 0.014, 0.018, 0.003), 0.07, 0.008, 0.012));
        size = [0.15, 0.035, 0.07];
        break;
      }
      case "brake_pads": {
        const outline = (w: number, h: number, bow: number) => {
          const s = new THREE.Shape();
          s.moveTo(-w, -h); s.quadraticCurveTo(0, -h - bow, w, -h);
          s.lineTo(w - 0.002, h); s.quadraticCurveTo(0, h + bow, -w + 0.002, h); s.closePath();
          return s;
        };
        const plate = (y: number) => at(new THREE.ExtrudeGeometry(outline(0.07, 0.022, 0.01), { depth: 0.005, bevelEnabled: false }), 0, y, 0, -H);
        const pad = (y: number) => at(new THREE.ExtrudeGeometry(outline(0.062, 0.018, 0.008), { depth: 0.011, bevelEnabled: false }), 0, y, 0, -H);
        add(M.darkSteel, plate(0), plate(0.034));
        add(M.friction, pad(0.005), pad(0.018));
        size = [0.15, 0.04, 0.07];
        break;
      }
      case "rotor": {
        add(M.castIron, at(cyl(0.14, 0.14, 0.024, 64), 0, 0.012, 0), at(cyl(0.085, 0.085, 0.05, 48), 0, 0.045, 0));
        add(M.darkSteel, at(cyl(0.035, 0.035, 0.052, 32), 0, 0.046, 0));
        size = [0.285, 0.075, 0.285];
        break;
      }
      case "wiper": {
        add(M.blackPlastic, at(rbox(0.55, 0.014, 0.022, 0.006), 0, 0.012, 0), at(rbox(0.06, 0.02, 0.026, 0.006), 0, 0.016, 0));
        add(M.rubber, at(new THREE.BoxGeometry(0.54, 0.006, 0.006), 0, 0.003, 0));
        size = [0.56, 0.026, 0.04];
        break;
      }
      case "coil": {
        add(M.blackPlastic, at(rbox(0.05, 0.05, 0.04, 0.006), 0, 0.15, 0), at(rbox(0.034, 0.022, 0.026, 0.004), 0.03, 0.16, 0));
        add(M.rubber, at(cyl(0.012, 0.011, 0.11, 20), 0, 0.07, 0), at(cyl(0.009, 0.009, 0.02, 16), 0, 0.01, 0));
        add(M.steel, at(cyl(0.006, 0.006, 0.012, 12), 0, 0.006, 0));
        size = [0.075, 0.18, 0.05];
        break;
      }
      case "belt": {
        const g = new THREE.TorusGeometry(0.095, 0.007, 8, 64); g.scale(1, 1, 0.5);
        add(M.rubber, at(g, 0, 0.004, 0, H));
        size = [0.21, 0.01, 0.21];
        break;
      }
      case "bulb": {
        add(M.bulbBox, at(rbox(0.05, 0.08, 0.05, 0.003), 0, 0.04, 0));
        add(M.canBand, at(new THREE.BoxGeometry(0.051, 0.02, 0.051), 0, 0.055, 0));
        size = [0.055, 0.082, 0.055];
        break;
      }
      case "jug": {
        add(M.hdpe, at(rbox(0.15, 0.22, 0.1, 0.02), 0, 0.11, 0), at(rbox(0.04, 0.05, 0.02, 0.008), 0.05, 0.235, 0));
        add(M.cap, at(cyl(0.02, 0.02, 0.025, 24), -0.04, 0.235, 0));
        add(M.canBand, at(new THREE.BoxGeometry(0.152, 0.09, 0.102), 0, 0.1, 0));
        size = [0.16, 0.25, 0.11];
        break;
      }
      case "aerosol": {
        add(M.can, at(cyl(0.033, 0.033, 0.18, 32), 0, 0.09, 0), at(new THREE.SphereGeometry(0.033, 24, 12, 0, Math.PI * 2, 0, H), 0, 0.18, 0));
        add(M.canBand, at(cyl(0.0335, 0.0335, 0.09, 32), 0, 0.085, 0));
        add(M.cap, at(cyl(0.022, 0.026, 0.035, 24), 0, 0.225, 0));
        size = [0.07, 0.245, 0.07];
        break;
      }
      case "alternator": {
        const ribs: THREE.BufferGeometry[] = [];
        for (let i = 0; i < 6; i++) ribs.push(at(cyl(0.072, 0.072, 0.006, 40), -0.035 + i * 0.014, 0.075, 0, 0, 0, H));
        add(M.alu, at(cyl(0.068, 0.068, 0.1, 40), 0, 0.075, 0, 0, 0, H), ...ribs,
          at(rbox(0.03, 0.03, 0.05, 0.006), -0.01, 0.145, 0.045), at(rbox(0.03, 0.03, 0.05, 0.006), -0.01, 0.015, -0.045));
        add(M.copper, at(cyl(0.06, 0.06, 0.07, 40), 0.004, 0.075, 0, 0, 0, H));
        add(M.darkSteel, at(cyl(0.028, 0.028, 0.03, 32), 0.07, 0.075, 0, 0, 0, H), at(cyl(0.06, 0.06, 0.02, 40), -0.06, 0.075, 0, 0, 0, H));
        size = [0.17, 0.16, 0.15];
        break;
      }
      case "starter": {
        add(M.blackPaint, at(cyl(0.045, 0.045, 0.14, 36), -0.04, 0.05, 0, 0, 0, H));
        add(M.steel, at(cyl(0.025, 0.025, 0.09, 28), 0.0, 0.11, 0, 0, 0, H));
        add(M.alu, at(cyl(0.04, 0.045, 0.06, 32), 0.06, 0.05, 0, 0, 0, H), at(rbox(0.02, 0.09, 0.1, 0.006), 0.035, 0.05, 0));
        add(M.copper, at(cyl(0.006, 0.006, 0.02, 12), 0.03, 0.135, 0));
        size = [0.24, 0.14, 0.11];
        break;
      }
      case "air_filter": {
        add(M.rubber, at(rbox(0.26, 0.012, 0.2, 0.005), 0, 0.006, 0));
        add(M.pleats, at(new THREE.BoxGeometry(0.235, 0.045, 0.175), 0, 0.03, 0));
        size = [0.26, 0.055, 0.2];
        break;
      }
      case "link": {
        add(M.steel, at(cyl(0.006, 0.006, 0.2, 16), 0, 0.016, 0, 0, 0, H));
        add(M.blackPaint, at(new THREE.SphereGeometry(0.016, 20, 14), -0.1, 0.016, 0), at(new THREE.SphereGeometry(0.016, 20, 14), 0.1, 0.016, 0));
        add(M.rubber, at(cyl(0.012, 0.012, 0.02, 16), -0.1, 0.035, 0), at(cyl(0.012, 0.012, 0.02, 16), 0.1, 0.035, 0));
        size = [0.24, 0.05, 0.04];
        break;
      }
      default: {
        add(M.cardboard, at(rbox(0.2, 0.12, 0.15, 0.004), 0, 0.06, 0));
        size = [0.21, 0.125, 0.16];
      }
    }
    return { parts, size };
  }

  dispose() {
    this.cache.forEach((m) => m.parts.forEach((p) => p.geo.dispose()));
    Object.values(this.mats).forEach((m) => m.dispose());
    this.disposables.forEach((d) => d.dispose());
  }
}
