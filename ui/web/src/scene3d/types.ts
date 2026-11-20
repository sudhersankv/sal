/** Public types for Sal's parts-room scene. SalEvent mirrors contracts/events.schema.json. */
export interface SalEvent {
  id?: string;
  run_id?: string;
  ts?: string;
  day?: string;
  type: string;
  actor?: string;
  summary?: string;
  reason?: string;
  sources?: { name: string; ref?: string; url?: string }[];
  money?: { wholesale?: number; retail?: number; saved?: number; currency?: string };
  refs?: Record<string, string | undefined>;
  data?: Record<string, unknown>;
}

/** One inventory row (GET /api/inventory). part_type is free text; it is matched by keyword
 *  (oil filter, oxygen/o2 sensor, brake pad, rotor, wiper, coil, spark, belt, bulb, fluid/coolant,
 *  alternator, starter, air filter, ...) to pick a 3D part model. */
export interface InventoryItem {
  sku: string;
  name: string;
  part_type: string;
  qty: number;
  min_qty: number;
  max_qty: number;
  incoming_qty?: number;
}

/** 'shelf:<part_type>' focuses the bin holding that part type (keyword match, e.g. 'shelf:oil filter'). */
export type FocusTarget = "overview" | "counter" | "receiving" | `shelf:${string}`;

export interface ShopSceneOptions {
  /** 'high' (default): soft shadows + SSAO + bloom + SMAA. 'low': no post-processing. */
  quality?: "high" | "low";
  /** Slow idle camera drift (default true). */
  autoDrift?: boolean;
  /** Called when the user clicks a bin (sku), or null when clicking empty space. */
  onSelect?: (sku: string | null) => void;
  /** Called when the hovered bin changes. */
  onHover?: (sku: string | null) => void;
}

export interface ShopScene {
  handleEvent(ev: SalEvent): void;
  /** Replace the whole inventory; bins are created/updated by sku. Call again any time. */
  setInventory(items: InventoryItem[]): void;
  setFocus(target: FocusTarget): void;
  resize(): void;
  dispose(): void;
}
