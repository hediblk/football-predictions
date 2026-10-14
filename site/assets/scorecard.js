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

export async function renderScorecardTable() {
  const frame = $("m-scorecard");
  try {
    const card = await load();
    const rows = COMPS.filter(c => card.competitions[c.slug]?.n).map(c => [c.label, card.competitions[c.slug]]);
    if (!card.all.n) { frame.hidden = true; return; }
    frame.hidden = false;
    const line = (name, row, total = false) => `<tr${total ? ' class="total"' : ""}><td class="club l">${esc(name)}</td><td>${row.n}</td>
      <td class="lit">${dec(row.model.log_loss, 3)}</td><td>${delta(row)}</td><td>${dec(row.model.brier, 3)}</td>
      <td>${share(row.called, row.n)}</td><td>${share(row.n_published, row.n)}</td></tr>`;
    $("m-record-table").innerHTML = `<thead><tr><th class="club l">Competition</th><th>Played</th><th>Log loss</th><th>vs baseline</th><th>Brier</th><th>Called</th><th>Published share</th></tr></thead>
      <tbody>${rows.map(([name, row]) => line(name, row)).join("")}${line("All", card.all, true)}</tbody>`;
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

function renderTrackRecord() {
  const entry = competition === "all" ? data.all : data.competitions[competition];
  const row = cohort === "combined" ? entry : entry[cohort];
  $("sc-cohorts").innerHTML = ["combined", "published", "reconstructed"].map(k => `<button type="button" class="chip" data-cohort="${k}" aria-pressed="${k === cohort}">${k[0].toUpperCase() + k.slice(1)}<span>${k === "combined" ? entry.n : entry[k].n}</span></button>`).join("");
  $("sc-summary").innerHTML = table(["Forecasts", "n", "Log loss", "Brier", "RPS", "Called", "Exact score", "Avg chance given"], ["combined", "published", "reconstructed"].map(k => {
    const r = k === "combined" ? entry : entry[k];
    return cells([k, r.n, dec(r.model.log_loss, 3), dec(r.model.brier, 3), dec(r.model.rps, 3), share(r.called, r.n), share(r.exact, r.n), r.n ? `${dec(r.avg_chance_given * 100, 1)}%` : "–"]);
  }));
  $("sc-charts").innerHTML = row.n ? `<div>${reliability(row)}</div><div>${rolling(row)}</div>` : `<p class="note">No ${cohort} forecasts have finished yet.</p>`;
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
