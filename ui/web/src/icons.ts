// Line-art part drawings for B-Line tiles (no scraped photos). Same stroke language as the 3D shop.
const S = (body: string) =>
  `<svg viewBox="0 0 120 70" fill="none" stroke="#141414" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;

const ICONS: Record<string, string> = {
  o2_sensor: S(`<path d="M20 35h22"/><rect x="42" y="27" width="16" height="16" rx="2"/><path d="M58 31l6-3v14l-6-3"/><path d="M64 30h14v10H64"/><path d="M78 32h10v6H78"/><path d="M88 34h12"/><path d="M45 27v-6m5 6v-6m5 6v-6"/><path d="M20 35c-8 0-8 14-16 14"/>`),
  alternator: S(`<circle cx="58" cy="35" r="22"/><circle cx="58" cy="35" r="14"/><circle cx="58" cy="35" r="4"/><path d="M36 35h-8v-6h-6v12h6v-6"/><path d="M58 13v-5m0 54v-5m22-22h5"/><path d="M44 21l10 10m8 8l10 10m0-28L62 31m-8 8L44 49"/>`),
  starter: S(`<rect x="22" y="22" width="44" height="26" rx="4"/><rect x="66" y="28" width="18" height="14"/><path d="M84 35h14"/><circle cx="102" cy="35" r="4"/><rect x="30" y="12" width="26" height="10" rx="2"/>`),
  oil_filter: S(`<rect x="38" y="12" width="44" height="48" rx="6"/><path d="M38 22h44M38 50h44"/><path d="M46 12v-4h28v4"/><path d="M48 26v20m8-20v20m8-20v20m8-20v20"/>`),
  wiper: S(`<path d="M10 50Q60 20 110 30"/><path d="M14 54Q60 26 110 34"/><path d="M60 40l-4 18h8l-4-18"/><path d="M30 45l2 4m18-12l2 4m18-8l2 4m18-4l2 4"/>`),
  brake_cleaner: S(`<rect x="46" y="18" width="28" height="44" rx="4"/><path d="M50 18v-6h20v6"/><path d="M56 12V6h10v6"/><path d="M66 8h10"/><path d="M50 30h20M50 48h20"/><path d="M78 6l8-2m-8 4l9 2"/>`),
  generic: S(`<rect x="34" y="18" width="52" height="34" rx="3"/><path d="M34 30h52"/><path d="M50 18v12m20-12v12"/>`),
};

export function partIcon(kind: string) {
  return ICONS[kind] ?? ICONS.generic;
}

export function kindFor(text: string) {
  const t = text.toLowerCase();
  if (t.includes("o2") || t.includes("oxygen") || t.includes("36532")) return "o2_sensor";
  if (t.includes("alternator")) return "alternator";
  if (t.includes("starter")) return "starter";
  if (t.includes("filter") || t.startsWith("flt")) return "oil_filter";
  if (t.includes("wiper") || t.startsWith("wpr")) return "wiper";
  if (t.includes("clean") || t.startsWith("chm")) return "brake_cleaner";
  return "generic";
}
