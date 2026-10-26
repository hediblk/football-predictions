import { $, esc, getJSON, setStatus } from "./core.js";
import { decodeSeason, normalizeStrategy, encodeStrategy, decodeStrategy } from "./backtest-engine.js";

const leagues = { PL: "Premier League", PD: "La Liga", BL1: "Bundesliga", SA: "Serie A", FL1: "Ligue 1" };
const slugs = { PL: "premier-league", PD: "la-liga", BL1: "bundesliga", SA: "serie-a", FL1: "ligue-1" };
const picks = { model_favourite: "Model favourite", market_favourite: "Market favourite", edge: "Best edge", disagreement: "Model / market disagreement", home: "Home win", draw: "Draw", away: "Away win" };
const methods = { flat: "Flat stake", fraction: "Fixed bankroll fraction", probability: "By model probability", edge: "By edge", kelly: "Kelly", to_win: "To win" };
const books = { bet365: "Bet365", avg: "Market average · benchmark", max: "Market maximum · optimistic benchmark", betfair_exchange: "Betfair exchange", pinnacle: "Pinnacle", betfair: "Betfair sportsbook", betfred: "Betfred", betvictor: "BetVictor", bwin: "bwin", paddypower: "Paddy Power", skybet: "Sky Bet", williamhill: "William Hill", ladbrokes: "Ladbrokes", interwetten: "Interwetten", "1xbet": "1xBet", betmgm: "BetMGM", betway: "Betway" };
const fields = { p: ["Model probability (%)", 100], edge: ["Expected return (%)", 100], gap: ["Model − market (probability points)", 100], price: ["Price (decimal odds)", 1], xg_diff: ["Expected goals · side minus opponent", 1], xg_total: ["Expected goals · total", 1], rating_gap: ["Strength rating gap (points)", 1], elo_agrees: ["Elo agrees", 1], stakes: ["Stakes tag", 1] };
const fmt = (x, digits = 1) => x == null ? "Unavailable" : Number(x).toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const pct = (x) => x == null ? "Unavailable" : `${fmt(x * 100)}%`;
const units = (x) => `${fmt(x)} u`;
const seasonName = (year) => `${year}/${String(Number(year) + 1).slice(-2)}`;
const options = (map) => Object.entries(map).map(([key, label]) => `<option value="${esc(key)}">${esc(label)}</option>`).join("");
const select = (id, label, map, multi = false) => `<label>${label}<select id="bt-${id}" ${multi ? 'multiple size="3"' : ""}>${options(map)}</select></label>`;
const input = (id, label, value, min = 0, max = "", step = "any") => `<label>${label}<input id="bt-${id}" type="number" value="${value}" min="${min}" ${max !== "" ? `max="${max}"` : ""} step="${step}" required></label>`;
let files = [], rows = [], manifest, loadPromise, worker, timer, generation = 0, current, output, page = 0;
let matchLinks = new Set();

function shell() {
  $("view-backtest").innerHTML = `
    <fieldset class="frame bt-strategy"><legend>Backtest · Strategy</legend>
      <p class="note">The model does not beat the market in these historical baseline strategies. Presets are examples, not winning strategies.</p>
      <details id="bt-editor" open><summary id="bt-strategy-summary">Configure a strategy</summary>
      <form id="bt-form">
        <div class="chips bt-presets" role="group" aria-label="Example strategies">${[["model", "Model favourite"], ["market", "Market favourite"], ["value", "Edge ≥5%"], ["kelly", "¼ Kelly · edge ≥5%"]].map(([id, text]) => `<button class="chip" type="button" data-preset="${id}">${text}</button>`).join("")}</div>
        <div class="bt-controls">
          ${select("pick", "Selection · 90-minute 1X2", picks)}
          ${select("method", "Staking method", methods)}
          ${select("book", "Bookmaker / price source", books)}
          ${select("timing", "Price timing", { pre: "Pre-closing", close: "Closing" })}
        </div>
        <p id="bt-timing-note" class="note">Published forecasts require closing execution. No price or timing is substituted when missing.</p>
        <details id="bt-advanced"><summary>Universe, conditions & stake settings</summary>
          <h2>Universe</h2><p class="note">No selection means all available. Use Ctrl / ⌘ to select several leagues or seasons.</p>
          <div class="bt-controls">
            ${select("comp", "Leagues", leagues, true)}${select("season", "Seasons", {}, true)}
            ${select("forecast", "Forecast provenance", { replayed: "Replayed · standalone", published: "Published before kickoff" })}
            ${select("include", "Include teams · known IDs only", {}, true)}${select("exclude", "Exclude teams · known IDs only", {}, true)}
            ${select("venue", "Included team's venue", { any: "Any venue", home: "Home", away: "Away" })}
            <label class="bt-check"><input id="bt-team-side" type="checkbox">Bet only on an included team</label>
            <label>Rounds · inclusive, blank = all<input id="bt-rounds" placeholder="e.g. 10, 38" inputmode="numeric"></label>
            <label>Months · 1–12, blank = all<input id="bt-months" placeholder="e.g. 4, 5" inputmode="numeric"></label>
            <label>UTC weekdays · Mon 0 to Sun 6<input id="bt-weekdays" placeholder="e.g. 1, 2, 3" inputmode="numeric"></label>
          </div>
          <h2>Conditions · all must hold</h2><p class="note">Unknown evidence fails a condition. Expected goals are pre-match estimates; observed xG never selects a bet. For draws, side differences use the absolute home–away gap.</p>
          <div id="bt-conditions"></div><button id="bt-add-condition" class="chip" type="button">Add condition</button>
          <h2>Stake settings</h2><div class="bt-controls">
            ${input("unit", "Base stake / target profit (units)", 1, .001)}
            ${input("bankroll", "Starting bankroll per season (units)", 100, .001)}
            ${input("fraction", "Bankroll fraction / Kelly multiplier (0–1)", .01, .0001, 1)}
            ${input("cap", "Per-bet bankroll cap (0–1)", .03, .0001, 1)}
            ${input("daily-cap", "Batch exposure cap (0–1)", 1, .0001, 1)}
            ${input("trust", "Kelly model trust (0–1)", 1, 0, 1)}
            ${input("commission", "Commission on net winnings (%)", 0, 0, 99.99)}
          </div>
          <label id="bt-bands-label">Optional probability bands · probability fractions and units (JSON)<textarea id="bt-bands" rows="2" placeholder='[{"min":0.5,"max":1,"stake":1}]'></textarea></label>
          <p id="bt-stake-note" class="note"></p>
        </details>
        <div class="bt-actions"><button class="chip" id="bt-run" type="submit">Run backtest</button><button class="chip" id="bt-reset" type="button">Reset strategy</button><a id="bt-share" class="chip" href="#backtest">Strategy link</a></div>
      </form></details>
      <p id="bt-status" class="note" role="status" aria-live="polite" data-state="loading">Loading available seasons…</p>
    </fieldset>
    <div id="bt-results" hidden></div>`;
  $("bt-form").addEventListener("submit", (event) => { event.preventDefault(); schedule(true); });
  $("bt-form").addEventListener("input", () => schedule());
  $("bt-form").addEventListener("change", (event) => {
    if (event.target.id === "bt-method") $("bt-fraction").value = event.target.value === "kelly" ? .25 : .01;
    if (event.target.id === "bt-book") $("bt-commission").value = event.target.value === "betfair_exchange" ? 2 : 0;
    syncControls(); schedule();
  });
  $("bt-add-condition").onclick = () => { addCondition(); schedule(); };
  $("bt-reset").onclick = () => { fill(normalizeStrategy({})); schedule(); };
  document.querySelectorAll("[data-preset]").forEach((button) => {
    button.onclick = () => {
      const key = button.dataset.preset;
      fill(normalizeStrategy({ rule: { pick: key === "market" ? "market_favourite" : ["value", "kelly"].includes(key) ? "edge" : "model_favourite", conditions: ["value", "kelly"].includes(key) ? [{ field: "edge", op: ">=", value: .05 }] : [] }, stake: { method: key === "kelly" ? "kelly" : "flat" } }));
      schedule();
    };
  });
}

function addCondition(condition = { field: "edge", op: ">=", value: .05 }) {
  const row = document.createElement("div"); row.className = "bt-condition";
  row.innerHTML = `<label>Measure<select class="bt-field">${options(Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v[0]])))}</select></label>
    <label>Operator<select class="bt-op">${options({ ">=": "≥", ">": ">", "<=": "≤", "<": "<", "==": "=", "!=": "≠", between: "Between (inclusive)" })}</select></label>
    <label>Value<input class="bt-value" required></label><button type="button" class="chip bt-remove" aria-label="Remove condition">Remove</button>`;
  row.querySelector(".bt-field").value = condition.field;
  row.querySelector(".bt-op").value = condition.op;
  const displayValue = (value) => typeof value === "boolean" ? String(value) : value * fields[condition.field][1];
  row.querySelector(".bt-value").value = Array.isArray(condition.value) ? condition.value.map(displayValue).join(", ") : displayValue(condition.value);
  const hints = () => {
    const bool = ["stakes", "elo_agrees"].includes(row.querySelector(".bt-field").value);
    const op = row.querySelector(".bt-op");
    [...op.options].forEach((option) => { option.disabled = bool && !["==", "!="].includes(option.value); });
    if (bool && !["==", "!="].includes(op.value)) op.value = "==";
    row.querySelector(".bt-value").placeholder = bool ? "true or false" : op.value === "between" ? "e.g. 40, 60" : "Number in the labelled unit";
  };
  row.querySelector(".bt-field").onchange = () => { if (["stakes", "elo_agrees"].includes(row.querySelector(".bt-field").value)) row.querySelector(".bt-value").value = "true"; hints(); };
  row.querySelector(".bt-op").onchange = hints;
  row.querySelector(".bt-remove").onclick = () => { row.remove(); $("bt-add-condition").focus(); schedule(); };
  hints(); $("bt-conditions").append(row);
}

function selected(id, numeric = false) { return [...$(id).selectedOptions].map((option) => numeric ? Number(option.value) : option.value); }
function list(id) {
  const value = $(id).value.trim();
  if (!value) return [];
  const values = value.split(",").map((v) => v.trim() === "" ? NaN : Number(v));
  if (values.some((v) => !Number.isFinite(v))) throw new Error("Use comma-separated numbers for rounds, months and weekdays.");
  return values;
}
function read() {
  if (!$("bt-form").checkValidity()) throw new Error("Complete the highlighted numeric fields within their labelled limits.");
  const conditions = [...document.querySelectorAll(".bt-condition")].map((row) => {
    const field = row.querySelector(".bt-field").value, op = row.querySelector(".bt-op").value;
    const raw = row.querySelector(".bt-value").value.trim();
    let value;
    if (["stakes", "elo_agrees"].includes(field)) {
      if (!["true", "false"].includes(raw)) throw new Error("Stakes and Elo conditions need true or false.");
      value = raw === "true";
    } else {
      const parse = (v) => v.trim() === "" ? NaN : Number(v) / fields[field][1];
      value = op === "between" ? raw.split(",").map(parse) : parse(raw);
      const values = Array.isArray(value) ? value : [value];
      if (field === "p" && values.some((v) => v < 0 || v > 1)) throw new Error("Model probability must be between 0% and 100%.");
      if (field === "price" && values.some((v) => v <= 1)) throw new Error("Decimal prices must be greater than 1.");
    }
    return { field, op, value };
  });
  return normalizeStrategy({
    universe: { comps: selected("bt-comp"), seasons: selected("bt-season", true), forecast: $("bt-forecast").value, include: selected("bt-include", true), exclude: selected("bt-exclude", true), venue: $("bt-venue").value, team_side: $("bt-team-side").checked, matchdays: list("bt-rounds"), months: list("bt-months"), weekdays: list("bt-weekdays") },
    rule: { pick: $("bt-pick").value, conditions },
    stake: { method: $("bt-method").value, unit: +$("bt-unit").value, fraction: +$("bt-fraction").value, cap: +$("bt-cap").value, daily_cap: +$("bt-daily-cap").value, trust: +$("bt-trust").value, bands: $("bt-bands").value.trim() ? JSON.parse($("bt-bands").value) : null },
    execution: { book: $("bt-book").value, timing: $("bt-timing").value, commission: +$("bt-commission").value / 100 }, bankroll: +$("bt-bankroll").value,
  });
}
function fill(s) {
  const values = { pick: s.rule.pick, method: s.stake.method, book: s.execution.book, timing: s.execution.timing, forecast: s.universe.forecast, venue: s.universe.venue, rounds: s.universe.matchdays.join(", "), months: s.universe.months.join(", "), weekdays: s.universe.weekdays.join(", "), unit: s.stake.unit, bankroll: s.bankroll, fraction: s.stake.fraction, cap: s.stake.cap, "daily-cap": s.stake.daily_cap, trust: s.stake.trust, commission: s.execution.commission * 100, bands: s.stake.bands ? JSON.stringify(s.stake.bands) : "" };
  Object.entries(values).forEach(([key, value]) => { $(`bt-${key}`).value = value; });
  for (const [key, values] of Object.entries({ comp: s.universe.comps, season: s.universe.seasons, include: s.universe.include, exclude: s.universe.exclude })) {
    const el = $(`bt-${key}`);
    values.forEach((value) => { if (![...el.options].some((o) => o.value === String(value))) el.add(new Option(`${value} · unavailable in loaded data`, value)); });
    [...el.options].forEach((option) => { option.selected = values.map(String).includes(option.value); });
  }
  $("bt-team-side").checked = s.universe.team_side;
  $("bt-conditions").innerHTML = ""; s.rule.conditions.forEach(addCondition);
  syncControls();
}
function syncControls() {
  const published = $("bt-forecast").value === "published", pre = $("bt-timing").value === "pre";
  $("bt-timing").querySelector('[value="pre"]').disabled = published;
  $("bt-forecast").querySelector('[value="published"]').disabled = pre;
  $("bt-timing-note").textContent = pre ? "Published forecasts require closing execution: choose Closing first. Missing prices never fall back to another book or timing." : "Closing execution supports replayed or published forecasts. No later price exists for closing-line value.";
  const included = selected("bt-include").length > 0;
  $("bt-venue").disabled = !included; $("bt-team-side").disabled = !included;
  const method = $("bt-method").value, relative = ["kelly", "fraction"].includes(method);
  ["fraction", "cap", "daily-cap"].forEach((key) => { $(`bt-${key}`).disabled = !relative; });
  $("bt-trust").disabled = method !== "kelly";
  $("bt-bands-label").hidden = method !== "probability";
  $("bt-stake-note").textContent = relative ? "Bankroll resets each season. Pre-closing bets share their forecast-date starting balance; closing bets use their UTC match-day balance. Caps scale the whole batch. Kelly trust blends model and market only for sizing." : "Unit-return reference: no finite-bankroll constraint. Probability = base × p / 0.5; edge = base × positive edge / 0.05; to win = target / net decimal profit. Probability alone cannot establish value.";
}
function status(state, message) { $("bt-status").dataset.state = state; $("bt-status").textContent = message; $("bt-results").setAttribute("aria-busy", String(state === "loading")); }
function schedule(explicit = false) {
  clearTimeout(timer); worker?.terminate(); generation += 1;
  $("bt-results").hidden = true;
  status("loading", "Updating strategy…");
  timer = setTimeout(() => run(explicit), explicit ? 0 : 300);
}
function run(explicit) {
  let strategy;
  try { strategy = read(); } catch (error) { status("invalid", error.message); return; }
  current = strategy;
  const hash = encodeStrategy(strategy); history.replaceState(null, "", hash); $("bt-share").href = hash;
  $("bt-strategy-summary").textContent = `${picks[strategy.rule.pick]} · ${methods[strategy.stake.method]} · ${books[strategy.execution.book]} · ${strategy.execution.timing === "pre" ? "pre-closing" : "closing"}`;
  if (!files.length) { status("unavailable", "Historical prices are not publicly available. Publication permission is unresolved; no backtest results are shown. Your strategy link can still be shared."); return; }
  if (strategy.universe.seasons.some((year) => !files.some((file) => file.season === year))) { status("unavailable", "A season in this strategy is unavailable. Choose only loaded seasons; no partial result is substituted."); return; }
  const ticket = generation;
  status("loading", "Calculating strategy and 2,000 match-date bootstrap samples…");
  const url = new URL("./backtest-worker.js", import.meta.url); url.search = new URL(import.meta.url).search;
  worker = new Worker(url, { type: "module" });
  worker.onmessage = ({ data }) => {
    if (ticket !== generation) return;
    if (data.progress) { status("loading", data.progress); return; }
    worker.terminate();
    if (data.error) { status("invalid", data.error); return; }
    output = data; page = 0; renderResults();
    status(data.result.summary.bets ? "results" : "empty", data.result.summary.bets ? `Complete · ${data.result.summary.bets.toLocaleString()} bets. Strategy link reflects these settings.` : "No bets match this strategy. Review the universe, conditions and price coverage below.");
    if (explicit && matchMedia("(max-width: 699px)").matches) { $("bt-editor").open = false; $("bt-strategy-summary").focus(); }
  };
  worker.onerror = () => { worker.terminate(); status("invalid", "The calculation could not finish. Reset the strategy and try again."); };
  worker.postMessage({ files, strategy });
}

async function load() {
  const response = await fetch("data/backtest/index.json");
  if (!response.ok) throw new Error("Season availability could not be loaded. No results are shown.");
  manifest = await response.json();
  if (manifest.version !== 1 || !Array.isArray(manifest.seasons) || manifest.seasons.some((v) => !Number.isInteger(v))) throw new Error("Invalid season availability. No results are shown.");
  files = await Promise.all([...new Set(manifest.seasons)].map(async (year) => {
    const response = await fetch(`data/backtest/${year}.json`);
    if (!response.ok) throw new Error(`Season ${seasonName(year)} could not be loaded. No partial results are shown.`);
    const file = await response.json();
    if (file.season !== year) throw new Error("Season file does not match its date.");
    decodeSeason(file); return file;
  }));
  rows = files.flatMap(decodeSeason);
  $("bt-season").innerHTML = options(Object.fromEntries(manifest.seasons.map((year) => [year, seasonName(year)])));
  const teams = new Map(); rows.forEach((row) => { if (row.home_id) teams.set(row.home_id, row.home); if (row.away_id) teams.set(row.away_id, row.away); });
  const teamOptions = [...teams].sort((a, b) => a[1].localeCompare(b[1])).map(([id, name]) => `<option value="${id}">${esc(name)}</option>`).join("");
  $("bt-include").innerHTML = teamOptions; $("bt-exclude").innerHTML = teamOptions;
  // The current match router only knows fixtures in the site's match indexes.
  if (files.length) await Promise.all(Object.entries(slugs).map(async ([code, slug]) => {
    try {
      const response = await fetch(`data/matches/${slug}.json`);
      if (!response.ok) return;
      const data = await response.json();
      data.matches.forEach((m) => { if (Number.isInteger(m.id) && m.id > 0) matchLinks.add(`${code}/${m.id}`); });
    } catch { /* Unknown fixture routes stay plain text. */ }
  }));
}
export async function showBacktest() {
  document.title = "Backtest · Floodlight";
  getJSON("index.json").then((index) => {
    if (location.hash.startsWith("#backtest")) setStatus(index.map((row) => row.generated_at).sort().at(-1));
  }).catch(() => { $("status-text").textContent = "Historical simulation"; });
  if (!$("bt-form")) { shell(); fill(normalizeStrategy({})); }
  clearTimeout(timer); worker?.terminate(); generation += 1;
  const ticket = generation; $("bt-results").hidden = true;
  status("loading", "Loading available seasons…");
  try {
    loadPromise ||= load(); await loadPromise;
    if (ticket !== generation) return;
    const strategy = location.hash === "#backtest" ? normalizeStrategy({}) : decodeStrategy(location.hash);
    fill(strategy); run(false);
  } catch (error) { if (ticket === generation) status(location.hash.includes("/") ? "invalid" : "unavailable", error.message); }
}

function interval(s) { return s.roi_low == null ? "Unavailable · fewer than two match dates" : `${pct(s.roi_low)} to ${pct(s.roi_high)}`; }
function metric(label, value) { return `<div><dt>${label}</dt><dd>${value}</dd></div>`; }
function renderResults() {
  const { result, reference } = output, s = result.summary, u = current.universe;
  const chosenFiles = files.filter((f) => !u.seasons.length || u.seasons.includes(f.season));
  const sampleLabel = u.forecast === "published" ? "Published before kickoff · standalone forecasts" : "Replayed standalone forecasts";
  $("bt-results").innerHTML = `
    <fieldset class="frame hero bt-hero"><legend>Result · historical simulation</legend><div class="hero-in">
      <div class="who"><h1>Return on stake</h1><p class="caption">${s.bets.toLocaleString()} bets · ${units(s.staked)} staked<br>95% interval: ${interval(s)}</p><p class="caption">${sampleLabel}</p></div>
      <div id="bt-roi" class="numeral ${s.roi < 0 ? "bt-negative" : ""}">${s.roi == null ? "—" : pct(s.roi)}</div>
    </div><p class="note">${chosenFiles.some((f) => f.season <= 2025) ? "2015/16–2025/26: replayed, in-sample for calibration. " : ""}${chosenFiles.some((f) => f.season >= 2026) ? "2026/27: unseen by calibration; later strategy choices may use these results. " : ""}Historical simulation, not betting advice.</p></fieldset>
    <fieldset class="frame"><legend>Bankroll · units</legend><p class="note">Solid amber: strategy. Dashed ink: market favourite, flat ${units(current.stake.unit)} per bet, same universe and prices, no conditions or bet-on-team restriction. Each season starts at ${units(current.bankroll)}; seasons are never joined.</p>
      <div id="bt-chart"></div><p class="note">${["kelly", "fraction"].includes(current.stake.method) ? "Strategy sizes from a finite bankroll." : "Strategy is a unit-return reference and can fall below zero; it has no finite-bankroll constraint."} Reference ROI ${pct(reference.summary.roi)} · ${reference.summary.bets.toLocaleString()} bets · ${units(reference.summary.staked)} staked · 95% interval ${interval(reference.summary)}.</p>
      <details class="bt-details"><summary>Daily bankroll values · text equivalent</summary><div id="bt-chart-table"></div></details></fieldset>
    <fieldset class="frame"><legend>Summary</legend><dl id="bt-summary" class="bt-metrics">
      ${metric("Bets", fmt(s.bets, 0))}${metric("Staked", units(s.staked))}${metric("Profit", units(s.profit))}${metric("ROI · 95% interval", `${pct(s.roi)}<small>${interval(s)}</small>`)}
      ${metric("Won / implied by prices", `${pct(s.strike_rate)} / ${pct(s.implied_strike_rate)}`)}${metric("Average decimal price", fmt(s.average_price, 2))}${metric("Mean expected return", pct(s.mean_edge))}${metric("Maximum season drawdown", units(s.max_drawdown_units))}${metric("Longest losing run", `${s.longest_losing_run} bets`)}${metric("Closing-line value", `${pct(s.clv)}<small>${s.clv_bets} of ${s.bets} bets with a close</small>`)}
      </dl><p class="note">95% intervals use 2,000 resamples of UTC match dates, seed 7, conditional on realized stakes. They do not account for searching strategies or re-size Kelly under reordered outcomes. Drawdowns and losing runs reset per season.</p></fieldset>
    <fieldset class="frame"><legend>Breakdowns</legend><label class="bt-breakdown-label">Group bets by<select id="bt-breakdown">${options({ season: "Season", competition: "League", price_band: "Decimal price band", team: "Team", month: "UTC month" })}</select></label><div id="bt-breakdown-table"></div><p class="note">Original portfolio stakes, not independently resized. Each fixture belongs to both teams in the team view.</p></fieldset>
    <fieldset class="frame"><legend>Bet log</legend><p class="note">90-minute results. Links appear only for known fixtures available on this site. Balance is the season’s settled day-end balance, not an intra-day sizing balance.</p><div id="bt-bets" class="bt-log-scroll" tabindex="0" role="region" aria-label="Scrollable bet log"></div><div class="bt-actions"><button id="bt-prev" class="chip" type="button">Previous 100</button><span id="bt-page"></span><button id="bt-next" class="chip" type="button">Next 100</button></div></fieldset>
    <fieldset class="frame"><legend>Coverage & provenance</legend><div id="bt-coverage"></div></fieldset>`;
  $("bt-results").hidden = false;
  renderChart(); renderBreakdown(); renderBets(); renderCoverage(chosenFiles);
  $("bt-breakdown").onchange = renderBreakdown;
  $("bt-prev").onclick = () => { page--; renderBets(); };
  $("bt-next").onclick = () => { page++; renderBets(); };
}
function table(headers, body, className = "bt-table") { return `<table class="board ${className}"><thead><tr>${headers.map((h) => `<th scope="col">${h}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table>`; }
function cells(values) { return `<tr>${values.map((v) => `<td>${v}</td>`).join("")}</tr>`; }
function renderBreakdown() {
  const dimension = $("bt-breakdown").value;
  const groups = output.result.breakdowns.filter((g) => g.dimension === dimension);
  $("bt-breakdown-table").innerHTML = table(["Group", "Bets / staked", "ROI / 95% interval", "Profit"], groups.map((g) => cells([
    esc(dimension === "season" ? seasonName(g.value) : leagues[g.value] || g.value), `${g.bets}<small>${units(g.staked)}</small>`, `${pct(g.roi)}<small>${interval(g)}</small>`, units(g.profit),
  ])).join("")) + (!groups.length ? '<p class="note">No bets in this group.</p>' : "");
}
function renderBets() {
  const bets = output.result.bets, slice = bets.slice(page * 100, (page + 1) * 100);
  const balances = new Map(output.result.bankroll.map((p) => [`${p.season}/${p.day}`, p.bankroll]));
  $("bt-bets").innerHTML = table(["UTC date", "Match / forecast origin", "Selection", "Price", "Model", "Edge", "Stake", "Result / profit", "Day-end balance"], slice.map((b) => {
    const name = `${esc(b.home)} – ${esc(b.away)}`;
    const link = Number.isInteger(b.id) && b.id > 0 && matchLinks.has(`${b.comp}/${b.id}`) ? `<a href="#match/${slugs[b.comp]}/${b.id}">${name}</a>` : name;
    return cells([b.day, `${link}<small>${esc(b.at)} · ${esc(b.comp)}</small>`, esc(b.selection), fmt(b.price, 2), pct(b.probability), pct(b.edge), units(b.stake), `<span class="bt-outcome ${b.won ? "bt-won" : "bt-lost"}">${b.won ? "Won" : "Lost"}</span> ${b.score.join("–")}<small>${units(b.profit)}</small>`, units(balances.get(`${b.season}/${b.day}`))]);
  }).join(""), "bt-log");
  $("bt-prev").disabled = page === 0; $("bt-next").disabled = (page + 1) * 100 >= bets.length;
  $("bt-page").textContent = bets.length ? `${page * 100 + 1}–${Math.min((page + 1) * 100, bets.length)} of ${bets.length}` : "No bets";
}
function renderChart() {
  const { result, reference } = output;
  const seasons = [...new Set([...result.bankroll, ...reference.bankroll].map((p) => p.season))].sort();
  let html = "", text = "";
  for (const season of seasons) {
    const paths = [result.bankroll, reference.bankroll].map((path) => path.filter((p) => p.season === season));
    const dates = [...new Set(paths.flat().map((p) => p.day).filter(Boolean))].sort();
    const start = Date.parse(dates[0]) - 86400000, end = Date.parse(dates.at(-1));
    const values = [0, current.bankroll, ...paths.flat().map((p) => p.bankroll)];
    const low = Math.min(...values), high = Math.max(...values), span = high - low || 1;
    const x = (day) => 52 + ((day ? Date.parse(day) : start) - start) / (end - start || 1) * 622;
    const y = (value) => 160 - (value - low) / span * 135;
    html += `<div class="bt-season-chart"><h2>${seasonName(season)} <span>Reset to ${units(current.bankroll)}</span></h2><svg viewBox="0 0 700 195" role="img" aria-label="${seasonName(season)} bankroll in units; solid strategy and dashed market favourite. Daily values follow in the table.">
      ${[low, (low + high) / 2, high].map((v) => `<line x1="52" x2="674" y1="${y(v)}" y2="${y(v)}" class="bt-grid"/><text x="46" y="${y(v) + 4}" text-anchor="end">${fmt(v, 0)}</text>`).join("")}
      <line x1="52" x2="674" y1="${y(current.bankroll)}" y2="${y(current.bankroll)}" class="bt-start"/>
      ${paths.map((path, i) => path.length ? `<path d="${path.map((p, j) => `${j ? "L" : "M"}${x(p.day).toFixed(2)},${y(p.bankroll).toFixed(2)}`).join(" ")}" class="bt-line ${i ? "bt-reference" : ""}"/>` : "").join("")}
      <text x="52" y="185">Start</text><text x="674" y="185" text-anchor="end">${esc(dates.at(-1) || "")}</text></svg></div>`;
    const maps = paths.map((path) => new Map(path.map((p) => [p.day, p.bankroll])));
    let balances = [current.bankroll, current.bankroll];
    text += `<h2>${seasonName(season)}</h2>` + table(["UTC date", "Strategy (u)", "Market favourite (u)"], [null, ...dates].map((day) => {
      balances = balances.map((value, i) => maps[i].get(day) ?? value);
      return cells([day || "Season reset", ...balances.map((v) => fmt(v))]);
    }).join(""));
  }
  $("bt-chart").innerHTML = html || '<p class="note">No settled bets to plot.</p>';
  $("bt-chart-table").innerHTML = text || '<p class="note">No daily values.</p>';
}
function renderCoverage(chosenFiles) {
  const c = output.result.coverage;
  const selectedRows = rows.filter((r) => chosenFiles.some((f) => f.season === r.season) && (!current.universe.comps.length || current.universe.comps.includes(r.comp)) && r.forecast === current.universe.forecast);
  const missing = (field) => selectedRows.filter((r) => r[field] == null).length;
  $("bt-coverage").innerHTML = `<dl class="bt-metrics">${Object.entries(c).map(([k, v]) => metric(esc(k.replaceAll("_", " ")), fmt(v, 0))).join("")}</dl>
    <p class="note">Before team/calendar filters and conditions: ${selectedRows.length} rows in the selected seasons, leagues and forecast kind. Unknown rounds ${missing("matchday")}; ratings ${missing("rating_gap")}; Stakes ${missing("stakes")}; fixture IDs ${missing("id")}. Unknowns are never inferred. Missing prices void a candidate; zero-stake selections are counted separately.</p>
    <p class="note">${["avg", "max"].includes(current.execution.book) ? "Aggregate benchmark: not an executable single-book offer; maximum prices are optimistic and may not have been simultaneously obtainable. " : ""}No account limits, slippage, rejected bets or taxes are modelled. CLV = entry / close − 1; missing closing quotes remain unavailable.</p>
    ${chosenFiles.map((file) => {
      const p = file.provenance || {}, dates = file.columns.kickoff.filter(Boolean).sort();
      return `<details class="bt-details"><summary>${seasonName(file.season)} · ${esc(p.forecast_label || "Calibration status not supplied")} · source dates</summary>
        <p class="note">File generated: ${esc(file.generated_at || "Unknown")}. Covered kickoffs: ${esc(dates[0] || "Unknown")} to ${esc(dates.at(-1) || "Unknown")}. Calibration: ${esc(file.calibration_version || "Unknown")}.</p>
        <p class="note">${esc(p.timing || "Quote observation dates not supplied.")} These are cached source dates, not a claim of current coverage.</p>
        <p class="note">Results cutoffs: ${esc(Object.entries(p.results_cutoff_by_comp || {}).map(([comp, date]) => `${comp}: ${date}`).join(" · ") || "Not supplied")}. Receipt exclusions: ${esc(p.receipt_exclusions ?? "Unknown")}.</p>
        <p class="note">Historical quotes: football-data.co.uk. Individual quote timestamps are approximate. Archived source hashes identify the exact inputs.</p>
        <details><summary>Source hashes and recorded coverage</summary><pre class="bt-provenance">${esc(JSON.stringify({ coverage: file.coverage, provenance: p }, null, 2))}</pre></details></details>`;
    }).join("")}`;
}
