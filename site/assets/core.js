// Shared helpers: data loading, formatting, the tooltip and the refresh status.

// Display order; the first entry is the default page.
export const COMPS = [
  { slug: "la-liga", label: "La Liga", short: "ESP" },
  { slug: "premier-league", label: "Premier League", short: "ENG" },
  { slug: "bundesliga", label: "Bundesliga", short: "GER" },
  { slug: "ligue-1", label: "Ligue 1", short: "FRA" },
  { slug: "serie-a", label: "Serie A", short: "ITA" },
  { slug: "champions-league", label: "Champions League", short: "UCL" },
];
export const LEAGUES = COMPS.filter((c) => c.slug !== "champions-league");
export const compBySlug = Object.fromEntries(COMPS.map((c) => [c.slug, c]));

// Mirrors the cron in .github/workflows/site.yml (daily, 05:30 UTC).
const REFRESH_UTC = { hour: 5, minute: 30 };
const STALE_HOURS = 30;

export const $ = (id) => document.getElementById(id);
export const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const nf = new Intl.NumberFormat("en-US");
export const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

/* table cells drop the % sign (headers carry it); prose keeps it */
export function num(p) {
  if (p <= 0) return "–";
  if (p < 0.5) return "<1";
  if (p > 99.5) return ">99";
  return Math.round(p).toString();
}
export const pct = (p) => (p <= 0 ? "0%" : num(p) + "%");
/* probabilities stored as 0–1 */
export const pct1 = (p) => pct(p * 100);
export const dec = (v, d = 1) => (v == null ? "–" : Number(v).toFixed(d));

export function when(iso) {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
}
export function ago(iso) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

/* kickoffs in the viewer's own time zone */
export const clock = (iso) => new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
export const dayKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const parseDay = (key) => { const [y, m, d] = key.split("-").map(Number); return new Date(y, m - 1, d); };
export const shiftDay = (key, n) => { const d = parseDay(key); d.setDate(d.getDate() + n); return dayKey(d); };
export const shortDate = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/* bulb brightness: near-linear so only real contenders light up; `top` is the brightest chance on show */
export function bulb(p, top) {
  const t = Math.min(1, Math.pow(Math.max(0, p) / top, 0.9));
  return t < 0.02 ? "var(--bulb-off)" : `color-mix(in srgb, var(--amber) ${Math.round(t * 100)}%, var(--bulb-off))`;
}

/* ---------- data ---------- */
const cache = new Map();
export function getJSON(path) {
  if (!cache.has(path)) {
    const request = fetch(`data/${path}`, { cache: "no-cache" }).then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    });
    request.catch(() => cache.delete(path));
    cache.set(path, request);
  }
  return cache.get(path);
}

/* Crests use provider IDs, including clubs outside the five domestic leagues. */
let crests = {};
export async function loadCrests() {
  crests = await getJSON("crests.json");
}
const crestSizes = { inline: 18, row: 24, card: 36, hero: 80 };
export function clubCrest(id, size = "row") {
  const crest = crests[id];
  if (!crest) return "";
  const pixels = crestSizes[size];
  return `<span class="crest${crest.backing ? " crest--backed" : ""}"><img class="club-crest" src="${esc(crest.path)}" width="${pixels}" height="${pixels}" alt="" decoding="async"${size === "hero" ? "" : ' loading="lazy"'}></span>`;
}
export function clubName(id, name, size = "row") {
  return `<span class="club-name club-name--${size}">${clubCrest(id, size)}<span class="club-label" title="${esc(name)}">${esc(name)}</span></span>`;
}
document.addEventListener("error", (event) => {
  if (event.target.classList?.contains("club-crest")) event.target.parentElement.hidden = true;
}, true);

/* ---------- match helpers (probabilities are home, draw, away) ---------- */
export const outcome = (score) => (score[0] > score[1] ? 0 : score[0] === score[1] ? 1 : 2);
export const pick = (p) => p.indexOf(Math.max(...p));
/* the predicted score: the likeliest scoreline within the picked outcome, so it never contradicts the pick
   (older data has no `call`; its top four always hold one) */
export function callScore(m) {
  if (m.call) return m.call;
  const fav = pick(m.p);
  return m.top.find(([h, a]) => outcome([h, a]) === fav) || m.top[0];
}
export function verdict(m) {
  if (!m.score || !m.p) return null;
  const actual = outcome(m.score);
  const [h, a] = callScore(m);
  return { hit: pick(m.p) === actual, exact: h === m.score[0] && a === m.score[1], given: m.p[actual], actual };
}
/* the match from one club's side: [win, draw, loss] and [for, against] */
export const sideProbs = (m, home) => (home ? m.p : [m.p[2], m.p[1], m.p[0]]);
export const sidePair = (pair, home) => (home ? pair : [pair[1], pair[0]]);

/* ---------- refresh status ---------- */
function lastScheduledRun(now) {
  const run = new Date(now);
  run.setUTCHours(REFRESH_UTC.hour, REFRESH_UTC.minute, 0, 0);
  if (run > now) run.setUTCDate(run.getUTCDate() - 1);
  return run;
}
function nextRunText(generatedAt) {
  const now = new Date();
  const last = lastScheduledRun(now);
  // The run takes ~10 minutes; until its data lands, say so rather than promising tomorrow.
  if (new Date(generatedAt) < last && now - last < 3.6e6) return "updating now";
  const mins = Math.ceil((last.getTime() + 864e5 - now) / 60000);
  return mins < 60 ? `next in ${mins} min` : `next in ${Math.round(mins / 60)} h`;
}
let statusSource = null;
export function setStatus(generatedAt, cutoff) {
  statusSource = { generatedAt, cutoff };
  const hours = (Date.now() - new Date(generatedAt)) / 3.6e6;
  $("lamp").classList.toggle("stale", hours > STALE_HOURS);
  $("status-text").textContent = `Updated ${ago(generatedAt)} · ${nextRunText(generatedAt)}`;
  const through = cutoff ? ` · results through ${when(cutoff)}` : "";
  $("status-text").title = `Model run ${when(generatedAt)}${through} · refreshes daily at 05:30 UTC`;
  $("foot-updated").textContent = `Model run ${when(generatedAt)}${through}`;
}
// Keep the "updated / next" wording current on a page left open.
setInterval(() => { if (statusSource) setStatus(statusSource.generatedAt, statusSource.cutoff); }, 60000);

/* ---------- tooltip ---------- */
const tip = $("tip");
let tipTimer;
function showTip(el, x, y) {
  tip.innerHTML = el.dataset.tip;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  tip.style.left = Math.min(window.innerWidth - r.width - 8, Math.max(8, x + 14)) + "px";
  tip.style.top = (y - r.height - 12 < 8 ? y + 18 : y - r.height - 12) + "px";
}
document.addEventListener("mousemove", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  if (el) showTip(el, e.clientX, e.clientY);
  else tip.hidden = true;
});
document.addEventListener("touchstart", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  if (!el) { tip.hidden = true; return; }
  showTip(el, e.touches[0].clientX, e.touches[0].clientY);
  clearTimeout(tipTimer);
  tipTimer = setTimeout(() => { tip.hidden = true; }, 2500);
}, { passive: true });
document.addEventListener("focusin", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  if (!el) { tip.hidden = true; return; }
  const r = el.getBoundingClientRect();
  showTip(el, r.left + r.width / 2, r.top);
});
window.addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });

/* Rows that expand: click or Enter/Space on [data-toggle] calls `open(row)` / closes the panel after it. */
export function expandable(container, selector, build) {
  const toggle = (row) => {
    const open = row.getAttribute("aria-expanded") === "true";
    const next = row.nextElementSibling;
    if (next && next.classList.contains("panel")) next.remove();
    row.setAttribute("aria-expanded", String(!open));
    if (!open) row.after(build(row));
  };
  container.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const row = e.target.closest(selector);
    if (row && container.contains(row)) toggle(row);
  });
  container.addEventListener("keydown", (e) => {
    const row = e.target.closest(selector);
    if (row && e.target === row && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); toggle(row); }
  });
}
