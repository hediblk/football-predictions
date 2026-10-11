"use strict";

const COMPS = [
  { slug: "premier-league", label: "Premier League" },
  { slug: "la-liga", label: "La Liga" },
  { slug: "bundesliga", label: "Bundesliga" },
  { slug: "serie-a", label: "Serie A" },
  { slug: "ligue-1", label: "Ligue 1" },
  { slug: "champions-league", label: "Champions League" },
];
const STAGES = [["playoffs", "Play-offs"], ["round16", "Round of 16"], ["quarterfinal", "Quarter-finals"], ["semifinal", "Semi-finals"], ["final", "Final"]];
const STALE_HOURS = 24;

const $ = (id) => document.getElementById(id);
const cache = new Map();
let current = null;

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const nf = new Intl.NumberFormat("en-US");
const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

/* table cells drop the % sign (headers carry it); prose keeps it */
function num(p) {
  if (p <= 0) return "–";
  if (p < 0.5) return "<1";
  if (p > 99.5) return ">99";
  return Math.round(p).toString();
}
const pct = (p) => (p <= 0 ? "0%" : num(p) + "%");

function when(iso) {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
}
function ago(iso) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

/* bulb brightness: near-linear so only real contenders for a place light up; `top` is the brightest chance on the board */
function bulb(p, top) {
  const t = Math.min(1, Math.pow(Math.max(0, p) / top, 0.9));
  return t < 0.02 ? "var(--bulb-off)" : `color-mix(in srgb, var(--amber) ${Math.round(t * 100)}%, var(--bulb-off))`;
}

/* ---------- navigation ---------- */
function renderNav(active) {
  $("nav").innerHTML = COMPS.map((c) =>
    `<button type="button" data-slug="${c.slug}" aria-current="${c.slug === active}">${c.label}</button>`).join("");
  const on = $("nav").querySelector('[aria-current="true"]');
  if (on) on.scrollIntoView({ block: "nearest", inline: "nearest" });
}
$("nav").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-slug]");
  if (b) location.hash = b.dataset.slug;
});
window.addEventListener("hashchange", route);

function route() {
  const comp = COMPS.find((c) => c.slug === location.hash.slice(1)) || COMPS[0];
  renderNav(comp.slug);
  load(comp.slug);
}

async function fetchData(slug) {
  const res = await fetch(`data/${slug}.json`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function load(slug) {
  current = slug;
  if (!cache.has(slug)) {
    $("status-text").textContent = "Loading";
    try {
      cache.set(slug, await fetchData(slug));
    } catch (err) {
      $("hero-in").innerHTML = `<div class="who"><h1>No signal</h1><p class="caption">This forecast could not be loaded (${esc(err.message)}).</p></div>`;
      $("status-text").textContent = "Offline";
      return;
    }
  }
  if (current === slug) render(cache.get(slug), true);
}

$("reload").addEventListener("click", async () => {
  const btn = $("reload");
  btn.disabled = true;
  try {
    const before = cache.get(current)?.generated_at;
    const data = await fetchData(current);
    cache.clear();
    cache.set(current, data);
    render(data, data.generated_at !== before);
    if (data.generated_at === before) $("status-text").textContent = `No newer run · ${ago(data.generated_at)}`;
  } catch {
    $("status-text").textContent = "Reload failed";
  } finally {
    btn.disabled = false;
  }
});

function renderStatus(data) {
  const hours = (Date.now() - new Date(data.generated_at)) / 3.6e6;
  $("lamp").classList.toggle("stale", hours > STALE_HOURS);
  $("status-text").textContent = `Updated ${ago(data.generated_at)}`;
  $("status-text").title = `Model run ${when(data.generated_at)} · results through ${when(data.data_cutoff)}`;
  $("foot-updated").textContent = `Model run ${when(data.generated_at)} · results through ${when(data.data_cutoff)}`;
}

/* ---------- page ---------- */
function render(data, fresh) {
  const ucl = data.kind === "ucl";
  document.title = `${data.name} forecast ${data.season} · Final Table`;
  renderStatus(data);
  renderHero(data, fresh);
  renderRaces(data);
  renderTable(data);
  $("ko-frame").hidden = !ucl;
  $("bracket-frame").hidden = !ucl;
  if (ucl) {
    renderKnockouts(data);
    renderBracket(data);
  }
}

function renderHero(data, fresh) {
  const ucl = data.kind === "ucl";
  const byTitle = [...data.teams].sort((a, b) => b.title - a.title);
  const [fav, ...rest] = byTitle;
  const runs = ucl ? "simulated tournaments" : "simulated seasons";
  const wins = Math.round((fav.title / 100) * data.n_sim);
  const rivals = rest.slice(0, 2).map((t) => `${esc(t.name)} <b>${pct(t.title)}</b>`).join(" · ");
  const extra = ucl
    ? `Reaches the final in <b>${pct(fav.stages.final)}</b>`
    : `Expected <b>${Math.round(fav.xpts)}</b> pts (${fav.p10}–${fav.p90})`;
  $("hero-legend").textContent = `${data.name} · ${data.season} · ${ucl ? "Trophy" : "Title"}`;
  $("hero-in").innerHTML = `
    <div class="who">
      <h1>${esc(fav.name)}</h1>
      <p class="caption">${ucl ? "Wins it" : "Champions"} in <b>${nf.format(wins)}</b> of ${nf.format(data.n_sim)} ${runs} · ${rivals} · ${extra}</p>
    </div>
    <div class="numeral${fresh ? " on" : ""}" role="img" aria-label="${esc(`${fav.name}: ${pct(fav.title)} chance`)}">${Math.round(fav.title)}<sup>%</sup></div>`;
}

function raceLine(title, note, rows, field, tone, emptyText) {
  const items = rows.length
    ? `<ol>${rows.map((t) => `<li><span class="nm">${esc(t.name)}</span><span class="v">${pct(t[field])}</span></li>`).join("")}</ol>`
    : `<span class="empty">${emptyText}</span>`;
  return `<div class="race ${tone}"><h2>${title}<small>${note}</small></h2>${items}</div>`;
}

function renderRaces(data) {
  const t = data.teams;
  const pick = (f, lo, hi, n = 6) => t.filter((x) => x[f] >= lo && x[f] <= hi).sort((a, b) => b[f] - a[f]).slice(0, n);
  let lines;
  if (data.kind === "ucl") {
    const finalists = [...t].sort((a, b) => b.stages.final - a.stages.final).slice(0, 6).map((x) => ({ ...x, final: x.stages.final }));
    lines = [
      raceLine("Final", "reach the final", finalists, "final", "", ""),
      raceLine("Top eight", "skip the play-offs", pick("r16", 15, 92), "r16", "", "No close calls right now."),
      raceLine("Danger", "out before the knockouts", pick("out", 10, 95), "out", "red", "Nobody in real danger."),
    ];
  } else {
    const top = data.zones.find((z) => z.key === "ucl").to;
    const rel = data.zones.find((z) => z.key === "releg");
    lines = [
      raceLine("Title", "finish first", t.filter((x) => x.title >= 0.5).sort((a, b) => b.title - a.title).slice(0, 6), "title", "", ""),
      raceLine(`Top ${top}`, "Champions League places", pick("ucl", 4, 97), "ucl", "", "The top places look settled."),
      raceLine("Drop", `${ordinal(rel.from)} or lower`, t.filter((x) => x.releg >= 4).sort((a, b) => b.releg - a.releg).slice(0, 6), "releg", "red", "Nobody in real danger."),
    ];
  }
  $("races").innerHTML = lines.join("");
}

/* ---------- main board ---------- */
function renderTable(data) {
  const ucl = data.kind === "ucl";
  const n = data.teams.length;
  const size = ucl ? 9 : 13;
  const gaps = ucl ? new Set([9, 25]) : new Set();
  const top = Math.min(50, Math.max(...data.teams.flatMap((t) => t.probs)));
  const lo = Math.min(...data.teams.map((t) => Math.min(t.points, t.p10)));
  const hi = Math.max(...data.teams.map((t) => t.p90));
  const x = (v) => (((v - lo) / Math.max(1, hi - lo)) * 100).toFixed(1);
  const good = data.zones[0];
  const bad = data.zones[data.zones.length - 1];
  const cols = ucl
    ? [["r16", "Top 8 %", "lit"], ["playoff", "Play-off %", ""], ["out", "Out %", "warn"]]
    : [["title", "Title %", "lit"], ["ucl", `Top ${good.to} %`, "b"], ["europe", "Europe %", ""], ["releg", "Down %", "warn"]];

  const head = Array.from({ length: n }, (_, i) => {
    const pos = i + 1;
    const zone = pos <= good.to ? "z-good" : pos >= bad.from ? "z-bad" : "";
    const label = ucl ? ([1, 8, 9, 24, 25, 36].includes(pos) ? pos : "") : pos;
    return `<span class="${zone}${gaps.has(pos) ? " gap" : ""}">${label}</span>`;
  }).join("");

  const cuts = ucl
    ? { 8: ["▲ Round of 16 · ▼ Play-offs", ""], 24: ["▼ Eliminated", "bad"] }
    : { [good.to]: ["▲ Champions League", ""], [bad.from - 1]: ["▼ Relegation", "bad"] };
  const span = 7 + cols.length;

  const rows = data.teams.map((t, i) => {
    const rank = i + 1;
    const bulbs = t.probs.map((p, j) =>
      `<i class="${gaps.has(j + 1) ? "gap" : ""}" style="background:${bulb(p, top)}" data-tip="${esc(`<b>${esc(t.name)}</b> ${ordinal(j + 1)}: <b>${p.toFixed(2)}%</b>`)}"></i>`).join("");
    const tip = `<b>${esc(t.name)}</b><br>Projected <b>${t.xpts.toFixed(1)}</b> pts · 80% range <b>${t.p10}–${t.p90}</b><br>Now <b>${t.points}</b> after ${t.played}`;
    const cells = cols.map(([k, , tone]) => {
      const v = t[k];
      const cls = v <= 0 ? "off" : tone === "warn" ? (v >= 10 ? "warn" : "") : tone === "lit" ? (v >= 1 ? "lit" : "") : tone;
      return `<td class="${cls}">${num(v)}</td>`;
    }).join("");
    const cut = cuts[rank] && rank < n ? `<tr class="cut ${cuts[rank][1]}"><td colspan="${span}"><span>${cuts[rank][0]}</span></td></tr>` : "";
    return `<tr class="row" data-i="${i}" aria-expanded="false" tabindex="0">
      <td class="rk l">${String(rank).padStart(2, "0")}</td>
      <td class="club l" title="${esc(t.full)}">${esc(t.name)}</td>
      <td>${t.played}</td><td class="b">${t.points}</td>
      <td class="${t.gd >= 0 ? "gd-pos" : "gd-neg"}">${t.gd > 0 ? "+" : ""}${t.gd}</td>
      <td data-tip="${esc(tip)}"><span class="rg"><span class="band" style="left:${x(t.p10)}%;width:${x(t.p90) - x(t.p10)}%"></span><span class="now" style="left:${x(t.points)}%"></span><span class="proj" style="left:${x(t.xpts)}%"></span></span>&nbsp; <b class="b">${Math.round(t.xpts)}</b></td>
      <td class="l"><span class="bulbs" style="--b:${size}px">${bulbs}</span></td>
      ${cells}
    </tr>${cut}`;
  }).join("");

  const table = $("table");
  table.innerHTML = `<thead><tr>
      <th class="rk l">#</th><th class="club l">Club</th><th>P</th><th>Pts</th><th>GD</th><th>Projected pts</th>
      <th class="l"><span class="bulb-head" style="--b:${size}px">${head}</span></th>
      ${cols.map(([, label]) => `<th>${label}</th>`).join("")}
    </tr></thead><tbody>${rows}</tbody>`;
  table.onclick = (e) => { const tr = e.target.closest("tr.row"); if (tr) toggleDetail(data, tr, span); };
  table.onkeydown = (e) => {
    const tr = e.target.closest("tr.row");
    if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); toggleDetail(data, tr, span); }
  };

  $("table-legend").textContent = ucl ? "League phase · projected" : "Projected table";
  const sample = [1, 5, 20, 50].map((p) => `<i style="background:${bulb(p, top)}"></i>`).join("");
  $("table-key").innerHTML = `
    <span><i class="k-range"></i>80% points range</span>
    <span><i class="k-proj"></i>Projected</span>
    <span><i class="k-now"></i>Now</span>
    <span><span class="k-bulbs">${sample}</span>Chance of each finishing place: brighter is likelier</span>
    <span>Tap a club for its full spread</span>`;
  $("table-note").textContent = ucl
    ? "Places 1–8 go straight to the round of 16, 9–24 enter the knockout play-offs and 25–36 are eliminated."
    : `Europe = places ${data.zones[1].from}–${data.zones[1].to}; the real Europa and Conference League spots also depend on cup winners.`
      + (n === 18 ? ` Down includes ${ordinal(bad.from)}, which goes to a relegation play-off.` : "");
}

function toggleDetail(data, tr, span) {
  const open = tr.getAttribute("aria-expanded") === "true";
  const next = tr.nextElementSibling;
  if (next && next.classList.contains("detail")) next.remove();
  tr.setAttribute("aria-expanded", String(!open));
  if (open) return;
  const t = data.teams[+tr.dataset.i];
  const bad = data.zones[data.zones.length - 1];
  const max = Math.max(...t.probs);
  const mode = t.probs.indexOf(max) + 1;
  const many = t.probs.length > 20;
  const bars = t.probs.map((p, j) => {
    const pos = j + 1;
    const label = !many || [1, 8, 9, 24, 25, 36].includes(pos) ? pos : "";
    return `<div class="col" data-tip="${esc(`<b>${esc(t.name)}</b> ${ordinal(pos)}: <b>${p.toFixed(2)}%</b>`)}">
      ${pos === mode ? `<span class="v">${Math.round(p)}</span>` : ""}
      <div class="bar" style="height:${((p / max) * 100).toFixed(1)}%${pos >= bad.from ? ";--c:var(--red)" : ""}"></div>
      <span class="x">${label}</span></div>`;
  }).join("");
  const row = document.createElement("tr");
  row.className = "detail";
  row.innerHTML = `<td colspan="${span}"><div class="det">
    <dl>
      <dt>Projected</dt><dd>${t.xpts.toFixed(1)} pts</dd>
      <dt>80% range</dt><dd>${t.p10}–${t.p90} pts</dd>
      <dt>Most likely</dt><dd>${ordinal(mode)} (${pct(max)})</dd>
      <dt>Average finish</dt><dd>${t.xpos.toFixed(1)}</dd>
    </dl>
    <div class="segs" role="img" aria-label="${esc(`${t.name}: chance of each finishing place`)}">${bars}</div>
  </div></td>`;
  tr.after(row);
}

/* ---------- Champions League extras ---------- */
function renderKnockouts(data) {
  const cols = [["r16", "Top 8"], ["round16", "Last 16"], ["quarterfinal", "Quarters"], ["semifinal", "Semis"], ["final", "Final"], ["title", "Win"]];
  const teams = [...data.teams].sort((a, b) => b.title - a.title || b.stages.final - a.stages.final).slice(0, 16);
  const value = (t, k) => (k in t.stages ? t.stages[k] : t[k]);
  const cell = (p, k) => {
    if (p <= 0) return `<td class="p off">–</td>`;
    if (k === "title") return `<td class="p lit">${num(p)}</td>`;
    const t = Math.min(1, Math.pow(p / 100, 0.7));
    return `<td class="p" style="color:color-mix(in srgb, var(--amber-t) ${Math.round(t * 100)}%, var(--dim))">${num(p)}</td>`;
  };
  $("ko-table").innerHTML = `<thead><tr><th class="rk l">#</th><th class="club l">Club</th>${cols.map(([, l]) => `<th>${l} %</th>`).join("")}</tr></thead>
    <tbody>${teams.map((t, i) => `<tr><td class="rk l">${String(i + 1).padStart(2, "0")}</td><td class="club l">${esc(t.name)}</td>
      ${cols.map(([k]) => cell(value(t, k), k)).join("")}</tr>`).join("")}</tbody>`;
}

function renderBracket(data) {
  const b = data.bracket;
  const champion = data.teams.find((t) => t.name === b.champion);
  const cols = STAGES.map(([stage, label]) => {
    const ties = (b.stages[stage] || []).map((tie) => {
      const side = (name) => {
        const win = name === tie.winner;
        return `<div class="tm ${win ? "win" : ""}"><span class="nm">${esc(name)}</span><em>${win ? Math.round(tie.advance) + "%" : ""}</em></div>`;
      };
      const tip = `<b>${esc(tie.winner)}</b> go through in <b>${tie.advance.toFixed(1)}%</b> of simulations of this tie`;
      return `<div class="tie" data-tip="${esc(tip)}">${side(tie.team1)}${side(tie.team2)}</div>`;
    }).join("");
    return `<div class="b-col"><h3>${label}</h3><div class="b-ties">${ties}</div></div>`;
  }).join("");
  $("bracket").innerHTML = cols + `<div class="b-col"><h3>Winner</h3><div class="champ">
    <div class="who-won">${esc(b.champion)}</div>
    ${champion ? `<div class="sub">${pct(champion.title)} to win across every draw</div>` : ""}</div></div>`;
  $("bracket-note").textContent = "One path through the knockouts: the most likely league-phase order, a permitted draw, and the favourite going through in every tie (the number is that tie's chance). Pairings are illustrative until the real draw.";
}

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
window.addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });

route();
