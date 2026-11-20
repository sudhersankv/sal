// Mirrors contracts/events.schema.json (lead-owned).
export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export const DAYS: Day[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export type Source = { name: string; ref?: string; url?: string };

export type SalEvent = {
  id: string;
  run_id: string;
  ts: string;
  day: Day;
  type: string;
  actor: "sal" | "tech" | "owner" | "car_owner" | "vendor" | "system";
  summary: string;
  reason?: string;
  sources?: Source[];
  money?: { wholesale?: number; retail?: number; saved?: number; currency?: "USD" };
  refs?: Record<string, unknown>;
  data?: Record<string, unknown>;
};

export type Listing = {
  vendor_id: string;
  vendor?: string;
  brand: string;
  sku: string;
  price: number;
  eta_minutes?: number;
  verdict?: string;
  score?: number;
};
