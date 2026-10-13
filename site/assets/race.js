// Title-race charts: each contender's chances through the season, from the daily history files.
import { $, esc, pct, getJSON, clubName, clubCrest } from "./core.js";

const UCL_METRICS = [["top8", "Top 8"], ["last16", "Last 16"], ["qf", "Quarter-finals"], ["sf", "Semi-finals"], ["final", "Final"], ["title", "Winner"]];
const DASHES = ["", "4 3", "1 3", "6 2 1 2", "2 2"];
const MAX_LINES = 6;
const WIDE = new Set(["title", "final", "sf"]); // judged by their peak; the rest by where they stand now
const choice = {}; // chosen metric per competition kind
let token = 0;
let state = null; // { data, hist } of the chart on screen

const dayOf = (iso) => Date.parse(`${iso}T00:00:00Z`);
const fmt = (iso, opts) => new Date(dayOf(iso)).toLocaleDateString("en-GB", { ...opts, timeZone: "UTC" }).replace("Sept", "Sep");
const last = (vals) => { for (let i = vals.length - 1; i >= 0; i--) if (vals[i] != null) return i; return -1; };

export async function showRace(data) {
  const mine = ++token;
  const frame = $("race-frame");
  let hist;
  try {
    hist = await getJSON(`history/${data.season.split("/")[0]}/${data.slug}.json`);
  } catch {
    if (mine === token) { frame.hidden = true; state = null; }
    return;
  }
  if (mine !== token) return;
  if (!hist.dates || hist.dates.length < 2) { frame.hidden = true; state = null; return; }
  state = { data, hist };
  frame.hidden = false;
  draw();
}

function metricsFor({ data, hist }) {
  if (data.kind === "ucl") return UCL_METRICS.filter(([key]) => hist.metrics.includes(key));
  const top = data.zones.find((z) => z.key === "ucl")?.to ?? 4;
  return [["title", "Title"], ["ucl", `Top ${top}`], ["releg", "Relegation"]].filter(([key]) => hist.metrics.includes(key));
}

/* the contenders for one metric, best first */
export function pickTeams(teams, metric) {
  return teams.map((t) => {
    const vals = t[metric] || [], at = last(vals), now = at < 0 ? 0 : vals[at];
    return { t, vals, at, now, peak: Math.max(0, ...vals.filter((v) => v != null)) };
  }).filter((r) => r.at >= 0 && (WIDE.has(metric) ? Math.max(r.peak, r.now) >= 3 : r.now >= 3 && r.now <= 97))
    .sort((a, b) => b.now - a.now).slice(0, MAX_LINES);
}

function draw() {
  if (!state || $("race-frame").hidden || $("view-tables").hidden) return;
  const { data, hist } = state, ucl = data.kind === "ucl";
  const metrics = metricsFor(state);
  if (!metrics.length) { $("race-frame").hidden = true; return; }
  const key = metrics.some(([k]) => k === choice[data.kind]) ? choice[data.kind] : "title";
  const label = metrics.find(([k]) => k === key)[1];
  $("race-chips").innerHTML = metrics.map(([k, text]) => `<button type="button" class="chip" data-metric="${k}" aria-pressed="${k === key}">${esc(text)}</button>`).join("");

  const rows = pickTeams(hist.teams, key);
  const first = fmt(hist.dates[0], { day: "numeric", month: "short" });
  const runs = ucl ? "simulated tournaments" : "simulated seasons";
  $("race-note").textContent = `One point per day with new results, from ${first}. Chances are shares of 10,000 ${runs}, as forecast that day. The table below lists the current values.`;
  if (!rows.length) { $("race-chart").innerHTML = `<p class="note">Nobody has been in this race yet.</p>`; return; }

  const tone = key === "releg" ? "var(--red)" : "var(--amber)";
  const W = Math.round(Math.min(760, Math.max(300, $("race-chart").clientWidth || 760)));
  const phone = W < 480;
  const H = Math.round(Math.max(240, W * 0.5)), pad = { l: 36, r: phone ? 12 : 130, t: 12, b: 26 };
  const times = hist.dates.map(dayOf), t0 = times[0], t1 = times[times.length - 1];
  const x = (ms) => pad.l + ((ms - t0) / (t1 - t0)) * (W - pad.l - pad.r);
  const y = (v) => H - pad.b - (v / 100) * (H - pad.t - pad.b);

  const grid = [0, 25, 50, 75, 100].map((v) => `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="tick" x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end">${v}%</text>`).join("");
  const months = [], d0 = new Date(t0);
  for (let m = Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth() + (d0.getUTCDate() === 1 ? 0 : 1), 1); m <= t1; m = Date.UTC(new Date(m).getUTCFullYear(), new Date(m).getUTCMonth() + 1, 1)) months.push(m);
  const axis = [];
  const startGap = months.length ? x(months[0]) - pad.l : Infinity;
  if (startGap >= 64) axis.push(`<text class="tick" x="${pad.l}" y="${H - 8}" text-anchor="start">${first}</text>`);
  for (const ms of months) axis.push(`<line class="grid" x1="${x(ms)}" x2="${x(ms)}" y1="${H - pad.b}" y2="${H - pad.b + 4}"/><text class="tick" x="${x(ms)}" y="${H - 8}" text-anchor="middle">${new Date(ms).toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }).replace("Sept", "Sep")}</text>`);

  // lines break at nulls; a lone point becomes a dot
  const path = (vals) => {
    let d = "", dots = "", run = 0;
    vals.forEach((v, i) => {
      if (v == null) { run = 0; return; }
      const next = vals[i + 1] != null;
      if (!run && !next) dots += `<circle cx="${x(times[i])}" cy="${y(v)}" r="2"/>`;
      d += `${run ? "L" : "M"}${x(times[i]).toFixed(1)} ${y(v).toFixed(1)}`;
      run++;
    });
    return [d, dots];
  };
  const lines = rows.map((r, i) => {
    const [d, dots] = path(r.vals);
    const style = i ? `stroke-dasharray="${DASHES[(i - 1) % DASHES.length]}"` : "";
    return `<g class="ln${i ? "" : " first"}"><path d="${d}" ${style}/>${dots}</g>`;
  }).reverse().join(""); // leader drawn last

  // end labels, pushed apart vertically with a short leader when moved
  let labels = "";
  if (!phone) {
    const L = rows.map((r, i) => ({ r, i, y0: y(r.now), y: y(r.now) })).sort((a, b) => a.y0 - b.y0);
    L.forEach((l, k) => { if (k) l.y = Math.max(l.y, L[k - 1].y + 14); });
    for (let k = L.length - 1; k >= 0; k--) L[k].y = Math.min(L[k].y, k === L.length - 1 ? H - pad.b : L[k + 1].y - 14);
    const xe = W - pad.r;
    labels = L.map(({ r, i, y0, y: ly }) => {
      const name = r.t.name.length > 12 ? r.t.name.slice(0, 11) + "…" : r.t.name;
      const mover = Math.abs(ly - y0) > 1 ? `<line class="lead-ln" x1="${xe + 2}" y1="${y0}" x2="${xe + 8}" y2="${ly}"/>` : "";
      return `${mover}<text class="end-lbl${i ? "" : " first"}" x="${xe + 11}" y="${ly + 4}">${esc(name)} ${pct(r.now)}</text>`;
    }).join("");
  }

  // one hit column per date, carrying that day's values for the shared tooltip
  const hits = hist.dates.map((iso, i) => {
    const x0 = i ? (x(times[i - 1]) + x(times[i])) / 2 : pad.l, x1 = i < times.length - 1 ? (x(times[i]) + x(times[i + 1])) / 2 : W - pad.r;
    const vals = rows.filter((r) => r.vals[i] != null).sort((a, b) => b.vals[i] - a.vals[i]);
    const tip = `<b>${fmt(iso, { weekday: "short", day: "numeric", month: "short" })}</b>${vals.map((r) => `<br>${clubName(r.t.id, r.t.name, "inline")} <b>${pct(r.vals[i])}</b>`).join("")}`;
    return `<rect class="hit" data-i="${i}" x="${x0.toFixed(1)}" y="${pad.t}" width="${(x1 - x0).toFixed(1)}" height="${H - pad.t - pad.b}" data-tip="${esc(tip)}"/>`;
  }).join("");

  const now = rows.map((r) => `${r.t.name} ${pct(r.now)}`).join(", ");
  const aria = `${label} chances since ${first}: ${now}. The table below lists the current values.`;
  $("race-chart").style.cssText = `--tone:${tone};--tone-t:${key === "releg" ? tone : "var(--amber-t)"}`;
  $("race-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(aria)}">
    ${grid}${axis.join("")}${lines}${labels}
    <line class="xhair" y1="${pad.t}" y2="${H - pad.b}" hidden/><g class="hov"></g>${hits}</svg>`
    + (phone ? `<ul class="race-legend">${rows.map((r, i) => `<li class="${i ? "" : "first"}"><svg width="22" height="8" aria-hidden="true"><line x1="0" x2="22" y1="4" y2="4" stroke="${i ? "var(--ink-2)" : tone}" stroke-width="${i ? 1.5 : 2.5}" ${i ? `stroke-dasharray="${DASHES[(i - 1) % DASHES.length]}"` : ""}/></svg>${clubCrest(r.t.id, "inline")}<span>${esc(r.t.name)}</span> <b>${pct(r.now)}</b></li>`).join("")}</ul>` : "");

  // crosshair and points follow the pointer, snapped to the date
  const svg = $("race-chart").querySelector("svg"), xhair = svg.querySelector(".xhair"), hov = svg.querySelector(".hov");
  const clear = () => { xhair.setAttribute("hidden", ""); hov.innerHTML = ""; };
  const track = (e) => {
    const i = e.target.dataset?.i;
    if (i == null) return clear();
    const cx = x(times[i]);
    xhair.setAttribute("x1", cx); xhair.setAttribute("x2", cx); xhair.removeAttribute("hidden");
    hov.innerHTML = rows.map((r, n) => r.vals[i] == null ? "" : `<circle class="${n ? "" : "first"}" cx="${cx}" cy="${y(r.vals[i])}" r="3.5"/>`).join("");
  };
  svg.addEventListener("pointermove", track);
  svg.addEventListener("pointerdown", track);
  svg.addEventListener("pointerleave", clear);
}

$("race-chips").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-metric]");
  if (!b || !state) return;
  choice[state.data.kind] = b.dataset.metric;
  draw();
});

let resizing;
window.addEventListener("resize", () => {
  clearTimeout(resizing);
  resizing = setTimeout(draw, 150);
});
