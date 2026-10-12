// Tables view: the projected final table for one competition.
import { $, esc, nf, ordinal, num, pct, bulb, getJSON, setStatus } from "./core.js";
import { showRounds } from "./rounds.js";

const STAGES = [["playoffs", "Play-offs"], ["round16", "Round of 16"], ["quarterfinal", "Quarter-finals"], ["semifinal", "Semi-finals"], ["final", "Final"]];
let clubSlugs = new Set();
let current = null;

export async function showTables(slug) {
  current = slug;
  let data;
  try {
    [data] = await Promise.all([getJSON(`${slug}.json`), loadClubSlugs()]);
  } catch (err) {
    $("hero-in").innerHTML = `<div class="who"><h1>No signal</h1><p class="caption">This forecast could not be loaded (${esc(err.message)}).</p></div>`;
    $("status-text").textContent = "Offline";
    return;
  }
  if (current === slug) render(data);
}

async function loadClubSlugs() {
  try {
    const clubs = await getJSON("clubs.json");
    clubSlugs = new Set(clubs.clubs.map((c) => c.slug));
  } catch { /* profiles are optional here */ }
}

function render(data) {
  const ucl = data.kind === "ucl";
  document.title = `${data.name} forecast ${data.season} · Final Table`;
  setStatus(data.generated_at, data.data_cutoff);
  renderHero(data);
  renderRaces(data);
  renderTable(data);
  $("rounds-frame").hidden = !ucl;
  $("ko-frame").hidden = !ucl;
  $("bracket-frame").hidden = !ucl;
  if (ucl) {
    showRounds(data);
    renderKnockouts(data);
    renderBracket(data);
  }
}

function renderHero(data) {
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
    <div class="numeral on" role="img" aria-label="${esc(`${fav.name}: ${pct(fav.title)} chance`)}">${Math.round(fav.title)}<sup>%</sup></div>`;
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
  table.onclick = (e) => {
    if (e.target.closest("a")) return;
    const tr = e.target.closest("tr.row");
    if (tr) toggleDetail(data, tr, span);
  };
  table.onkeydown = (e) => {
    const tr = e.target.closest("tr.row");
    if (tr && e.target === tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); toggleDetail(data, tr, span); }
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
      + (n === 18 ? ` Down includes ${ordinal(bad.from)}, which goes to a relegation play-off.` : "")
      + fixtureNotes(data);
}

/* cancelled/awarded fixtures the model had to interpret, from the forecast metadata */
function fixtureNotes(data) {
  return (data.fixture_notes || []).map((f) => {
    const day = f.kickoff ? new Date(f.kickoff).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }) : "";
    const what = f.used_status === "FINISHED"
      ? `is counted as ${f.score} (${f.reason.replace(/^override: /, "")})`
      : "is simulated as if it will be replayed";
    return ` ${f.home} v ${f.away}${day ? ` (${day})` : ""} was reported ${f.reported_status.toLowerCase()} and ${what}.`;
  }).join("");
}

function toggleDetail(data, tr, span) {
  const open = tr.getAttribute("aria-expanded") === "true";
  const next = tr.nextElementSibling;
  if (next && next.classList.contains("detail")) next.remove();
  tr.setAttribute("aria-expanded", String(!open));
  if (open) return;
  const t = data.teams[+tr.dataset.i];
  const bad = data.zones[data.zones.length - 1];
  const row = document.createElement("tr");
  row.className = "detail";
  const profile = t.slug && clubSlugs.has(t.slug) ? `<a class="more" href="#clubs/${t.slug}">${esc(t.name)} club profile →</a>` : "";
  row.innerHTML = `<td colspan="${span}">${spreadPanel(t, bad.from, profile)}</td>`;
  tr.after(row);
}

/* finishing-place spread for one club: key numbers and one bar per place */
export function spreadPanel(t, dropFrom, extra = "") {
  const max = Math.max(...t.probs);
  const mode = t.probs.indexOf(max) + 1;
  const many = t.probs.length > 20;
  const bars = t.probs.map((p, j) => {
    const pos = j + 1;
    const label = !many || [1, 8, 9, 24, 25, 36].includes(pos) ? pos : "";
    return `<div class="col" data-tip="${esc(`<b>${esc(t.name)}</b> ${ordinal(pos)}: <b>${p.toFixed(2)}%</b>`)}">
      ${pos === mode ? `<span class="v">${Math.round(p)}</span>` : ""}
      <div class="bar" style="height:${((p / max) * 100).toFixed(1)}%${pos >= dropFrom ? ";--c:var(--red)" : ""}"></div>
      <span class="x">${label}</span></div>`;
  }).join("");
  return `<div class="det">
    <dl>
      <dt>Projected</dt><dd>${t.xpts.toFixed(1)} pts</dd>
      <dt>80% range</dt><dd>${t.p10}–${t.p90} pts</dd>
      <dt>Most likely</dt><dd>${ordinal(mode)} (${pct(max)})</dd>
      <dt>Average finish</dt><dd>${t.xpos.toFixed(1)}</dd>
    </dl>
    <div class="segs" role="img" aria-label="${esc(`${t.name}: chance of each finishing place`)}">${bars}</div>
    ${extra}
  </div>`;
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
