/** Public types for the realistic shop scene. Mirrors contracts/events.schema.json. */
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

export type FocusTarget =
  | "overview" | "bay1" | "bay2" | "bay3" | "bay4"
  | "shelf" | "counter" | "office" | "door";

export interface ShopSceneOptions {
  /** 'high' (default): shadows + SSAO + bloom + SMAA. 'low': no post-processing, cheaper shadows. */
  quality?: "high" | "low";
  /** Slow idle camera drift (default true). */
  autoDrift?: boolean;
}

export interface ShopScene {
  handleEvent(ev: SalEvent): void;
  setFocus(target: FocusTarget): void;
  resize(): void;
  dispose(): void;
}
