import { COMPS, $, dec, esc, getJSON } from "./core.js";

const share = (value, n) => n ? `${Math.round(100 * value / n)}%` : "–";
const signed = (value) => `${value < 0 ? "−" : "+"}${Math.abs(value).toFixed(3)}`;
const delta = (row, key = "frequency") => {
  const b = row.baselines[key];
  if (!b.n) return "–";
  const difference = b.model.log_loss - b.log_loss;
  return `<span class="${difference < 0 ? "sc-better" : ""}" title="Model minus ${key === "frequency" ? "prior frequency" : "Elo"}, same ${b.n} fixtures">${difference < 0 ? "▲ " : ""}${signed(difference)}</span>`;
};
let data;
let competition = "all";
let cohort = "combined";
const load = async () => data ||= await getJSON("scorecard.json");

/* with the xG lens, Called is the share of games with a clear xG winner (margin over 0.5) where it was the favourite */
const xgCalled = (row) => {
  const kinds = Object.values(row.misses.kinds);
  const won = sum(kinds.map(k => k.xg.won)), clear = won + sum(kinds.map(k => k.xg.lost));
  return clear ? share(won, clear) : "–";
};

export async function renderScorecardTable(lens = "score") {
  const frame = $("m-scorecard");
  try {
    const card = await load();
    const rows = COMPS.filter(c => card.competitions[c.slug]?.n).map(c => [c.label, card.competitions[c.slug]]);
    if (!card.all.n) { frame.hidden = true; return; }
    frame.hidden = false;
    const xg = lens === "xg" && card.all.misses;
    $("m-called-note").textContent = xg ? "Called on xG = share of games with a clear xG winner (by more than 0.5) where that side was the favourite; level games and games without xG are left out." : "Called = hit rate.";
    const line = (name, row, total = false) => `<tr${total ? ' class="total"' : ""}><td class="club l">${esc(name)}</td><td>${row.n}</td>
      <td class="lit">${dec(row.model.log_loss, 3)}</td><td>${delta(row)}</td><td>${dec(row.model.brier, 3)}</td>
      <td>${xg ? xgCalled(row) : share(row.called, row.n)}</td><td>${share(row.n_published, row.n)}</td></tr>`;
    $("m-record-table").innerHTML = `<thead><tr><th class="club l">Competition</th><th>Played</th><th>Log loss</th><th>vs baseline</th><th>Brier</th><th>${xg ? "Called on xG" : "Called"}</th><th>Published share</th></tr></thead>
      <tbody>${rows.map(([name, row]) => line(name, row)).join("")}${line("All", card.all, true)}</tbody>`;
    $("m-misses").hidden = !card.all.misses;
    if (card.all.misses) $("m-misses").innerHTML = `${esc(missLine(card.all))} <a href="#model/misses">How we miss →</a>`;
  } catch { frame.hidden = true; }
}

const axes = (y, ticks, label) => ticks.map(t => `<line class="sc-grid" x1="55" x2="565" y1="${y(t)}" y2="${y(t)}"/><text x="46" y="${y(t) + 4}" text-anchor="end">${label(t)}</text>`).join("");
const chart = (label, body) => `<svg viewBox="0 0 600 280" role="img" aria-label="${esc(label)}">${body}</svg>`;
const table = (headers, rows) => `<div class="scroll"><table class="board"><thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
const cells = values => `<tr>${values.map(v => `<td>${v}</td>`).join("")}</tr>`;

function reliability(row) {
  const x = p => 55 + p * 510, y = p => 235 - p * 210;
  const ticks = [0, .2, .4, .6, .8, 1];
  const bins = row.calibration.filter(b => b.n);
  const max = Math.max(1, ...bins.map(b => b.n));
  const body = axes(y, ticks, p => `${Math.round(p * 100)}%`)
    + ticks.map(p => `<line class="sc-grid" x1="${x(p)}" x2="${x(p)}" y1="25" y2="235"/><text x="${x(p)}" y="265" text-anchor="middle">${Math.round(p * 100)}%</text>`).join("")
    + `<path class="sc-diagonal" d="M${x(0)},${y(0)} L${x(1)},${y(1)}"/>`
    + bins.map(b => `<circle class="sc-dot" cx="${x(b.probability)}" cy="${y(b.observed)}" r="${3 + 9 * Math.sqrt(b.n / max)}"><title>Forecast ${dec(100 * b.probability, 1)}%; observed ${dec(100 * b.observed, 1)}%; ${b.n} outcome probabilities</title></circle>`).join("");
  return `<h3>Calibration</h3>${chart("Reliability: forecast probability horizontally, observed frequency vertically", body)}
    <p class="note">Ten bins pool all three outcomes (${3 * row.n} probabilities). Dot size reflects count; the diagonal is perfect calibration. Forecast chance →; observed frequency ↑.</p>
    <details><summary>Calibration counts</summary>${table(["Bin", "Count", "Forecast", "Observed"], row.calibration.map(b => cells([`${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%`, b.n, b.n ? `${dec(100 * b.probability, 1)}%` : "–", b.n ? `${dec(100 * b.observed, 1)}%` : "–"])))}</details>`;
}

function rolling(row) {
  const series = row.weekly;
  const keys = ["model", "frequency", "elo"].filter(k => series.some(p => p[k].n));
  const values = series.flatMap(p => keys.map(k => p[k].log_loss).filter(v => v != null));
  const low = Math.floor(Math.min(...values) * 10) / 10 - .1, high = Math.ceil(Math.max(...values) * 10) / 10 + .1;
  const x = i => 55 + i / Math.max(1, series.length - 1) * 510;
  const y = v => 235 - (v - low) / (high - low) * 210;
  const ticks = Array.from({ length: 5 }, (_, i) => low + (high - low) * i / 4);
  const body = axes(y, ticks, v => dec(v, 2))
    + keys.map(k => `<path class="sc-line sc-${k}" d="${series.map((p, i) => p[k].n ? `${series.slice(0, i).some(v => v[k].n) ? "L" : "M"}${x(i)},${y(p[k].log_loss)}` : "").join(" ")}"/>`).join("")
    + series.filter((_, i) => i === 0 || i === series.length - 1 || i % Math.ceil(series.length / 4) === 0).map(p => `<text x="${x(series.indexOf(p))}" y="265" text-anchor="middle">${esc(p.week.slice(5))}</text>`).join("");
  const last = series.at(-1);
  return `<h3>Cumulative log loss</h3>${chart("Cumulative mean log loss by Monday week: model solid, prior frequency dashed, Elo dotted", body)}
    <p class="note">From the season's first scored match through each Monday week (UTC). Model solid, prior frequency dashed, Elo dotted. Latest: ${keys.map(k => `${k === "frequency" ? "prior frequency" : k} ${dec(last[k].log_loss, 3)} (n=${last[k].n})`).join("; ")}. Lower is better; baseline coverage can differ.</p>
    <details><summary>Weekly scores and counts</summary>${table(["Monday week", ...keys.map(k => `${k === "frequency" ? "Prior frequency" : k} · n`)], series.map(p => cells([p.week, ...keys.map(k => `${dec(p[k].log_loss, 3)} · ${p[k].n}`)])))}</details>`;
}

/* "How we miss": calls against results, misses split by whole-game chances, outcome counts, goals, xG-scored log loss */
const OUTCOMES = ["Home win", "Draw", "Away win"];
const SPLIT = [["won", "won"], ["level", "level"], ["lost", "lost"], ["unknown"]];
const KINDS = [["draw", "Draws", "the favourite drew"], ["upset", "Upsets", "the favourite lost"], ["missed_draw_call", "Missed draw calls", "we called a draw"]];
const sum = values => values.reduce((a, b) => a + b, 0);
const kindN = (x, k) => sum(Object.values(x.kinds[k].xg));
const named = (headers, rows) => `<div class="scroll"><table class="board"><thead><tr>${headers.map((h, i) => `<th${i ? "" : ' class="l"'}>${h}</th>`).join("")}</tr></thead>
  <tbody>${rows.map(r => `<tr>${r.map((v, i) => `<td${i ? "" : ' class="l"'}>${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
const oneDec = value => `${value < 0 ? "−" : "+"}${Math.abs(value).toFixed(1)}`;

export function missLine(row) {
  const x = row.misses, up = x.kinds.upset.xg, upsets = kindN(x, "upset"), withXg = upsets - up.unknown, mdc = kindN(x, "missed_draw_call");
  return `Misses: ${kindN(x, "draw")} draws, ${upsets} upsets${mdc ? `, ${mdc} missed draw calls` : ""}`
    + (withXg ? `; the favourite won on chances in ${up.won} of ${withXg} upsets${withXg < upsets ? " with xG" : ""}.` : ".");
}

function misses(row) {
  const x = row.misses;
  if (!x || !row.n) return "";
  const n = row.n, called = kindN(x, "called"), missed = n - called;
  const unknown = sum(Object.values(x.kinds).map(k => k.xg.unknown));
  const coverage = unknown === n
    ? "None of these games has xG, so misses can't be split by chances."
    : `Observed xG covers ${n - unknown} of ${n} games${unknown ? `; the other ${unknown} show as no xG` : ""}.`;
  const calls = x.confusion.map(sum);
  const board = `<div class="scroll"><table class="board sc-confusion"><thead><tr><th class="l">Called ↓</th>${OUTCOMES.map(o => `<th>${o}</th>`).join("")}<th>Calls</th></tr></thead>
    <tbody>${x.confusion.map((r, i) => `<tr><td class="l">${OUTCOMES[i]}</td>${r.map((v, j) => `<td class="${i === j && v ? "lit" : ""}">${calls[i] ? `${v} <small>${share(v, calls[i])}</small>` : "–"}</td>`).join("")}<td class="b">${calls[i]}</td></tr>`).join("")}</tbody></table></div>
    <p class="note">Rows are the call, the single likeliest outcome; columns what happened. Small figures are shares of each row, and the lit diagonal is a call that came true.</p>`;
  const meter = ([key, label, gloss]) => {
    const k = x.kinds[key].xg, total = kindN(x, key);
    const shown = SPLIT.filter(([s]) => k[s]);
    return `<div class="sc-split-row"><span class="sc-split-lbl"><b>${total}</b> ${label}</span>
      <span class="sc-split-bar" aria-hidden="true">${shown.map(([s]) => `<i class="${s}" style="width:${(100 * k[s] / Math.max(1, missed)).toFixed(1)}%"></i>`).join("")}</span>
      <span class="note">${[gloss, total - k.unknown ? `on chances the favourite ${shown.filter(([s]) => s !== "unknown").map(([s, word]) => `${word} ${k[s]}`).join(" · ")}` : "",
        k.unknown ? `${k.unknown} without xG` : ""].filter(Boolean).join("; ")}</span></div>`;
  };
  const split = `<div class="key"><span><i class="sc-k won"></i>Favourite won on chances</span><span><i class="sc-k level"></i>Level, within 0.5 xG</span><span><i class="sc-k lost"></i>Favourite lost on chances</span><span><i class="sc-k unknown"></i>No xG</span></div>
    ${KINDS.filter(([k]) => k !== "missed_draw_call" || kindN(x, k)).map(meter).join("")}
    <p class="note">Bars share one scale, all ${missed} misses. The favourite is the likelier winner of the two sides; chances compare whole-game observed xG, Understat's for the leagues and ESPN's for the Champions League. ${esc(coverage)}</p>`;
  const counts = named(["Outcome", "Called", "Expected", "Actual", "Actual − expected"], OUTCOMES.map((o, i) =>
    [o, calls[i], dec(x.outcomes.expected[i], 1), x.outcomes.actual[i], oneDec(x.outcomes.actual[i] - x.outcomes.expected[i])]));
  const g = x.goals;
  const goals = g.team_games
    ? `<p class="sc-line">Goals per team-game, over the ${g.team_games / 2} games with xG: <b>${dec(g.predicted, 2)}</b> expected before kickoff, <b>${dec(g.goals, 2)}</b> scored, <b>${dec(g.xg, 2)}</b> xG. Mean absolute error <b>${dec(g.mae_goals, 2)}</b> against goals and <b>${dec(g.mae_xg, 2)}</b> against xG.</p>`
    : `<p class="note">No games with xG here, so no goals line.</p>`;
  const scored = Object.entries(x.xg_scored).filter(([, s]) => s.n);
  const names = { model: "Floodlight", elo: "Elo", frequency: "Prior frequency" };
  const diagnostic = scored.length ? `<h4>Diagnostic · xG-scored log loss</h4>
    ${named(["Forecast", "Games", "Log loss · result", "xG-scored"], scored.map(([k, s]) => [names[k], s.n, dec(s.real_log_loss, 3), dec(s.log_loss, 3)]))}
    <p class="note">xG-scored log loss scores the same forecasts against the on-chances chances (two independent Poissons with each side's observed xG as means) instead of the result, on each forecast's games with xG. It measures a different target and is shown only as a diagnostic: it never chooses or tunes the model, and log loss against the result stays the yardstick.</p>` : "";
  return `<h3>How we miss</h3>
    <p class="sc-line"><b>${called}</b> of ${n} calls came true (${share(called, n)}). Of the <b>${missed}</b> misses: ${KINDS.filter(([k]) => k !== "missed_draw_call" || kindN(x, k)).map(([k, label]) => `<b>${kindN(x, k)}</b> ${label.toLowerCase()}`).join(", ").replace(/, ([^,]*)$/, " and $1")}.</p>
    <div class="sc-pair"><div><h4>Called against result</h4>${board}</div><div><h4>The misses, by chances</h4>${split}</div></div>
    <div class="sc-pair"><div><h4>Expected against actual</h4>${counts}<p class="note">Expected counts add up each game's forecast chance of that outcome. A call needs the single likeliest outcome, so an outcome can be expected often and seldom called.</p></div>
    <div><h4>Goals</h4>${goals}</div></div>${diagnostic}`;
}

function renderTrackRecord() {
  const entry = competition === "all" ? data.all : data.competitions[competition];
  const row = cohort === "combined" ? entry : entry[cohort];
  $("sc-cohorts").innerHTML = ["combined", "published", "reconstructed"].map(k => `<button type="button" class="chip" data-cohort="${k}" aria-pressed="${k === cohort}">${k[0].toUpperCase() + k.slice(1)}<span>${k === "combined" ? entry.n : entry[k].n}</span></button>`).join("");
  $("sc-summary").innerHTML = table(["Forecasts", "n", "Log loss", "Brier", "RPS", "Called", "Exact score", "Avg chance given"], ["combined", "published", "reconstructed"].map(k => {
    const r = k === "combined" ? entry : entry[k];
    return cells([k, r.n, dec(r.model.log_loss, 3), dec(r.model.brier, 3), dec(r.model.rps, 3), share(r.called, r.n), share(r.exact, r.n), r.n ? `${dec(r.avg_chance_given * 100, 1)}%` : "–"]);
  }));
  $("sc-charts").innerHTML = row.n ? `<div>${reliability(row)}</div><div>${rolling(row)}</div>` : `<p class="note">No ${cohort} forecasts have finished yet.</p>`;
  $("misses").innerHTML = misses(row);
  const sources = competition === "all" ? Object.entries(data.competitions) : [[competition, entry]];
  $("sc-baselines").innerHTML = table(["Competition", "Frequency seasons", "History n", "Scored n", "Log loss", "vs frequency", "Elo n", "Elo log loss", "vs Elo"], sources.map(([slug, r]) => {
    const b = r.frequency_baseline, selected = cohort === "combined" ? r : r[cohort];
    return cells([esc(COMPS.find(c => c.slug === slug).label), b ? b.seasons.map(y => `${y}/${String(y + 1).slice(-2)}`).join(", ") : "Awaiting forecast export", b?.n ?? 0, selected.baselines.frequency.n, dec(selected.baselines.frequency.log_loss, 3), delta(selected), selected.baselines.elo.n, dec(selected.baselines.elo.log_loss, 3), delta(selected, "elo")]);
  }));
  $("sc-counts").textContent = `${row.n} ${cohort} finished forecasts; ${row.n_published} published before kickoff. Small samples are noisy. Scores cover 90 minutes; log loss uses natural logs, Brier sums three squared errors, and RPS averages the two cumulative errors in home/draw/away order.`;
}

export async function showTrackRecord() {
  const frame = $("scorecard");
  try {
    await load();
    frame.hidden = !Object.keys(data.competitions).length;
    if (frame.hidden) return;
    $("sc-competition").innerHTML = `<option value="all">All competitions</option>${COMPS.filter(c => data.competitions[c.slug]).map(c => `<option value="${c.slug}">${esc(c.label)}</option>`).join("")}`;
    $("sc-competition").value = competition;
    renderTrackRecord();
  } catch { frame.hidden = true; }
}

$("sc-competition").addEventListener("change", e => { competition = e.target.value; renderTrackRecord(); });
$("sc-cohorts").addEventListener("click", e => {
  const button = e.target.closest("[data-cohort]");
  if (button) { cohort = button.dataset.cohort; renderTrackRecord(); }
});
