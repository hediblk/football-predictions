"use strict";

const COMPS = [
  { slug: "premier-league", short: "PL", long: "Premier League" },
  { slug: "la-liga", short: "LaLiga", long: "La Liga" },
  { slug: "bundesliga", short: "BL", long: "Bundesliga" },
  { slug: "serie-a", short: "Serie A", long: "Serie A" },
  { slug: "ligue-1", short: "L1", long: "Ligue 1" },
  { slug: "champions-league", short: "UCL", long: "Champions League" },
];
const ZONE_COLOR = {
  title: "var(--z-title)", ucl: "var(--z-ucl)", europe: "var(--z-europe)", releg: "var(--z-releg)",
  r16: "var(--z-ucl)", playoff: "var(--z-europe)", out: "var(--z-releg)",
};
const SLOTS = ["var(--s1)", "var(--s2)", "var(--s3)"];
const STAGE_LABEL = { playoffs: "Play-offs", round16: "Round of 16", quarterfinal: "Quarter-finals", semifinal: "Semi-finals", final: "Final" };

const $ = (id) => document.getElementById(id);
const cache = new Map();
let current = null;

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const ordinal = (n) => n + (["th", "st", "nd", "rd"][(n % 100 - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th");
const nf = new Intl.NumberFormat("en-US");

function pct(p, { digits = 0 } = {}) {
  if (p <= 0) return "–";
  if (p < 0.5 && digits === 0) return "<1%";
  if (p > 99.5 && p < 100) return ">99%";
  if (p >= 100) return ">99%";
  return p.toFixed(digits) + "%";
}
function pctWord(p) {
  if (p >= 99.5) return ">99%";
  if (p < 1) return p > 0 ? "<1%" : "0%";
  return Math.round(p) + "%";
}
function when(iso) {
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
}
function listNames(items) {
  if (items.length <= 1) return items.join("");
  return items.slice(0, -1).join(", ") + " and " + items[items.length - 1];
}

/* sequential blue ramp for the finishing-position heatmap; sqrt scale so small odds stay visible */
const RAMP = [[0, [27, 27, 31]], [0.22, [24, 79, 149]], [0.5, [57, 135, 229]], [1, [205, 226, 251]]];
function heat(p, top = 50) {
  const t = Math.min(1, Math.pow(Math.max(0, p) / top, 0.65));
  for (let i = 1; i < RAMP.length; i++) {
    const [t1, c1] = RAMP[i];
    const [t0, c0] = RAMP[i - 1];
    if (t <= t1) {
      const k = (t - t0) / (t1 - t0);
      return { bg: `rgb(${c0.map((v, j) => Math.round(v + (c1[j] - v) * k)).join(",")})`, dark: t > 0.72 };
    }
  }
  return { bg: "rgb(205,226,251)", dark: true };
}

function zoneOf(data, pos) {
  return data.zones.find((z) => pos >= z.from && pos <= z.to);
}

/* ---------- picker & routing ---------- */
function renderPicker(active) {
  $("picker").innerHTML = COMPS.map((c) => `
    <button type="button" data-slug="${c.slug}" aria-pressed="${c.slug === active}">
      <span class="long">${c.long}</span><span class="short">${c.short}</span>
    </button>`).join("");
}
$("picker").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-slug]");
  if (b) location.hash = b.dataset.slug;
});
window.addEventListener("hashchange", route);

function route() {
  const slug = location.hash.slice(1);
  const comp = COMPS.find((c) => c.slug === slug) || COMPS[0];
  renderPicker(comp.slug);
  load(comp.slug);
}

async function load(slug) {
  current = slug;
  if (!cache.has(slug)) {
    $("hero").innerHTML = `<div class="skeleton" style="grid-column:1/-1"></div>`;
    try {
      const res = await fetch(`data/${slug}.json`, { cache: "no-cache" });
      if (!res.ok) throw new Error(res.status);
      cache.set(slug, await res.json());
    } catch (err) {
      $("hero").innerHTML = `<p>Could not load this forecast (${esc(err.message)}).</p>`;
      return;
    }
  }
  if (current === slug) render(cache.get(slug));
}

/* ---------- page ---------- */
function render(data) {
  const ucl = data.kind === "ucl";
  document.title = `${data.name} forecast ${data.season} · Final Table`;
  $("intro").innerHTML = `
    <div class="crumb">${esc(data.country)} · ${esc(data.season)}</div>
    <h1>${esc(data.name)} predictions</h1>
    <p>Updated <b>${when(data.generated_at)}</b> · results through <b>${when(data.data_cutoff)}</b> ·
      ${data.played_fixtures} played, ${data.remaining_fixtures} to go${ucl ? " in the league phase" : ""} ·
      ${nf.format(data.n_sim)} simulated ${ucl ? "tournaments" : "seasons"}</p>`;
  $("foot-updated").textContent = `Forecast updated ${when(data.generated_at)}`;
  renderHero(data);
  renderRaces(data);
  renderTable(data);
  $("ko-card").hidden = !ucl;
  $("bracket-card").hidden = !ucl;
  if (ucl) {
    renderKnockouts(data);
    renderBracket(data);
  }
}

function renderHero(data) {
  const ucl = data.kind === "ucl";
  const byTitle = [...data.teams].sort((a, b) => b.title - a.title);
  const fav = byTitle[0];
  const runs = ucl ? "simulated tournaments" : "simulated seasons";
  const headline = ucl
    ? `${esc(fav.name)} lift the trophy in <em>${pctWord(fav.title)}</em> of ${nf.format(data.n_sim)} ${runs}.`
    : `${esc(fav.name)} win ${["Premier League", "Bundesliga"].includes(data.name) ? "the " : ""}${esc(data.name)} in <em>${pctWord(fav.title)}</em> of ${nf.format(data.n_sim)} ${runs}.`;

  const contenders = byTitle.filter((t) => t.title >= 5).slice(0, 3);
  let lede;
  if (ucl) {
    const top8 = data.teams.filter((t) => t.r16 >= 60).map((t) => t.name);
    lede = `It's wide open: ${listNames(byTitle.slice(0, 3).map((t) => `${esc(t.name)} (${pctWord(t.title)})`))} lead the way. `
      + `${top8.length ? `${listNames(top8.slice(0, 4).map(esc))} are the likeliest to skip the play-offs with a top-eight finish.` : ""}`;
  } else {
    const race = fav.title >= 75 ? "is close to decided" : fav.title >= 45 ? "has a clear favourite" : "is wide open";
    const ucl4 = data.teams.filter((t) => t.ucl > 15 && t.ucl < 95).sort((a, b) => b.ucl - a.ucl).slice(0, 3);
    const down = data.teams.filter((t) => t.releg >= 50).sort((a, b) => b.releg - a.releg);
    lede = `The title race ${race}: ${listNames(contenders.map((t) => `${esc(t.name)} (${pctWord(t.title)})`)) || esc(fav.name)}.`
      + (ucl4.length ? ` The Champions League chase runs through ${listNames(ucl4.map((t) => `${esc(t.name)} (${pctWord(t.ucl)})`))}.` : "")
      + (down.length ? ` At the bottom, ${listNames(down.map((t) => `${esc(t.name)} (${pctWord(t.releg)})`))} ${down.length > 1 ? "are" : "is"} more likely down than not.` : "");
  }

  const stats = ucl
    ? [[pctWord(fav.stages.final), `${fav.name} reach the final`], [pctWord(fav.r16), `${fav.name} finish top 8`], [data.remaining_fixtures, "league-phase games left"]]
    : [[fav.xpts.toFixed(0), `${fav.name} expected points`], [`${fav.p10}–${fav.p90}`, "80% points range"], [data.remaining_fixtures, "matches left"]];

  // 100 squares, allocated to contenders by largest remainder
  const shown = byTitle.slice(0, 3).filter((t) => t.title >= 1);
  const raw = shown.map((t) => t.title);
  const cells = raw.map(Math.floor);
  const otherPct = Math.max(0, 100 - raw.reduce((a, b) => a + b, 0));
  let left = 100 - cells.reduce((a, b) => a + b, 0) - Math.floor(otherPct);
  const rema = raw.map((v, i) => [v - cells[i], i]).sort((a, b) => b[0] - a[0]);
  for (const [, i] of rema) { if (left <= 0) break; cells[i]++; left--; }
  const squares = [];
  cells.forEach((n, i) => { for (let k = 0; k < n; k++) squares.push(i); });
  while (squares.length < 100) squares.push(-1);
  const waffle = squares.map((s, k) => {
    const team = s >= 0 ? shown[s] : null;
    const tip = team ? `<b>${esc(team.name)}</b> ${ucl ? "win" : "champions"} · ${pct(team.title, { digits: 1 })}` : `Any other club · ${pct(otherPct, { digits: 1 })}`;
    return `<i style="background:${s >= 0 ? SLOTS[s] : "var(--s-other)"};animation-delay:${k * 7}ms" data-tip="${esc(tip)}"></i>`;
  }).join("");
  const key = shown.map((t, i) => `<span><i style="background:${SLOTS[i]}"></i>${esc(t.name)} <b>${pct(t.title)}</b></span>`).join("")
    + `<span><i style="background:var(--s-other)"></i>Others <b>${pct(otherPct)}</b></span>`;

  $("hero").innerHTML = `
    <div>
      <h2>${headline}</h2>
      <p class="lede">${lede}</p>
      <div class="hero-stats">${stats.map(([v, l]) => `<div class="st"><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join("")}</div>
    </div>
    <div class="waffle-wrap">
      <div class="waffle" role="img" aria-label="${esc(`Title odds: ${shown.map((t) => `${t.name} ${pct(t.title)}`).join(", ")}, others ${pct(otherPct)}`)}">${waffle}</div>
      <div class="waffle-key">${key}</div>
      <div class="waffle-cap">100 squares, one per 1% of ${runs}, coloured by ${ucl ? "winner" : "champion"}.</div>
    </div>`;
}

function raceCard(title, note, color, rows, field, emptyText) {
  const items = rows.length
    ? `<ol>${rows.map((t) => `<li><span class="nm">${esc(t.name)}</span><span class="v">${pct(t[field])}</span>
        <span class="bar"><span style="width:${Math.max(1.5, t[field])}%;background:${color}"></span></span></li>`).join("")}</ol>`
    : `<p class="empty">${emptyText}</p>`;
  return `<article class="race"><h3><i style="background:${color}"></i>${title}</h3><p>${note}</p>${items}</article>`;
}

function renderRaces(data) {
  const t = data.teams;
  const between = (f, lo, hi) => t.filter((x) => x[f] >= lo && x[f] <= hi).sort((a, b) => b[f] - a[f]).slice(0, 6);
  let cards;
  if (data.kind === "ucl") {
    cards = [
      raceCard("Title odds", "Chance of lifting the trophy.", ZONE_COLOR.title, [...t].sort((a, b) => b.title - a.title).slice(0, 6), "title", ""),
      raceCard("Top-eight race", "Finish 1st–8th and go straight to the round of 16.", ZONE_COLOR.r16, between("r16", 15, 92), "r16", "No close races right now."),
      raceCard("Danger zone", "Finish 25th or lower and go out before the knockouts.", ZONE_COLOR.out, between("out", 10, 95), "out", "Nobody is in serious danger."),
    ];
  } else {
    const ucl = data.zones.find((z) => z.key === "ucl");
    const rel = data.zones.find((z) => z.key === "releg");
    const releg = t.filter((x) => x.releg >= 3).sort((a, b) => b.releg - a.releg).slice(0, 6);
    cards = [
      raceCard("Title race", "Chance of finishing first.", ZONE_COLOR.title, t.filter((x) => x.title >= 0.5).sort((a, b) => b.title - a.title).slice(0, 6), "title", ""),
      raceCard("Champions League", `Chance of a top-${ucl.to} finish.`, ZONE_COLOR.ucl, between("ucl", 4, 97), "ucl", "The top places look settled."),
      raceCard("Relegation fight", `Chance of finishing ${ordinal(rel.from)} or lower${rel.to - rel.from === 2 && data.teams.length === 18 ? " (16th enters a play-off)" : ""}.`, ZONE_COLOR.releg, releg, "releg", "Nobody is in serious danger."),
    ];
  }
  $("races").innerHTML = cards.join("");
}

/* ---------- main table ---------- */
function probCell(p, zone) {
  if (p <= 0) return `<span class="pc nil">–</span>`;
  const alpha = Math.round(8 + Math.min(1, p / 100) * 52);
  return `<span class="pc" style="background:color-mix(in srgb, ${ZONE_COLOR[zone]} ${alpha}%, transparent);color:var(--ink)">${pct(p)}</span>`;
}

function renderTable(data) {
  const ucl = data.kind === "ucl";
  const n = data.teams.length;
  const cw = ucl ? 13 : 20;
  const top = Math.min(50, Math.max(...data.teams.flatMap((t) => t.probs)));
  const cuts = ucl ? new Set([9, 25]) : new Set();
  const lo = Math.min(...data.teams.map((t) => Math.min(t.points, t.p10)));
  const hi = Math.max(...data.teams.map((t) => t.p90));
  const x = (v) => ((v - lo) / Math.max(1, hi - lo)) * 100;
  const zoneCols = ucl
    ? [["r16", "Top 8"], ["playoff", "Play-off"], ["out", "Out"]]
    : [["title", "Title"], ["ucl", `Top ${data.zones[0].to}`], ["europe", "Europe"], ["releg", "Down"]];

  const heatHead = Array.from({ length: n }, (_, i) => {
    const pos = i + 1;
    const z = zoneOf(data, pos);
    const label = ucl ? ([1, 8, 9, 24, 25, 36].includes(pos) ? pos : "") : pos;
    return `<span class="${cuts.has(pos) ? "cut" : ""}" style="${z ? `border-bottom-color:${ZONE_COLOR[z.key]}` : ""}">${label}</span>`;
  }).join("");

  const head = `<thead><tr>
    <th class="c-rank l">#</th><th class="c-club l">Club</th>
    <th title="Matches played">P</th><th title="Current points">Pts</th><th title="Goal difference">GD</th>
    <th class="l">Projected points</th>
    <th class="l c-heat"><div class="heat-head" style="--cw:${cw}px">${heatHead}</div></th>
    ${zoneCols.map(([k, l]) => `<th><span class="zone-head"><i style="background:${ZONE_COLOR[k]}"></i>${l}</span></th>`).join("")}
  </tr></thead>`;

  const cutAfter = ucl
    ? { 8: ["▲ Round of 16 · ▼ Knockout play-offs", "var(--z-ucl)"], 24: ["▲ Knockout play-offs · ▼ Eliminated", "var(--z-releg)"] }
    : {
      [data.zones[0].to]: ["▲ Champions League places", "var(--z-ucl)"],
      [data.zones.find((z) => z.key === "releg").from - 1]: ["▼ Relegation zone", "var(--z-releg)"],
    };
  const span = 6 + 1 + zoneCols.length;

  const rows = data.teams.map((t, i) => {
    const rank = i + 1;
    const cells = t.probs.map((p, j) => {
      const pos = j + 1;
      const h = heat(p, top);
      const lbl = !ucl && p >= 9.5 ? Math.round(p) : "";
      const tip = `<b>${esc(t.name)}</b> finish ${ordinal(pos)}: <b>${p > 0 && p < 0.01 ? "<0.01%" : p.toFixed(2) + "%"}</b>`;
      return `<i class="${lbl ? (h.dark ? "lbl dark" : "lbl") : ""}${cuts.has(pos) ? " cut" : ""}" style="background:${h.bg}" data-tip="${esc(tip)}">${lbl}</i>`;
    }).join("");
    const gd = t.gd > 0 ? `+${t.gd}` : t.gd;
    const rangeTip = `<b>${esc(t.name)}</b><br>Expected <b>${t.xpts.toFixed(1)}</b> pts · 80% range <b>${t.p10}–${t.p90}</b><br>Now <b>${t.points}</b> pts after ${t.played} games`;
    const row = `<tr class="row" data-i="${i}" aria-expanded="false" tabindex="0">
      <td class="c-rank l">${rank}</td>
      <td class="c-club l" title="${esc(t.full)}">${esc(t.name)}</td>
      <td>${t.played}</td><td class="c-pts"><b>${t.points}</b></td>
      <td class="c-gd ${t.gd > 0 ? "pos" : t.gd < 0 ? "neg" : ""}">${gd}</td>
      <td class="l"><span class="pr" data-tip="${esc(rangeTip)}"><span class="range">
        <span class="band" style="left:${x(t.p10)}%;width:${x(t.p90) - x(t.p10)}%"></span>
        <span class="now" style="left:${x(t.points)}%"></span>
        <span class="dot" style="left:${x(t.xpts)}%"></span></span><b>${t.xpts.toFixed(0)}</b></span></td>
      <td class="l c-heat"><div class="heat" style="--cw:${cw}px">${cells}</div></td>
      ${zoneCols.map(([k]) => `<td>${probCell(t[k], k)}</td>`).join("")}
    </tr>`;
    const cut = cutAfter[rank] && rank < n
      ? `<tr class="cutline" style="color:${cutAfter[rank][1]}"><td colspan="${span}">${cutAfter[rank][0]}</td></tr>` : "";
    return row + cut;
  }).join("");

  const table = $("table");
  table.innerHTML = head + `<tbody>${rows}</tbody>`;
  table.onclick = (e) => { const tr = e.target.closest("tr.row"); if (tr) toggleDetail(data, tr, span); };
  table.onkeydown = (e) => {
    const tr = e.target.closest("tr.row");
    if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); toggleDetail(data, tr, span); }
  };

  $("table-title").textContent = ucl ? "League phase projection" : "Projected table";
  $("table-sub").textContent = ucl
    ? "Clubs ordered by average simulated league-phase finish. Each square is the chance of finishing in that place. Tap a club for its full distribution."
    : "Clubs ordered by average simulated finish. Each square is the chance of finishing in that place. Tap a club for its full distribution.";
  $("table-legend").innerHTML = `
    <span><i class="lg-dot"></i>Expected points</span>
    <span><i class="lg-range"></i>80% range</span>
    <span><i class="lg-now"></i>Points now</span>
    <span><i style="background:linear-gradient(90deg,#1b1b1f,#184f95,#3987e5,#cde2fb);width:40px"></i>Finish chance</span>`;
  const rel = data.zones.find((z) => z.key === "releg");
  $("table-note").textContent = ucl
    ? "Places 1–8 go straight to the round of 16, 9–24 enter the knockout play-offs and 25–36 are eliminated."
    : `“Europe” covers places ${data.zones[1].from}–${data.zones[1].to}; actual Europa and Conference League spots also depend on cup winners.`
      + (n === 18 ? ` “Down” includes ${ordinal(rel.from)} place, which goes to a relegation play-off.` : "");
}

function toggleDetail(data, tr, span) {
  const open = tr.getAttribute("aria-expanded") === "true";
  const next = tr.nextElementSibling;
  if (next && next.classList.contains("detail")) next.remove();
  tr.setAttribute("aria-expanded", String(!open));
  if (open) return;
  const t = data.teams[+tr.dataset.i];
  const max = Math.max(...t.probs);
  const mode = t.probs.indexOf(max) + 1;
  const bars = t.probs.map((p, j) => {
    const z = zoneOf(data, j + 1);
    const color = z ? ZONE_COLOR[z.key] : "#55555d";
    const showX = data.teams.length <= 20 || [1, 8, 9, 24, 25, 36].includes(j + 1);
    return `<div class="col" data-tip="${esc(`<b>${esc(t.name)}</b> finish ${ordinal(j + 1)}: <b>${p.toFixed(2)}%</b>`)}">
      ${j + 1 === mode ? `<span class="v">${Math.round(p)}%</span>` : ""}
      <div class="b" style="height:${(p / max) * 100}%;background:${color};opacity:${p > 0 ? 1 : 0}"></div>
      <span class="x">${showX ? j + 1 : "&nbsp;"}</span></div>`;
  }).join("");
  const stats = [
    [t.xpts.toFixed(1), "expected points"],
    [`${t.p10}–${t.p90}`, "80% points range"],
    [ordinal(mode), `most likely finish (${pct(max)})`],
    [t.xpos.toFixed(1), "average finish"],
  ];
  const row = document.createElement("tr");
  row.className = "detail";
  row.innerHTML = `<td colspan="${span}"><div class="det">
    <div class="det-stats">${stats.map(([v, l]) => `<div><b>${v}</b><span>${l}</span></div>`).join("")}</div>
    <div class="det-chart" role="img" aria-label="${esc(`${t.name} finishing position distribution`)}">${bars}</div>
  </div></td>`;
  tr.after(row);
}

/* ---------- knockouts ---------- */
function renderKnockouts(data) {
  const cols = [["r16", "Top 8", "r16"], ["round16", "Last 16", "s"], ["quarterfinal", "Quarters", "s"], ["semifinal", "Semis", "s"], ["final", "Final", "s"], ["title", "Win", "title"]];
  const teams = [...data.teams].sort((a, b) => b.title - a.title || b.stages.final - a.stages.final).slice(0, 16);
  const cell = (p, color) => {
    if (p <= 0) return `<span class="pc nil">–</span>`;
    const alpha = Math.round(6 + Math.min(1, p / 100) * 56);
    return `<span class="pc" style="background:color-mix(in srgb, ${color} ${alpha}%, transparent)">${pct(p)}</span>`;
  };
  $("ko-table").innerHTML = `<thead><tr><th class="c-rank l">#</th><th class="c-club l">Club</th>
    ${cols.map(([, l]) => `<th>${l}</th>`).join("")}</tr></thead><tbody>
    ${teams.map((t, i) => `<tr><td class="c-rank l">${i + 1}</td><td class="c-club l">${esc(t.name)}</td>
      ${cols.map(([k, , kind]) => {
        const p = kind === "s" ? t.stages[k] : t[k];
        return `<td class="c-stage">${cell(p, k === "title" ? "var(--z-title)" : "var(--z-ucl)")}</td>`;
      }).join("")}</tr>`).join("")}
    </tbody>`;
}

function renderBracket(data) {
  const b = data.bracket;
  const champion = data.teams.find((t) => t.name === b.champion);
  const cols = ["playoffs", "round16", "quarterfinal", "semifinal", "final"].map((stage) => {
    const ties = (b.stages[stage] || []).map((tie) => {
      const side = (name) => {
        const win = name === tie.winner;
        return `<div class="tm ${win ? "win" : "lose"}"><span class="nm">${esc(name)}</span><em>${win ? tie.advance.toFixed(0) + "%" : ""}</em></div>`;
      };
      const tip = `<b>${esc(tie.winner)}</b> advance in <b>${tie.advance.toFixed(1)}%</b> of simulations of this tie`;
      return `<div class="tie" data-tip="${esc(tip)}">${side(tie.team1)}${side(tie.team2)}</div>`;
    }).join("");
    return `<div class="b-col"><h4>${STAGE_LABEL[stage]}</h4><div class="b-ties">${ties}</div></div>`;
  }).join("");
  $("bracket").innerHTML = cols + `<div class="b-col"><h4>Champion</h4><div class="champ"><div class="champ-card">
    <div class="cup" aria-hidden="true">🏆</div><b>${esc(b.champion)}</b>
    ${champion ? `<span>${pct(champion.title, { digits: 1 })} to win overall</span>` : ""}</div></div></div>`;
  $("bracket-sub").textContent = "One projected path: the most likely league-phase order, a permitted draw, and the favourite advancing in every tie (percentages are each tie's advance chance). Pairings are illustrative until the real draw; the title odds above average over every simulated draw.";
}

/* ---------- tooltip ---------- */
const tip = $("tip");
let tipTimer;
function showTip(el, x, y) {
  tip.innerHTML = el.dataset.tip;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  const left = Math.min(window.innerWidth - r.width - 8, Math.max(8, x + 14));
  const top = y - r.height - 12 < 8 ? y + 18 : y - r.height - 12;
  tip.style.left = left + "px";
  tip.style.top = top + "px";
}
document.addEventListener("mousemove", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  if (el) showTip(el, e.clientX, e.clientY);
  else tip.hidden = true;
});
document.addEventListener("touchstart", (e) => {
  const el = e.target.closest && e.target.closest("[data-tip]");
  if (!el) { tip.hidden = true; return; }
  const t = e.touches[0];
  showTip(el, t.clientX, t.clientY);
  clearTimeout(tipTimer);
  tipTimer = setTimeout(() => { tip.hidden = true; }, 2500);
}, { passive: true });
window.addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });

route();
