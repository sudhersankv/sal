import "@fontsource/inter/300.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter-tight/300.css";
import "@fontsource/inter-tight/400.css";
import "@fontsource/inter-tight/500.css";
import "@fontsource/inter-tight/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./style.css";

import fixtureRaw from "../../fixtures/sample_week.jsonl?raw";
import { kindFor, partIcon } from "./icons";
import { ShopScene } from "./scene";
import { DAYS, type Day, type Listing, type SalEvent } from "./types";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const usd = (n: number, d = 0) => `$${n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const params = new URLSearchParams(location.search);

// ------------------------------------------------------------------ state
const scene = new ShopScene($("scene") as HTMLCanvasElement, $("labels"));
const seen = new Set<string>();
const applied: SalEvent[] = [];
let mode: "live" | "replay" = "live";
let log: SalEvent[] = [];
let cursor = 0;
let playing = true;
let speed = Number(params.get("speed") ?? 1.5) || 1.5;
let timer: number | undefined;
let currentDay: Day | null = null;
let instant = false;

// ------------------------------------------------------------------ top bar
const daysEl = $("days");
DAYS.forEach((d) => {
  const b = document.createElement("button");
  b.className = "day";
  b.dataset.day = d;
  b.textContent = d.toUpperCase();
  b.onclick = () => seekDay(d);
  daysEl.appendChild(b);
});
function paintDays() {
  const has = new Set((mode === "replay" ? log : applied).map((e) => e.day));
  const idx = currentDay ? DAYS.indexOf(currentDay) : -1;
  daysEl.querySelectorAll<HTMLButtonElement>(".day").forEach((b) => {
    const i = DAYS.indexOf(b.dataset.day as Day);
    b.classList.toggle("has", has.has(b.dataset.day as Day));
    b.classList.toggle("done", i < idx && has.has(b.dataset.day as Day));
    b.classList.toggle("now", i === idx);
  });
}

const SPEEDS = [0.75, 1, 1.5, 2, 4];
function paintSpeeds() {
  const el = $("speeds");
  el.innerHTML = "";
  for (const s of SPEEDS) {
    const b = document.createElement("button");
    b.textContent = `${s}×`;
    b.className = s === speed ? "on" : "";
    b.onclick = () => { speed = s; paintSpeeds(); };
    el.appendChild(b);
  }
}
paintSpeeds();
$("play").onclick = () => togglePlay();
$("next").onclick = () => nextDay();

function togglePlay(force?: boolean) {
  playing = force ?? !playing;
  $("play").textContent = playing ? "❚❚" : "▶";
  if (playing) schedule();
  else clearTimeout(timer);
}

function setMode(m: "live" | "replay", label?: string) {
  mode = m;
  const el = $("mode");
  el.classList.toggle("live", m === "live");
  $("modeText").textContent = m === "live" ? "LIVE" : "REPLAY";
  el.title = label ?? "";
  $("replayctl").style.display = m === "replay" ? "" : "none";
}

function clock(ev: SalEvent) {
  const t = ev.ts.slice(11, 16);
  $("clock").textContent = `${ev.day.toUpperCase()} ${ev.ts.slice(5, 10).replace("-", "/")} ${t}`;
}

let toastTimer: number | undefined;
function toast(text: string, sal = false) {
  const el = $("toast");
  el.textContent = text;
  el.className = `toast show${sal ? " sal" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (el.className = "toast"), 2600);
}

// ------------------------------------------------------------------ timeline
const trail = $("trail");
const dayGroups = new Map<Day, HTMLElement>();
const pendingButtons = new Map<string, HTMLButtonElement>();
const TYPE_LABEL: Record<string, string> = {
  "repair_order.created": "repair order", "part.identified": "part identified", "context.retrieved": "context",
  "vendors.compared": "vendors compared", "part.rejected": "rejected", "part.chosen": "chosen", "quote.sent": "quote sent",
  "approval.requested": "approval asked", "approval.received": "approved", "order.placed": "order placed",
  "order.delivered": "delivered", "payment.recorded": "payment", "inventory.checked": "inventory", "stock.low": "stock low",
  "restock.planned": "restock plan", "statement.parsed": "statement parsed", "identity.verified": "identity verified",
  escalation: "escalation", "scorecard.built": "scorecard", "rule.proposed": "rule proposed", "rule.approved": "rule approved",
  "memory.saved": "memory", "gate.enabled": "gate on", "metrics.updated": "metrics", "sal.summary": "summary", error: "error",
};
const ACTOR: Record<string, string> = { sal: "Sal", tech: "Tech", owner: "Owner", car_owner: "Car owner", vendor: "Vendor", system: "System" };

function dayGroup(day: Day) {
  let g = dayGroups.get(day);
  if (!g) {
    const wrap = document.createElement("div");
    const ex = applied.find((e) => e.day === day);
    wrap.innerHTML = `<div class="daysep">${day.toUpperCase()} ${ex ? ex.ts.slice(5, 10).replace("-", "/") : ""}</div>`;
    g = document.createElement("div");
    g.style.cssText = "display:flex;flex-direction:column;gap:8px";
    wrap.appendChild(g);
    trail.prepend(wrap);
    dayGroups.set(day, g);
  }
  return g;
}

function sourceChips(ev: SalEvent) {
  return (ev.sources ?? []).map((s) => {
    const ref = s.ref ? `<i>${esc(s.ref.length > 26 ? s.ref.slice(0, 25) + "…" : s.ref)}</i>` : "";
    const inner = `${esc(s.name)}${ref}`;
    return s.url ? `<a class="src" href="${esc(s.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${inner}</a>` : `<span class="src">${inner}</span>`;
  }).join("");
}

function moneyHtml(ev: SalEvent) {
  const m = ev.money;
  if (!m) return "";
  const parts: string[] = [];
  if (m.wholesale != null && m.retail != null) parts.push(`${usd(m.wholesale)} → ${usd(m.retail)}`);
  else if (m.wholesale != null) parts.push(usd(m.wholesale));
  else if (m.retail != null) parts.push(usd(m.retail));
  if (m.saved) parts.push(`<span class="s">+${usd(m.saved, m.saved % 1 ? 2 : 0)} saved</span>`);
  return parts.length ? `<span class="money">${parts.join(" · ")}</span>` : "";
}

function approveLabel(ev: SalEvent) {
  const a = String(ev.data?.action ?? "");
  if (a === "approve_rule" || ev.type === "rule.proposed") return `Approve rule ${ev.refs?.rule_id ?? ""}`.trim();
  if (a === "send_dispute") return "Approve dispute";
  if (ev.money?.wholesale) return `Approve ${usd(ev.money.wholesale)} order`;
  return "Approve";
}
function needsOwner(ev: SalEvent) {
  return (ev.type === "escalation" || ev.type === "rule.proposed") && (ev.data?.needs === "owner" || ev.data?.action || ev.type === "rule.proposed");
}
function pendingKey(ev: SalEvent) {
  const r = ev.refs ?? {};
  return String(r.rule_id ?? r.escalation_id ?? r.ro_id ?? ev.id);
}

function addCard(ev: SalEvent) {
  const card = document.createElement("div");
  const sal = ev.actor === "sal";
  card.className = `card${sal ? " sal" : ""}${instant ? "" : " fresh"}`;
  if (instant) card.style.animation = "none";
  const adminUrl = (ev.data?.admin_url as string | undefined) ?? (ev.sources ?? []).find((s) => s.name === "Shopify" && s.url)?.url;
  const isShopify = ev.type === "order.placed" && (ev.data?.channel === "shopify" || !!adminUrl);
  card.innerHTML = `
    <div class="meta"><span>${esc(ev.ts.slice(11, 16))}</span><span class="type">${esc(TYPE_LABEL[ev.type] ?? ev.type)}</span><span class="actor">${esc(ACTOR[ev.actor] ?? ev.actor)}</span></div>
    <div class="sum">${esc(ev.summary)}</div>
    ${ev.reason ? `<div class="why">${esc(ev.reason)}</div>` : ""}
    <div class="row">${sourceChips(ev)}${moneyHtml(ev)}</div>
    ${isShopify && adminUrl ? `<div class="act"><a class="ext" href="${esc(adminUrl)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Open in Shopify admin ↗</a>${ev.data?.fixture ? '<span class="muted mono" style="font-size:10px">fixture link</span>' : ""}</div>` : ""}
    <div class="detail">${esc(JSON.stringify({ refs: ev.refs, data: ev.data }, null, 2))}</div>`;
  if (needsOwner(ev)) {
    const act = document.createElement("div");
    act.className = "act";
    act.innerHTML = `<span class="needs">NEEDS OWNER</span>`;
    const btn = document.createElement("button");
    btn.className = "btn approve";
    btn.textContent = approveLabel(ev);
    btn.onclick = (e) => { e.stopPropagation(); approve(ev, btn); };
    act.appendChild(btn);
    card.appendChild(act);
    pendingButtons.set(pendingKey(ev), btn);
  }
  card.onclick = () => {
    if (isShopify && adminUrl) window.open(adminUrl, "_blank", "noopener");
    else card.classList.toggle("open");
  };
  dayGroup(ev.day).prepend(card);
  if (!instant) {
    setTimeout(() => card.classList.remove("fresh"), 2500);
    trail.scrollTo({ top: 0, behavior: "smooth" });
  } else card.classList.remove("fresh");
  $("trailCount").textContent = `${applied.length} events`;

  // resolve owner buttons when the approval lands
  if (ev.type === "approval.received" || ev.type === "rule.approved" || ev.type === "identity.verified") {
    const btn = pendingButtons.get(pendingKey(ev));
    if (btn && ev.type !== "identity.verified") { btn.disabled = true; btn.textContent = "Approved by owner ✓"; pendingButtons.delete(pendingKey(ev)); }
  }
}

async function approve(ev: SalEvent, btn: HTMLButtonElement) {
  btn.disabled = true;
  btn.textContent = "Sending…";
  const body = { event_id: ev.id, action: ev.data?.action ?? (ev.type === "rule.proposed" ? "approve_rule" : "approve_order"), ...ev.refs };
  try {
    const r = await fetch("/sim/approve", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (r.ok && j.ok !== false) { btn.textContent = "Approved ✓"; toast("Owner approval sent to Sal", true); }
    else if (mode === "replay") { btn.textContent = "Approved ✓ (replay)"; }
    else { btn.disabled = false; btn.textContent = "Sim offline · retry"; }
  } catch {
    if (mode === "replay") btn.textContent = "Approved ✓ (replay)";
    else { btn.disabled = false; btn.textContent = "Server offline · retry"; }
  }
}

// ------------------------------------------------------------------ meters
type Meters = { margin: number | null; saved: number; ontime: number | null; orders: number; escalations: number; variant: string; compare?: { off?: { on_time_pct?: number }; on?: { on_time_pct?: number } } };
function computeMeters(evs: SalEvent[]): Meters {
  let wholesale = 0, retail = 0, saved = 0, orders = 0, esc = 0, delivered = 0, late = 0, variant = "control";
  let metrics: Record<string, unknown> | null = null;
  for (const e of evs) {
    const m = e.money ?? {}, d = e.data ?? {};
    if (e.type === "order.placed") { orders++; wholesale += m.wholesale ?? 0; retail += m.retail ?? 0; saved += m.saved ?? 0; }
    if (e.type === "escalation") { esc++; if (d.kind === "dispute_drafted") saved += m.saved ?? 0; }
    if (e.type === "order.delivered") { delivered++; if (d.late) late++; }
    if (e.type === "gate.enabled" && d.value !== false) variant = String(d.gate ?? "routing_v2");
    if (e.type === "metrics.updated") metrics = d;
  }
  const out: Meters = { margin: retail ? (100 * (retail - wholesale)) / retail : null, saved, ontime: delivered ? (100 * (delivered - late)) / delivered : null, orders, escalations: esc, variant };
  if (metrics) {
    if (metrics.margin_pct != null) out.margin = Number(metrics.margin_pct);
    if (metrics.saved != null) out.saved = Math.max(out.saved, Number(metrics.saved));
    if (metrics.on_time_pct != null) out.ontime = Number(metrics.on_time_pct);
    if (metrics.orders != null) out.orders = Math.max(orders, Number(metrics.orders));
    if (metrics.escalations != null) out.escalations = Math.max(esc, Number(metrics.escalations));
    if (metrics.variant) out.variant = String(metrics.variant);
    if (metrics.compare) out.compare = metrics.compare as Meters["compare"];
  }
  return out;
}

const meterEls: Record<string, { v: HTMLElement; cur: number | null; fmt: (n: number) => string; wrap: HTMLElement }> = {};
function buildMeters() {
  const root = $("meters");
  const defs: [string, string, string, (n: number) => string][] = [
    ["margin", "PARTS MARGIN", "target ≥ 45%", (n) => `${n.toFixed(0)}<small>%</small>`],
    ["saved", "SAVED / RECOVERED", "this week", (n) => `$${n.toFixed(0)}`],
    ["ontime", "ON-TIME", "deliveries", (n) => `${n.toFixed(n % 1 ? 1 : 0)}<small>%</small>`],
    ["orders", "ORDERS", "placed by Sal", (n) => `${n.toFixed(0)}`],
    ["escalations", "ESCALATIONS", "to owner", (n) => `${n.toFixed(0)}`],
  ];
  for (const [k, label, hint, fmt] of defs) {
    const w = document.createElement("div");
    w.className = "meter";
    w.innerHTML = `<div class="k">${label}<i>${hint}</i></div><div class="v">—</div>`;
    root.appendChild(w);
    meterEls[k] = { v: w.querySelector(".v")!, cur: null, fmt, wrap: w };
  }
  const v = document.createElement("div");
  v.className = "meter variant";
  v.id = "variantMeter";
  v.innerHTML = `<div class="k">POLICY VARIANT<i>Statsig</i></div><div id="variantBody"></div>`;
  root.appendChild(v);
}
buildMeters();

function tick(key: string, target: number | null) {
  const m = meterEls[key];
  if (target == null) { m.v.innerHTML = "—"; m.cur = null; return; }
  const from = m.cur ?? 0;
  if (m.cur === target) return;
  m.cur = target;
  if (instant) { m.v.innerHTML = m.fmt(target); return; }
  m.wrap.classList.add("pulse");
  setTimeout(() => m.wrap.classList.remove("pulse"), 700);
  const t0 = performance.now(), dur = 900;
  const step = (now: number) => {
    if (m.cur !== target) return;
    const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    m.v.innerHTML = m.fmt(from + (target - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function paintMeters() {
  const m = computeMeters(applied);
  tick("margin", m.margin);
  tick("saved", m.saved);
  tick("ontime", m.ontime);
  tick("orders", m.orders);
  tick("escalations", m.escalations);
  const on = m.variant !== "control";
  const cmp = m.compare ? `<div class="cmpbar">gate OFF <b>${m.compare.off?.on_time_pct ?? "—"}%</b> · ON <b>${m.compare.on?.on_time_pct ?? "—"}%</b> on-time</div>` : `<div class="cmpbar">sal_vendor_routing_v2</div>`;
  $("variantBody").innerHTML = `<div class="variant"><span class="badge${on ? " on" : ""}"><span class="led"></span>${esc(on ? m.variant : "control")}</span>${cmp}</div>`;
}

// ------------------------------------------------------------------ strip: parts tiles + vendor comparison
type Tile = { key: string; label: string; fit: string; kind: string; qty?: string; flag?: string; low?: boolean };
const tiles = new Map<string, Tile>();
let listings: (Listing & { state?: "rejected" | "chosen"; why?: string })[] = [];
let stripMode: "parts" | "compare" = "parts";
const shownTiles = new Set<string>();

function upsertTile(t: Tile) {
  tiles.set(t.key, { ...(tiles.get(t.key) ?? {}), ...t });
}
function paintStrip() {
  const body = $("stripBody");
  if (stripMode === "compare" && listings.length) {
    $("stripTitle").textContent = "VENDOR COMPARISON";
    $("stripSub").textContent = `${listings.length} listings · SIE match`;
    body.innerHTML = `<table class="cmp"><thead><tr><th>VENDOR</th><th>BRAND</th><th>SKU</th><th>PRICE</th><th>ETA</th><th>MATCH</th><th>DECISION</th></tr></thead><tbody>${listings.map((l) => `
      <tr class="${l.state === "rejected" ? "rej" : l.state === "chosen" ? "win" : ""}">
        <td>${esc(l.vendor ?? l.vendor_id)}</td><td class="br">${esc(l.brand)}</td><td class="m">${esc(l.sku)}</td>
        <td class="m pr">${usd(l.price)}</td><td class="m">${fmtEta(l.eta_minutes)}</td>
        <td class="m">${esc(l.verdict ?? "")}${l.score != null ? ` ${l.score.toFixed(2)}` : ""}</td>
        <td>${l.state ? `<span class="chip-why${l.state === "chosen" ? " win" : ""}" title="${esc(l.why)}">${esc(l.state === "chosen" ? "chosen · " + (l.why ?? "") : l.why ?? "rejected")}</span>` : '<span class="muted mono" style="font-size:11px">…</span>'}</td>
      </tr>`).join("")}</tbody></table>`;
    return;
  }
  $("stripTitle").textContent = "PARTS";
  $("stripSub").textContent = tiles.size ? `${tiles.size} parts in play` : "waiting for work";
  body.innerHTML = `<div class="tiles">${[...tiles.values()].reverse().map((t) => `
    <div class="tile${t.low ? " low" : ""}${shownTiles.has(t.key) || instant ? "" : " new"}">
      <div><div class="pn">${esc(t.label)}</div><div class="fit">${esc(t.fit)}</div></div>
      ${t.flag ? `<span class="flag">${esc(t.flag)}</span>` : ""}
      ${partIcon(t.kind)}
      <div class="qty">${t.qty ?? ""}</div>
    </div>`).join("")}</div>`;
  for (const k of tiles.keys()) shownTiles.add(k);
}
function fmtEta(m?: number) {
  if (m == null) return "";
  if (m >= 1440) return `${Math.round(m / 1440)}d`;
  if (m >= 60) return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}`;
  return `${m}m`;
}

// vendor overlay cards in the 3D stage
const overlay = $("vendorOverlay");
let vcardsEl: HTMLElement | null = null;
function showVendorCards() {
  overlay.innerHTML = "";
  if (instant) { vcardsEl = null; return; }
  vcardsEl = document.createElement("div");
  vcardsEl.className = "vcards";
  vcardsEl.innerHTML = listings.slice(0, 5).map((l, i) => `
    <div class="vcard" data-sku="${esc(l.sku)}" style="animation-delay:${i * 120}ms">
      <div class="v">${esc((l.vendor ?? l.vendor_id).replace(/ (Auto Supply|Parts Co\.|Online)$/, ""))}</div>
      <div class="b">${esc(l.brand)}</div>
      <div class="p">${usd(l.price)}</div>
      <div class="e">ETA ${fmtEta(l.eta_minutes)} · ${esc(l.verdict ?? "")}</div>
      <span class="why"></span>
    </div>`).join("");
  overlay.appendChild(vcardsEl);
}
function vcard(sku: string) {
  return vcardsEl?.querySelector<HTMLElement>(`.vcard[data-sku="${CSS.escape(sku)}"]`) ?? null;
}
function anchorOverlay() {
  if (vcardsEl) {
    const p = scene.project(scene.counterPos.clone().setZ(6));
    const stage = $("stage");
    const w = vcardsEl.offsetWidth;
    const x = Math.max(w / 2 + 16, Math.min(stage.clientWidth - w / 2 - 16, p.x));
    vcardsEl.style.left = `${x}px`;
    vcardsEl.style.top = `${Math.min(stage.clientHeight - vcardsEl.offsetHeight - 64, p.y + 24)}px`;
  }
  requestAnimationFrame(anchorOverlay);
}
requestAnimationFrame(anchorOverlay);

function stripEvent(ev: SalEvent) {
  const r = ev.refs ?? {}, d = ev.data ?? {};
  switch (ev.type) {
    case "part.identified": {
      const key = String(r.part_no ?? ev.id);
      upsertTile({ key, label: key, fit: `${d.year ?? ""} ${d.make ?? ""} ${d.model ?? ""} ${d.engine_l ? d.engine_l + "L" : ""}`.trim(), kind: kindFor(`${d.part_type ?? ""} ${key}`), flag: String(d.position ?? "needed").toUpperCase() });
      stripMode = "parts";
      break;
    }
    case "vendors.compared":
      listings = ((d.listings as Listing[]) ?? []).map((l) => ({ ...l }));
      stripMode = "compare";
      showVendorCards();
      break;
    case "part.rejected": {
      const l = listings.find((x) => x.sku === r.sku);
      const why = ev.reason ?? ev.summary;
      if (l) { l.state = "rejected"; l.why = shortWhy(why); }
      const c = r.sku ? vcard(String(r.sku)) : null;
      if (c) {
        c.querySelector(".why")!.textContent = shortWhy(why);
        c.classList.add("rejecting");
        setTimeout(() => c.classList.add("rejected"), 1300);
      }
      break;
    }
    case "part.chosen": {
      const l = listings.find((x) => x.sku === r.sku);
      if (l) { l.state = "chosen"; l.why = shortWhy(ev.reason ?? ""); }
      const c = r.sku ? vcard(String(r.sku)) : null;
      if (c) { c.classList.add("chosen"); c.querySelector(".why")!.textContent = "chosen"; }
      const key = String(r.part_no ?? [...tiles.keys()].pop() ?? r.sku);
      const existing = tiles.get(key);
      if (existing && r.ro_id && listings.some((x) => x.sku === r.sku)) upsertTile({ ...existing, qty: `${usd(ev.money?.wholesale ?? 0)}<small>${esc(String(r.sku))}</small>`, flag: "CHOSEN" });
      else upsertTile({ key: String(r.sku ?? ev.id), label: String(r.sku ?? ""), fit: ev.summary.split("@")[0].trim(), kind: kindFor(ev.summary), qty: `${usd(ev.money?.wholesale ?? 0)}`, flag: "CHOSEN" });
      if (!listings.some((x) => x.sku === r.sku)) stripMode = "parts";
      break;
    }
    case "order.placed":
      if (vcardsEl) { const el = vcardsEl; setTimeout(() => { el.style.transition = "opacity .8s"; el.style.opacity = "0"; setTimeout(() => el.remove(), 900); }, 1800); vcardsEl = null; }
      break;
    case "order.delivered": {
      for (const t of tiles.values()) if (t.flag === "CHOSEN") t.flag = "DELIVERED";
      stripMode = "parts";
      break;
    }
    case "stock.low": {
      const sku = String(r.sku ?? ev.id);
      upsertTile({ key: sku, label: sku, fit: ev.summary.split(":")[0], kind: kindFor(`${sku} ${ev.summary}`), qty: `${d.have ?? 0}<small>/ need ${d.need ?? "?"}</small>`, flag: "LOW", low: true });
      stripMode = "parts";
      break;
    }
    case "restock.planned":
      for (const ln of (d.lines as { sku: string; qty: number }[]) ?? []) {
        const t = tiles.get(ln.sku);
        if (t) upsertTile({ ...t, flag: `+${ln.qty}` });
        else upsertTile({ key: ln.sku, label: ln.sku, fit: "bundle to free shipping (R6)", kind: kindFor(ln.sku), qty: `+${ln.qty}`, flag: "ADD" });
      }
      break;
  }
  if (ev.type === "order.placed" && ev.data?.channel === "shopify") {
    for (const t of tiles.values()) if (t.low) { t.low = false; t.flag = "ORDERED"; }
  }
}
function shortWhy(s: string) {
  const m = s.match(/^(R\d+)[^;:,]*[;:,]?\s*(.*)$/);
  const t = m ? `${m[1]} · ${m[2] || s}` : s;
  return t.length > 54 ? t.slice(0, 52) + "…" : t;
}

// ------------------------------------------------------------------ apply
function applyEvent(ev: SalEvent, isInstant = false) {
  if (seen.has(ev.id)) return;
  seen.add(ev.id);
  instant = isInstant;
  if (ev.day !== currentDay) {
    if (currentDay && !isInstant) scene.onDay(ev.day);
    if (!isInstant && currentDay) { listings = []; stripMode = "parts"; overlay.innerHTML = ""; vcardsEl = null; }
    currentDay = ev.day;
  }
  applied.push(ev);
  clock(ev);
  addCard(ev);
  stripEvent(ev);
  paintStrip();
  paintMeters();
  paintDays();
  scene.handle(ev, isInstant);
  if (isInstant) scene.finishAll();
  if (!isInstant && (ev.actor === "sal" || ev.type === "escalation")) toast(ev.summary, ev.actor === "sal");
  instant = false;
}

// ------------------------------------------------------------------ replay player
function delayFor(prev: SalEvent | undefined, ev: SalEvent) {
  if (!prev) return 400;
  let base = prev.day !== ev.day ? 3400 : 1500;
  if (prev.type === "vendors.compared") base += 1200;
  if (prev.type === "repair_order.created") base += 1800;
  if (prev.type === "order.placed" && prev.data?.channel !== "shopify") base += 1400;
  if (prev.type === "statement.parsed" || prev.type === "rule.proposed") base += 1000;
  return base / speed;
}
function schedule() {
  clearTimeout(timer);
  if (mode !== "replay" || !playing || cursor >= log.length) {
    if (mode === "replay" && cursor >= log.length) $("play").textContent = "▶";
    return;
  }
  timer = window.setTimeout(() => {
    applyEvent(log[cursor]);
    cursor++;
    schedule();
  }, delayFor(log[cursor - 1], log[cursor]));
}

function seekDay(day: Day) {
  if (mode !== "replay") { toast("Day jump works in replay; live follows the sim"); return; }
  const idx = log.findIndex((e) => DAYS.indexOf(e.day) >= DAYS.indexOf(day));
  if (idx < 0) return;
  if (idx < cursor) {
    const u = new URL(location.href);
    u.searchParams.set("from", day);
    location.href = u.toString();
    return;
  }
  clearTimeout(timer);
  while (cursor < idx) applyEvent(log[cursor++], true);
  scene.onDay(day);
  togglePlay(true);
}
async function nextDay() {
  if (mode === "replay") {
    const cur = currentDay ? DAYS.indexOf(currentDay) : -1;
    const nxt = log.slice(cursor).find((e) => DAYS.indexOf(e.day) > cur);
    if (nxt) seekDay(nxt.day);
    else toast("End of the recorded week");
    return;
  }
  const btn = $("next") as HTMLButtonElement;
  btn.disabled = true;
  try {
    const r = await fetch("/sim/next", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    const j = await r.json().catch(() => ({}));
    toast(r.ok ? "Sim advancing to the next day" : j.offline ? "Sim offline (port 8102)" : "Sim error", r.ok);
  } catch {
    toast("UI server offline");
  } finally {
    btn.disabled = false;
  }
}

function parseJsonl(raw: string) {
  return raw.split(/\r?\n/).filter((l) => l.trim()).map((l) => JSON.parse(l) as SalEvent);
}

async function startReplay(path: string | null) {
  let label = path ?? "fixture";
  try {
    if (path === "fixture") throw new Error("embedded");
    const r = await fetch(path ? `/replay?path=${encodeURIComponent(path)}` : "/replay");
    if (!r.ok) throw new Error(String(r.status));
    const j = await r.json();
    log = j.events;
    label = j.path;
  } catch {
    log = parseJsonl(fixtureRaw);
    label = "ui/fixtures/sample_week.jsonl";
  }
  setMode("replay", label);
  $("stageNote").textContent = `replay · ${label}`;
  paintDays();
  const from = params.get("from") as Day | null;
  if (from && DAYS.includes(from)) {
    const idx = log.findIndex((e) => DAYS.indexOf(e.day) >= DAYS.indexOf(from));
    while (idx > 0 && cursor < idx) applyEvent(log[cursor++], true);
  }
  schedule();
}

async function startLive() {
  setMode("live");
  try {
    const r = await fetch("/events");
    if (r.ok) for (const e of (await r.json()) as SalEvent[]) applyEvent(e, true);
  } catch { /* server may be starting */ }
  const es = new EventSource("/stream");
  es.addEventListener("sal", (m) => applyEvent(JSON.parse((m as MessageEvent).data)));
  es.onerror = () => $("mode").classList.remove("live");
  es.onopen = () => $("mode").classList.add("live");
}

// keyboard: space play/pause · → next day · R instant replay fallback
window.addEventListener("keydown", (e) => {
  if (e.target instanceof HTMLInputElement) return;
  if (e.key === " ") { e.preventDefault(); togglePlay(); }
  else if (e.key === "ArrowRight") nextDay();
  else if (e.key.toLowerCase() === "r" && mode === "live") { const u = new URL(location.href); u.searchParams.set("replay", ""); location.href = u.toString(); }
});

scene.toast = toast;
paintMeters();
paintStrip();

(async () => {
  const replayParam = params.get("replay");
  if (replayParam !== null) return startReplay(replayParam || null);
  try {
    const r = await fetch("/mode");
    const j = await r.json();
    if (j.mode === "replay") return startReplay(j.replay_path);
    return startLive();
  } catch {
    // no server: play the bundled fixture so the dashboard is never blank
    return startReplay("fixture");
  }
})();
