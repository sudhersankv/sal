// Sal owner app (D-010 + docs/AGENT_UX.md): Home = Sal; drill-downs; Activity & Trace; Demo.
import "@fontsource/inter/300.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter-tight/300.css";
import "@fontsource/inter-tight/400.css";
import "@fontsource/inter-tight/500.css";
import "@fontsource/inter-tight/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./app.css";

import { createShopScene, type InventoryItem, type ShopScene as ShopHandle } from "./scene3d";
import type { SalEvent } from "./types";

// ------------------------------------------------------------------ utils
const $ = (id: string) => document.getElementById(id)!;
const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const usd = (n: unknown, d = 0) => (n == null || n === "" || Number.isNaN(Number(n)) ? "—" : `$${Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`);
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
function when(ts: unknown, withDay = true) {
  const s = String(ts ?? "");
  if (!s || s === "None") return "—";
  const d = new Date(s.length > 19 || s.includes("T") ? s.slice(0, 19) : s.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return s;
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return withDay ? `${DOW[d.getDay()]} ${d.getMonth() + 1}/${d.getDate()} ${hm}` : hm;
}
async function get<T = any>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} ${r.status}`);
  return r.json();
}
let toastT: number | undefined;
function toast(t: string, sal = false) {
  const el = $("toast");
  el.textContent = t;
  el.className = `toast show${sal ? " sal" : ""}`;
  clearTimeout(toastT);
  toastT = window.setTimeout(() => (el.className = "toast"), 2800);
}
const chip = (text: string, cls = "") => `<span class="chip ${cls}">${esc(text)}</span>`;
const whyBtn = (q: string) => `<button class="btn why" data-why="${esc(q)}">Why?</button>`;

// ------------------------------------------------------------------ nav + router
const PAGES: [string, string][] = [
  ["home", "Sal"], ["inventory", "Inventory"], ["orders", "Orders"], ["jobs", "Jobs"], ["vendors", "Vendors"],
  ["activity", "Activity & Trace"],
];
function paintNav(route: string, waiting = 0) {
  $("navItems").innerHTML = PAGES.map(([k, label]) => `<a href="#/${k}" class="${route === k ? "on" : ""}">${label}${k === "home" && waiting ? `<span class="n hot">${waiting}</span>` : ""}</a>`).join("")
    + `<div class="sep"></div><a href="/demo.html">Demo week <span class="n">sim</span></a>`;
}
let waitingCount = 0;
function route() {
  const [page = "home", ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  return { page: PAGES.some(([k]) => k === page) ? page : "home", rest: rest.map(decodeURIComponent) };
}
const main = $("main");
let renderSeq = 0;
async function render() {
  const { page, rest } = route();
  paintNav(page, waitingCount);
  const seq = ++renderSeq;
  try {
    const html = await (PAGE_FNS[page] ?? homePage)(rest);
    if (seq !== renderSeq) return;
    if (html !== null) main.innerHTML = html;
    after[page]?.(rest);
  } catch (e) {
    if (seq === renderSeq) main.innerHTML = `<div class="ph"><div><h1>Can't reach Sal's server</h1><p>${esc((e as Error).message)}</p></div></div>`;
  }
}
window.addEventListener("hashchange", () => { stopShopSync(); render(); });

// Why? → trace for that row
main.addEventListener("click", (e) => {
  const t = e.target as HTMLElement;
  const why = t.closest<HTMLElement>("[data-why]");
  if (why) { e.stopPropagation(); location.hash = `#/activity/trace/${encodeURIComponent(why.dataset.why!)}`; return; }
  const row = t.closest<HTMLElement>("[data-href]");
  if (row && !t.closest("a,button,input")) location.hash = row.dataset.href!;
  const card = t.closest<HTMLElement>(".tcard");
  if (card && !t.closest("a,button")) card.classList.toggle("open");
});

// ------------------------------------------------------------------ live stream
let mode: "live" | "replay" = "live";
const streamed: SalEvent[] = [];
let shop: ShopHandle | null = null;
const shopHost = document.createElement("div");
shopHost.className = "shop";
shopHost.innerHTML = `<div class="cap label">Parts room</div><div class="ticker" id="ticker"></div>`;
function ensureShop() {
  if (shop) return shop;
  const quality = new URLSearchParams(location.search).get("quality") === "low" ? "low" : "high";
  shop = createShopScene(shopHost, { quality, onSelect: (sku) => { if (sku) location.hash = `#/inventory/${encodeURIComponent(sku)}`; } });
  return shop;
}
let refreshT: number | undefined;
function onEvent(ev: SalEvent) {
  streamed.push(ev);
  shop?.handleEvent(ev as unknown as Parameters<ShopHandle["handleEvent"]>[0]);
  const tk = document.getElementById("ticker");
  if (tk) tk.innerHTML = `<b>${esc(when(ev.ts))}</b> · ${esc(ev.summary)}`;
  clearTimeout(refreshT);
  refreshT = window.setTimeout(() => {
    const { page } = route();
    if (page === "home" || page === "activity") render();
  }, 900);
}
function connect() {
  const es = new EventSource("/stream");
  es.addEventListener("sal", (m) => { try { onEvent(JSON.parse((m as MessageEvent).data)); } catch { /* ignore */ } });
  es.onopen = () => $("navMode").classList.add("live");
  es.onerror = () => $("navMode").classList.remove("live");
}

// ------------------------------------------------------------------ approvals
const KIND: Record<string, string> = { order: "order", restock: "order", quote: "quote", approval: "order", verification: "identity", dispute: "order", rule: "rule" };
async function decide(a: any, approved: boolean, btn: HTMLButtonElement) {
  btn.disabled = true;
  const kind = KIND[a.kind] ?? "order";
  const r = a.refs ?? {};
  const id = kind === "rule" ? r.rule_id ?? a.action_id : r.ro_id ?? r.approval_id ?? r.escalation_id ?? r.vendor_id ?? a.action_id;
  try {
    const res = await fetch("/sim/approve", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind, id, approved, action_id: a.action_id }) });
    if (res.ok) toast(approved ? "Approved. Sal is on it." : "Declined. Sal will stand down.", true);
    else toast(mode === "replay" ? "Recorded week: decisions are already in the log" : "Sal's runner is offline; try Telegram");
  } catch {
    toast("Server offline");
  } finally {
    btn.disabled = false;
  }
}

// ------------------------------------------------------------------ Home = Sal
const STEPS = ["planned", "waiting_owner", "in_progress", "done"];
const STATUS_LABEL: Record<string, [string, string]> = {
  planned: ["planned", ""], waiting_owner: ["waiting on you", "waiting"], in_progress: ["in progress", "progress"],
  done: ["done", "done"], refused: ["refused", "refused"], failed: ["failed", "failed"],
};
function actionCard(a: any, i: number) {
  const [label, cls] = STATUS_LABEL[a.status] ?? [a.status, ""];
  const idx = Math.max(0, STEPS.indexOf(a.status));
  const r = a.refs ?? {};
  const why = r.ro_id ?? r.order_id ?? r.rule_id ?? r.vendor_id ?? a.action_id;
  return `<div class="acard ${cls}">
    <div class="t">${chip(label, cls)}<span class="title">${esc(a.title)}</span><span class="mono muted" style="font-size:11px">${esc(when(a.updated))}</span></div>
    <div class="steps">${STEPS.map((_, k) => `<i class="${k <= idx ? "on" : ""}"></i>`).join("")}</div>
    <div class="meta"><span>${esc(a.kind)}</span>${r.ro_id ? `<span>job ${esc(r.ro_id)}</span>` : ""}${r.order_id ? `<span>order ${esc(String(r.order_id).replace(/^gid:\/\/shopify\/Order\//, "#"))}</span>` : ""}${a.history?.length > 1 ? `<span>${a.history.length} updates</span>` : ""}</div>
    <div class="acts">${a.status === "waiting_owner" ? `<button class="btn primary" data-decide="${i}" data-ok="1">Approve</button><button class="btn" data-decide="${i}" data-ok="0">Decline</button>` : ""}${whyBtn(why)}</div>
  </div>`;
}
let homeActions: any[] = [];
const chatLog: { who: "you" | "sal"; text: string; ts: string }[] = [];
let chatOffline = false;
async function homePage() {
  const [h, inv] = await Promise.all([get("/api/home"), get("/api/inventory")]);
  homeActions = h.actions ?? [];
  waitingCount = homeActions.filter((a) => a.status === "waiting_owner").length;
  paintNav("home", waitingCount);
  ensureShop().setInventory(inv.items as InventoryItem[]);
  const waiting = homeActions.filter((a) => a.status === "waiting_owner");
  const rest = homeActions.filter((a) => a.status !== "waiting_owner");
  const m = h.money ?? {};
  const greeting = waiting.length
    ? `${waiting.length} thing${waiting.length > 1 ? "s" : ""} need${waiting.length > 1 ? "" : "s"} you.`
    : "Nothing needs you right now.";
  const low = h.low_stock ?? 0;
  const arriving = h.arriving ?? [];
  return `
  <div class="ph"><div><h1>${esc(greeting)}</h1><p>${esc(`${when(h.today)} · ${low} part${low === 1 ? "" : "s"} low or out · ${arriving.length} order${arriving.length === 1 ? "" : "s"} on the way · ${usd(m.spend)} spent this week`)}</p></div></div>
  <div class="stats">
    <div class="stat"><div class="label">Spent this week</div><div class="v">${usd(m.spend)}</div><div class="sub">parts bought by Sal</div></div>
    <div class="stat"><div class="label">Parts margin</div><div class="v">${m.margin_pct == null ? "—" : `${Math.round(m.margin_pct)}<small>%</small>`}</div><div class="sub">on jobs, target ≥ 45%</div></div>
    <div class="stat"><div class="label">Saved / recovered</div><div class="v acc">${usd(m.saved)}</div><div class="sub">shipping waived, credits found</div></div>
    <div class="stat"><div class="label">Low / out of stock</div><div class="v">${low}<small> / ${h.out_of_stock ?? 0}</small></div><div class="sub"><a href="#/inventory/low" class="muted">see what's short →</a></div></div>
  </div>
  <div class="cols">
    <div class="stack">
      <div class="panel"><div class="panel-h"><span class="label">Waiting on you</span><span class="count">${waiting.length}</span></div>
        <div class="panel-b">${waiting.length ? waiting.map((a) => actionCard(a, homeActions.indexOf(a))).join("") : `<div class="empty">You're clear. Sal will ping you here and on Telegram when something needs a yes.</div>`}</div></div>
      <div class="panel"><div class="panel-h"><span class="label">What Sal is doing</span><span class="count">${rest.length}</span></div>
        <div class="panel-b">${rest.length ? rest.map((a) => actionCard(a, homeActions.indexOf(a))).join("") : `<div class="empty">No actions yet.</div>`}</div></div>
    </div>
    <div class="stack">
      <div class="panel" id="shopSlot"></div>
      <div class="panel"><div class="panel-h"><span class="label">Talk to Sal</span><span class="count" id="chatState">${chatOffline ? "offline" : "same Sal as Telegram"}</span></div>
        <div class="msgs" id="chatMsgs" style="max-height:260px;overflow:auto">${chatLog.length ? chatLog.map(chatBubble).join("") : `<div class="empty" style="padding:4px">Try “are we low for the Civics next week?” or “where's the Bosch order?”</div>`}</div>
        <form id="chatForm" style="display:flex;gap:8px;padding:12px;border-top:1px solid var(--line)"><input class="search" id="chatInput" style="flex:1" placeholder="Message Sal…" autocomplete="off" /><button class="btn primary">Send</button></form>
      </div>
      <div class="panel"><div class="panel-h"><span class="label">Arriving</span><a class="count" href="#/orders">all orders →</a></div>
        <div class="list" style="padding:0 12px">${arriving.length ? arriving.map((o: any) => `<div class="li"><span class="grow">${esc(o.items)}</span><span class="mono muted">${esc(o.vendor ?? "")}</span><span class="mono">${usd(o.total)}</span>${whyBtn(o.order_id)}</div>`).join("") : `<div class="empty">Nothing in transit.</div>`}</div></div>
    </div>
  </div>`;
}
function chatBubble(m: { who: string; text: string; ts: string }) {
  return `<div class="msg ${m.who === "sal" ? "sal" : ""}"><div class="who">${m.who === "sal" ? "Sal" : "You"}<span>${esc(m.ts)}</span></div>${esc(m.text)}</div>`;
}
let shopSync: number | undefined;
function stopShopSync() { clearInterval(shopSync); }
const after: Record<string, (rest: string[]) => void> = {
  home: () => {
    $("shopSlot").appendChild(shopHost);
    shop?.resize();
    main.querySelectorAll<HTMLButtonElement>("[data-decide]").forEach((b) => {
      b.onclick = () => decide(homeActions[Number(b.dataset.decide)], b.dataset.ok === "1", b);
    });
    const form = $("chatForm") as HTMLFormElement;
    form.onsubmit = async (e) => {
      e.preventDefault();
      const inp = $("chatInput") as HTMLInputElement;
      const text = inp.value.trim();
      if (!text) return;
      inp.value = "";
      const now = new Date();
      const hm = `${now.getHours()}:${String(now.getMinutes()).padStart(2, "0")}`;
      chatLog.push({ who: "you", text, ts: hm });
      $("chatMsgs").innerHTML = chatLog.map(chatBubble).join("") + `<div class="msg sal"><div class="who">Sal</div>…</div>`;
      try {
        const r = await fetch("/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ chat_id: "ui", text }) });
        if (!r.ok) throw new Error(String(r.status));
        const j = await r.json();
        chatOffline = false;
        chatLog.push({ who: "sal", text: j.reply ?? "(no reply)", ts: hm });
      } catch {
        chatOffline = true;
        chatLog.push({ who: "sal", text: "Sal is offline right now. Message Sal on Telegram, or check back in a minute.", ts: hm });
      }
      $("chatState").textContent = chatOffline ? "offline" : "same Sal as Telegram";
      const box = $("chatMsgs");
      box.innerHTML = chatLog.map(chatBubble).join("");
      box.scrollTop = box.scrollHeight;
    };
  },
};

// ------------------------------------------------------------------ Inventory
let invFilter = "all", invQuery = "";
async function inventoryPage(rest: string[]) {
  const d = await get("/api/inventory");
  if (rest[0] === "low") invFilter = "low";
  else if (rest[0]) invQuery = rest[0];
  const items: any[] = d.items;
  const html = () => {
    const q = invQuery.toLowerCase();
    const rows = items.filter((i) => (invFilter === "all" || (invFilter === "low" ? i.status !== "ok" : i.status === "out"))
      && (!q || `${i.sku} ${i.name} ${i.part_type}`.toLowerCase().includes(q)));
    return rows.map((i) => {
      const max = i.max_qty || Math.max(i.qty, 1);
      const inc = i.incoming;
      return `<tr>
        <td class="m">${esc(i.sku)}</td><td>${esc(i.name)}</td><td class="dim">${esc(String(i.part_type ?? "").replace(/_/g, " "))}</td>
        <td class="num">${i.qty}<span class="bar ${i.status !== "ok" ? "low" : ""}"><i style="width:${Math.min(100, (100 * i.qty) / max)}%"></i>${i.min_qty ? `<b style="left:${Math.min(100, (100 * i.min_qty) / max)}%"></b>` : ""}</span></td>
        <td class="num dim">${i.min_qty ?? "—"} / ${i.max_qty ?? "—"}</td>
        <td>${chip(i.status, i.status)}</td>
        <td class="num">${inc ? `+${inc.qty} <span class="dim">${esc(when(inc.eta))}</span>` : `<span class="dim">—</span>`}</td>
        <td class="num">${i.needed_7d || `<span class="dim">0</span>`}</td>
        <td>${whyBtn(i.sku)}</td></tr>`;
    }).join("") || `<tr><td colspan="9" class="empty">No parts match.</td></tr>`;
  };
  setTimeout(() => {
    const body = $("invBody");
    const inp = $("invQ") as HTMLInputElement;
    inp.oninput = () => { invQuery = inp.value; body.innerHTML = html(); };
    main.querySelectorAll<HTMLButtonElement>("[data-f]").forEach((b) => (b.onclick = () => {
      invFilter = b.dataset.f!;
      main.querySelectorAll("[data-f]").forEach((x) => x.classList.toggle("on", x === b));
      body.innerHTML = html();
    }));
  });
  const low = items.filter((i) => i.status !== "ok").length;
  return `<div class="ph"><div><h1>Inventory</h1><p>${items.length} parts on the shelf · ${low} low or out · needs counted against the next 7 days of bookings</p></div>
    <div class="toolbar"><input class="search" id="invQ" placeholder="Search part, SKU, type" value="${esc(invQuery)}" />
    <div class="seg">${["all", "low", "out"].map((f) => `<button data-f="${f}" class="${invFilter === f ? "on" : ""}">${f === "all" ? "All" : f === "low" ? "Low + out" : "Out"}</button>`).join("")}</div></div></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>SKU</th><th>Part</th><th>Type</th><th class="num">On hand</th><th class="num">Min / max</th><th>Status</th><th class="num">Incoming</th><th class="num">Needed 7d</th><th></th></tr></thead><tbody id="invBody">${html()}</tbody></table></div>`;
}

// ------------------------------------------------------------------ Orders
let ordFilter = "all";
async function ordersPage() {
  const d = await get("/api/orders");
  const all: any[] = d.orders;
  const html = () => all.filter((o) => ordFilter === "all" || o.status === ordFilter || (ordFilter === "sal" && o.source === "sal")).slice(0, 200).map((o) => `
    <tr><td class="m">${esc(when(o.placed_at))}</td><td>${esc(o.vendor ?? "—")}</td><td>${chip(o.channel ?? "counter")}</td>
    <td>${esc(o.items)}${o.source === "sal" ? ` <span class="chip sal">Sal</span>` : ""}</td><td class="num">${usd(o.total, 2)}</td>
    <td>${chip(o.status, o.status === "in transit" ? "transit" : o.status)}</td>
    <td class="m">${o.ro_id ? `<a href="#/jobs/${esc(o.ro_id)}">${esc(o.ro_id)}</a>` : `<span class="dim">stock</span>`}</td>
    <td>${o.admin_url ? `<a class="src" href="${esc(o.admin_url)}" target="_blank" rel="noopener">Shopify ↗</a>` : ""}</td>
    <td>${whyBtn(o.order_id)}</td></tr>`).join("") || `<tr><td colspan="9" class="empty">No orders.</td></tr>`;
  setTimeout(() => main.querySelectorAll<HTMLButtonElement>("[data-f]").forEach((b) => (b.onclick = () => {
    ordFilter = b.dataset.f!;
    main.querySelectorAll("[data-f]").forEach((x) => x.classList.toggle("on", x === b));
    $("ordBody").innerHTML = html();
  })));
  const transit = all.filter((o) => o.status === "in transit").length, late = all.filter((o) => o.status === "late").length;
  const up = (d.upcoming ?? []).map((u: any) => `<div class="acard"><div class="t">${chip("planned")}<span class="title">${esc(u.title)}</span></div>${u.reason ? `<div class="meta">${esc(u.reason)}</div>` : ""}</div>`).join("");
  return `<div class="ph"><div><h1>Orders</h1><p>${all.length} orders · ${transit} on the way · ${late} late</p></div>
    <div class="seg">${[["all", "All"], ["sal", "By Sal"], ["in transit", "On the way"], ["delivered", "Delivered"], ["late", "Late"]].map(([k, l]) => `<button data-f="${k}" class="${ordFilter === k ? "on" : ""}">${l}</button>`).join("")}</div></div>
    ${up ? `<div class="stack" style="margin-bottom:16px">${up}</div>` : ""}
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Placed</th><th>Vendor</th><th>Channel</th><th>Items</th><th class="num">Total</th><th>Status</th><th>Job</th><th></th><th></th></tr></thead><tbody id="ordBody">${html()}</tbody></table></div>`;
}

// ------------------------------------------------------------------ Jobs
async function jobsPage(rest: string[]) {
  if (rest[0]) return jobDetail(rest[0]);
  const d = await get("/api/jobs");
  const rows = (d.jobs as any[]).map((j) => `<tr class="click" data-href="#/jobs/${esc(j.ro_id)}">
    <td class="m">${esc(when(j.opened_at))}</td><td class="m">${esc(j.ro_id)}</td><td>${esc(j.vehicle || "—")}</td>
    <td class="dim" style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(j.complaint)}</td>
    <td class="num">${j.bay ?? "—"}</td><td>${esc(j.customer ?? "—")}</td>
    <td class="num">${j.cost ? `${usd(j.cost, 2)} <span class="dim">→ ${usd(j.retail, 0)}</span>` : "—"}</td>
    <td>${chip(j.status, j.status === "in progress" ? "progress" : j.status === "waiting on owner" ? "waiting" : "done")}${j.source === "sal" ? ` <span class="chip sal">Sal</span>` : ""}</td>
    <td>${whyBtn(j.ro_id)}</td></tr>`).join("");
  return `<div class="ph"><div><h1>Jobs</h1><p>Cars through the shop · parts cost vs what the customer paid</p></div></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Opened</th><th>Job</th><th>Vehicle</th><th>Work</th><th class="num">Bay</th><th>Customer</th><th class="num">Parts cost → retail</th><th>Status</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
async function jobDetail(ro: string) {
  const d = await get(`/api/jobs/${encodeURIComponent(ro)}`);
  const j = d.job ?? { ro_id: ro };
  const listings: any[] = Array.isArray(d.listings) ? d.listings : [];
  const dec = d.decisions ?? {};
  const lrows = listings.map((l) => {
    const x = dec[l.sku];
    return `<tr><td>${esc(l.vendor ?? l.vendor_id)}</td><td>${esc(l.brand)}</td><td class="m">${esc(l.sku)}</td><td class="num">${usd(l.price, 2)}</td>
      <td class="m dim">${esc(l.verdict ?? "")} ${l.score != null ? Number(l.score).toFixed(2) : ""}</td>
      <td>${x ? chip(x.verdict, x.verdict === "chosen" ? "sal" : "") : ""}</td><td class="dim">${esc(x?.reason ?? "")}</td></tr>`;
  }).join("");
  return `<a class="back" href="#/jobs">← Jobs</a>
    <div class="ph" style="margin-top:10px"><div><h1>${esc(j.vehicle || ro)}</h1><p>${esc(ro)} · ${esc(j.complaint ?? "")}</p></div>${whyBtn(ro)}</div>
    <div class="detail-h"><div><div class="label">Opened</div><div class="v">${esc(when(j.opened_at))}</div></div><div><div class="label">Bay</div><div class="v">${j.bay ?? "—"}</div></div>
    <div><div class="label">Parts cost → retail</div><div class="v">${usd(j.cost, 2)} → ${usd(j.retail, 0)}</div></div><div><div class="label">Status</div><div class="v">${esc(j.status ?? "—")}</div></div></div>
    ${listings.length ? `<div class="h2">How Sal picked the part</div><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Vendor</th><th>Brand</th><th>SKU</th><th class="num">Price</th><th>Match</th><th>Decision</th><th>Why</th></tr></thead><tbody>${lrows}</tbody></table></div>` : ""}
    ${(d.lines ?? []).length ? `<div class="h2">Parts used</div><div class="tbl-wrap"><table class="tbl"><tbody>${d.lines.map((l: any) => `<tr><td>${esc(l.brand)}</td><td class="dim">${esc(String(l.part_type).replace(/_/g, " "))}</td><td class="m">${esc(l.sku)}</td><td class="num">${l.qty}× ${usd(l.unit_price, 2)}</td></tr>`).join("")}</tbody></table></div>` : ""}
    <div class="h2">Trail (${d.events.length})</div><div class="stack">${d.events.length ? [...d.events].reverse().map(traceCard).join("") : `<div class="empty">From shop history (before Sal). No trace.</div>`}</div>`;
}

// ------------------------------------------------------------------ Vendors
async function vendorsPage() {
  const d = await get("/api/vendors");
  const cards = (d.vendors as any[]).map((v) => `<div class="vcard ${v.late_rate > 0.2 ? "bad" : ""}">
    <div style="display:flex;justify-content:space-between;align-items:center"><h3>${esc(v.name)}</h3>${chip(v.kind)}</div>
    <div class="big">${v.on_time_pct ?? "—"}<small>% on time</small></div><div class="muted" style="font-size:12px">last ${d.days} days · ${v.orders} orders</div>
    <div class="kv"><span>Late deliveries</span><span>${v.late} / ${v.orders}</span><span>Missed core credits</span><span>${v.missed_core_credits} · ${usd(v.missed_core_amount, 2)}</span>
    <span>Price index</span><span>${v.avg_price_index != null ? Number(v.avg_price_index).toFixed(2) : "—"}</span><span>Counter cutoff</span><span>${esc(String(v.cutoff_local ?? "—").slice(0, 5))}</span></div>
    <div style="margin-top:14px">${whyBtn(v.vendor_id)}</div></div>`).join("");
  const rules = (d.rules as any[]).map((r) => `<tr><td class="m">${esc(r.rule_id)}</td><td>${esc(r.title)}</td><td class="dim">${esc(r.rule_text)}</td>
    <td>${chip(r.status, r.status === "active" ? "" : "waiting")}${r.learned ? ` <span class="chip sal">learned</span>` : ""}</td><td>${whyBtn(r.rule_id)}</td></tr>`).join("");
  return `<div class="ph"><div><h1>Vendors</h1><p>Scorecards from purchase history · one SQL query over the last ${d.days} days</p></div>
    ${d.gate ? chip(`${d.gate.gate ?? "routing"} on`, "sal") : ""}</div>
    <div class="vgrid">${cards || `<div class="empty">No vendors yet.</div>`}</div>
    <div class="h2">Shop rules Sal follows</div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Rule</th><th>Title</th><th>Text</th><th>Status</th><th></th></tr></thead><tbody>${rules}</tbody></table></div>`;
}

// ------------------------------------------------------------------ Activity & Trace
const TYPE_LABEL: Record<string, string> = {
  "repair_order.created": "new job", "part.identified": "part identified", "context.retrieved": "looked up", "vendors.compared": "compared vendors",
  "part.rejected": "rejected", "part.chosen": "chose", "quote.sent": "quote sent", "approval.requested": "asked approval", "approval.received": "approved",
  "order.placed": "ordered", "order.delivered": "delivered", "payment.recorded": "payment", "inventory.checked": "checked stock", "stock.low": "low stock",
  "restock.planned": "restock plan", "statement.parsed": "read statement", "identity.verified": "verified owner", escalation: "needs owner",
  "scorecard.built": "scorecard", "rule.proposed": "proposed rule", "rule.approved": "rule approved", "memory.saved": "remembered", "gate.enabled": "routing on",
  "metrics.updated": "metrics", "sal.summary": "summary", "chat.message": "message", "action.status": "action", error: "error",
};
const WHO: Record<string, string> = { sal: "Sal", tech: "Tech", owner: "Owner", car_owner: "Customer", vendor: "Vendor", system: "System" };
function traceCard(e: SalEvent) {
  const m = e.money;
  const money = m ? [m.wholesale != null && m.retail != null ? `${usd(m.wholesale)} → ${usd(m.retail)}` : m.wholesale != null ? usd(m.wholesale) : m.retail != null ? usd(m.retail) : "",
    m.saved ? `<span class="s">+${usd(m.saved, m.saved % 1 ? 2 : 0)} saved</span>` : ""].filter(Boolean).join(" · ") : "";
  const src = (e.sources ?? []).map((s) => {
    const inner = `${esc(s.name)}${s.ref ? `<i>${esc(s.ref.length > 30 ? s.ref.slice(0, 29) + "…" : s.ref)}</i>` : ""}`;
    return s.url ? `<a class="src" href="${esc(s.url)}" target="_blank" rel="noopener">${inner}</a>` : `<span class="src">${inner}</span>`;
  }).join("");
  return `<div class="tcard ${e.actor === "sal" ? "sal" : ""}">
    <div class="meta"><span>${esc(when(e.ts))}</span><span class="ty">${esc(TYPE_LABEL[e.type] ?? e.type)}</span><span class="who">${esc(WHO[e.actor] ?? e.actor)}</span></div>
    <div class="sum">${esc(e.summary)}</div>${e.reason ? `<div class="why">${esc(e.reason)}</div>` : ""}
    ${src || money ? `<div class="row">${src}${money ? `<span class="money">${money}</span>` : ""}</div>` : ""}
    <div class="raw">${esc(JSON.stringify(e, null, 2))}</div></div>`;
}
let activeThread = "";
async function activityPage(rest: string[]) {
  const tab = rest[0] || "conversations";
  const tabs = [["conversations", "Conversations"], ["actions", "Actions"], ["trace", "Trace"], ["integrations", "Integrations"]]
    .map(([k, l]) => `<a href="#/activity/${k}" class="${tab === k ? "on" : ""}">${l}</a>`).join("");
  let body = "";
  if (tab === "conversations") {
    const d = await get("/api/activity");
    const threads: any[] = d.threads;
    if (!threads.some((t) => t.chat_id === activeThread)) activeThread = threads[0]?.chat_id ?? "";
    const t = threads.find((x) => x.chat_id === activeThread);
    const name = (id: string) => (id === "ui" ? "Dashboard chat" : /owner/.test(id) ? "Owner · Telegram" : /shop|tech/.test(id) ? "Shop floor · Telegram" : `Telegram ${id}`);
    body = threads.length ? `<div class="chat"><div class="threads">${threads.map((x) => `<div class="thread ${x.chat_id === activeThread ? "on" : ""}" data-thread="${esc(x.chat_id)}"><div>${esc(name(x.chat_id))}</div><div class="last">${esc(x.messages[x.messages.length - 1].text)}</div></div>`).join("")}</div>
      <div class="msgs">${(t?.messages ?? []).map((m: any) => `<div class="msg ${m.actor === "sal" ? "sal" : ""}"><div class="who">${esc(WHO[m.actor] ?? m.actor)}<span>${esc(when(m.ts))}</span>${m.intent ? `<span>· ${esc(m.intent)}</span>` : ""}</div>${esc(m.text)}</div>`).join("")}</div></div>`
      : `<div class="empty">No conversations yet. Message Sal on Telegram or from the Sal tab.</div>`;
    setTimeout(() => main.querySelectorAll<HTMLElement>("[data-thread]").forEach((el) => (el.onclick = () => { activeThread = el.dataset.thread!; render(); })));
  } else if (tab === "actions") {
    const d = await get("/api/activity");
    body = `<div class="stack">${(d.actions as any[]).map((a) => `<div class="acard ${STATUS_LABEL[a.status]?.[1] ?? ""}"><div class="t">${chip(STATUS_LABEL[a.status]?.[0] ?? a.status, STATUS_LABEL[a.status]?.[1] ?? "")}<span class="title">${esc(a.title)}</span>${whyBtn(a.refs?.ro_id ?? a.refs?.order_id ?? a.refs?.rule_id ?? a.action_id)}</div>
      <div class="meta">${(a.history as any[]).map((h) => `<span>${esc(when(h.ts))} ${esc(STATUS_LABEL[h.status]?.[0] ?? h.status)}</span>`).join("<span>→</span>")}</div></div>`).join("") || `<div class="empty">No actions yet.</div>`}</div>`;
  } else if (tab === "trace") {
    const q = rest[1] ?? "";
    const typeSel = rest[2] ?? "";
    const d = await get(`/api/trace?limit=400${q ? `&q=${encodeURIComponent(q)}` : ""}${typeSel ? `&type=${encodeURIComponent(typeSel)}` : ""}`);
    const types = Object.keys(TYPE_LABEL);
    body = `<div class="toolbar" style="margin-bottom:14px"><input class="search" id="trQ" placeholder="Filter: job, order, SKU, vendor, any text" value="${esc(q)}" />
      <select class="search" id="trT" style="min-width:180px"><option value="">All event types</option>${types.map((t) => `<option value="${t}" ${t === typeSel ? "selected" : ""}>${esc(TYPE_LABEL[t])}</option>`).join("")}</select>
      <span class="count">${d.events.length} events${q ? ` matching “${esc(q)}”` : ""}</span></div>
      <div class="stack">${(d.events as SalEvent[]).map(traceCard).join("") || `<div class="empty">${q ? "No Sal trace for this one. It is shop history from before Sal, or nothing Sal touched." : "Nothing matches."}</div>`}</div>`;
    setTimeout(() => {
      const go = () => { location.hash = `#/activity/trace/${encodeURIComponent(($("trQ") as HTMLInputElement).value)}/${encodeURIComponent(($("trT") as HTMLSelectElement).value)}`; };
      ($("trQ") as HTMLInputElement).onchange = go;
      ($("trT") as HTMLSelectElement).onchange = go;
    });
  } else {
    const d = await get("/api/integrations");
    body = `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Service</th><th>Mode</th><th class="num">Events cited</th><th>Last used</th></tr></thead><tbody>${(d.integrations as any[]).map((i) => `<tr><td>${esc(i.name)}</td><td>${chip(i.mode, i.mode === "live" ? "live" : "")}</td><td class="num">${i.events}</td><td class="m dim">${esc(when(i.last))}</td></tr>`).join("")}</tbody></table></div>
      <p class="muted" style="font-size:12px;margin-top:12px">Live = key configured. Fallback = local cache or sqlite, labeled in every trace. Database: ${esc(d.seed?.status ?? "")} ${esc(d.seed?.detail ?? "")}</p>`;
  }
  return `<div class="ph"><div><h1>Activity & Trace</h1><p>Everything Sal saw, said and did. Tap any card for the raw record.</p></div></div><div class="subtabs">${tabs}</div>${body}`;
}

const PAGE_FNS: Record<string, (rest: string[]) => Promise<string | null>> = {
  home: homePage, inventory: inventoryPage, orders: ordersPage, jobs: jobsPage, vendors: vendorsPage, activity: activityPage,
};

// ------------------------------------------------------------------ boot
(async () => {
  try {
    const m = await get("/mode");
    mode = m.mode;
  } catch { /* server offline */ }
  $("navModeText").textContent = mode === "replay" ? "RECORDED WEEK" : "LIVE";
  if (mode === "live") $("navMode").classList.add("live");
  try {
    const h = await get("/api/home");
    $("navClock").textContent = `Shop time ${when(h.today)}`;
  } catch { /* ignore */ }
  render();
  connect();
})();
