// Match page: everything known about one fixture before kickoff, and after full time the forecast against the result.
import {
  COMPS, compBySlug, $, esc, getJSON, setStatus, ordinal, dec, dayKey, pick, sidePair, clubName, clubCrest, loadForm, played,
  verdict, pct, pct1,
} from "./core.js";
import { forecastBlocks, stakesTable, stageLabel, probCells, PENDING, stakeKinds, stakeLines } from "./matches.js";
import { rankTag } from "./clubs.js";

const OUTCOMES = ["Home win", "Draw", "Away win"];
const STRENGTH = [["rating", "Rating"], ["attack", "Attack"], ["defense", "Defence"]];
/* season chances that move by less than this (points) are within simulation noise */
const NOISE = 2;
let showing = 0;
let page = null; // the fixture on screen, its data and the After · Before choice

export async function showMatch(slug, id) {
  const ticket = ++showing;
  const comp = compBySlug[slug];
  let file, table, clubs, all;
  try {
    [file, table, clubs, all] = comp ? await Promise.all([
      getJSON(`matches/${slug}.json`),
      getJSON(`${slug}.json`).catch(() => null),
      getJSON("clubs.json").catch(() => null),
      Promise.all(COMPS.map((c) => getJSON(`matches/${c.slug}.json`).catch(() => null))),
      loadForm().catch(() => {}),
    ]) : [];
  } catch (err) {
    if (ticket === showing) $("view-match").innerHTML = `<p class="note">This fixture could not be loaded (${esc(err.message)}). <a href="#matches">← Matches</a></p>`;
    return;
  }
  const m = file && file.matches.find((x) => String(x.id) === id);
  if (!m) {
    document.title = "Match · Floodlight";
    if (ticket === showing) $("view-match").innerHTML = `<p class="note mp-none">No fixture ${esc(id || "")} in ${esc(comp ? comp.label : "our competitions")}. <a href="#matches">← Back to Matches</a></p>`;
    return;
  }
  const post = Boolean(m.score && m.p);
  const season = (table || clubs)?.season.split("/")[0];
  const [stakes, hist, weekly, events] = await Promise.all([
    stakesTable(m, slug),
    post && season ? getJSON(`history/${season}/${slug}.json`).catch(() => null) : null,
    post && season ? getJSON(`history/${season}/clubs.json`).catch(() => null) : null,
    // Understat shots: finished league games only (none for the Champions League); a missing file hides "Chances"
    post && season && slug !== "champions-league" ? getJSON(`match/${season}/${slug}/${m.id}.json`).catch(() => null) : null,
  ]);
  const span = post ? refreshes(hist, m.kickoff) : null;
  const pastStakes = post && m.published ? await stakesTable(m, slug, { day: span ? dayLabel(hist.dates[span.b]) : "–", before: (club, key) => histValue(hist, span, club, key, "b") }) : "";
  if (ticket !== showing) return;
  document.title = `${m.home} v ${m.away} · Floodlight`;
  setStatus(file.generated_at);
  const slugs = new Map((clubs ? clubs.clubs : []).map((c) => [c.id, c.slug]));
  page = { m, comp, slugs, stakes, pastStakes, file, table, clubs, files: all.filter(Boolean), hist, span, weekly, mode: post ? "after" : "before",
    shots: events && events.shots && events.shots.length ? events : null };
  render();
}

function render() {
  const { m, comp, slugs, stakes, table, clubs, files } = page;
  $("view-match").innerHTML = hero(m, comp, slugs) + (page.mode === "after" ? against(m, comp, page.file) + shotReport(m) + changed(m, comp)
    : (m.p ? `<fieldset class="frame"><legend>${m.score ? "The forecast before kickoff" : "The forecast"}</legend><div class="panel mp-fc">${forecastBlocks(m)}</div></fieldset>` : "")
      + (stakes ? `<fieldset class="frame"><legend>What's at stake</legend>${stakes}</fieldset>` : "")
      + sides(m, comp, table, clubs, files));
  drawXg();
}

/* After · Before: re-render in place and keep focus on the chip */
$("view-match").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-mode]");
  if (!b || !page || b.dataset.mode === page.mode) return;
  page.mode = b.dataset.mode;
  render();
  $("view-match").querySelector(`button[data-mode="${page.mode}"]`).focus();
});

function hero(m, comp, slugs) {
  const day = new Date(m.kickoff);
  const kickoff = day.toLocaleString("en-GB", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
  const side = (id, name) => (slugs.has(id) ? `<a href="#clubs/${slugs.get(id)}">${clubName(id, name, "hero")}</a>` : clubName(id, name, "hero"));
  const pending = PENDING[m.reported || m.status];
  const when = m.score ? `Full time · ${esc(kickoff)}`
    : pending ? `${pending} · was set for ${esc(kickoff)}`
    : `Kickoff <b>${esc(kickoff)}</b>, your time${day < Date.now() ? " · result pending" : ""}`;
  const fav = m.p ? pick(m.p) : -1;
  const facts = m.p ? ` · expected goals <b>${dec(m.exp[0])}–${dec(m.exp[1])}</b>` : "";
  const post = m.score && m.p;
  const modes = post ? `<div class="chips mp-modes" role="group" aria-label="Show">${[["after", "After"], ["before", "Before"]].map(([k, label]) =>
    `<button type="button" class="chip" data-mode="${k}" aria-pressed="${page.mode === k}">${label}</button>`).join("")}</div>` : "";
  let board = "";
  if (m.score) {
    board = `<div class="numeral on" role="img" aria-label="Final score ${m.score[0]}–${m.score[1]}">${m.score[0]}–${m.score[1]}</div>`;
  } else if (m.p) {
    board = `<p class="mp-lbl">${OUTCOMES[fav]}</p>
      <div class="numeral on" role="img" aria-label="${esc(`${OUTCOMES[fav]}: ${Math.round(m.p[fav] * 100)}% chance`)}">${Math.round(m.p[fav] * 100)}<sup>%</sup></div>`;
  }
  let said = "";
  if (post && page.mode === "after") {
    const v = verdict(m);
    said = `<p class="mp-said">The model gave ${esc(happened(m, v))} ${pct1(v.given)}. ${m.published ? "Published before kickoff." : "Reconstructed from results before match day."}</p>`;
  }
  return `<p class="crumbs"><a href="#matches/${dayKey(day)}">← Matches, ${esc(day.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }))}</a></p>
    <fieldset class="frame hero mp-hero">
      <legend>${esc(stageLabel(comp, [{ m }]))}</legend>
      <div class="hero-in">
        <div class="who">
          <h1>${side(m.home_id, m.home)}<span class="mp-v">v</span>${side(m.away_id, m.away)}</h1>
          <p class="caption">${when}${facts}</p>
          ${modes}
        </div>
        ${board || m.p ? `<div class="mp-board">${board}${m.p ? probCells(m) : ""}${said}</div>` : ""}
      </div>
    </fieldset>`;
}

/* ---------- after full time ---------- */
const dayLabel = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const happened = (m, v) => (v.actual === 1 ? "a draw" : `a ${v.actual ? m.away : m.home} win`);
const utcDay = (iso) => new Date(iso).toISOString().slice(0, 10);

/* The history points either side of a fixture, as indices { b, a }, or null. A point dated D is the run as of D
   (site_history.add_point dates it by the run's as_of): the daily refresh runs at 01:17 UTC (the backfill at 05:30),
   before any game that day, so "before" is the last point dated on or before the kickoff day and "after" the next one.
   Only the latest point's results cutoff is kept: if it already holds this game (a rerun later that day), it is
   "after"; if the next point is the latest and doesn't hold the game yet, there is no "after". */
function refreshes(hist, kickoff) {
  if (!hist || !hist.dates) return null;
  const k = Date.parse(kickoff);
  const last = hist.dates.length - 1;
  const holds = hist.cutoff != null && Date.parse(hist.cutoff) >= k;
  let b = hist.dates.findLastIndex((d) => d <= utcDay(kickoff));
  if (b === last && holds) b -= 1;
  const a = b + 1;
  return b < 0 || a > last || (a === last && !holds) ? null : { b, a };
}
const histValue = (hist, span, id, key, at) => {
  const t = span && hist.teams.find((x) => x.id === id);
  return t && t[key] ? t[key][span[at]] : null;
};

/* "Forecast against result": the actual score's chance, how surprising the result was this season, goals beside expectation */
function against(m, comp, file) {
  const v = verdict(m);
  const [hs, as] = m.score;
  const rank = m.top.findIndex(([h, a]) => h === hs && a === as);
  const score = `The actual <b>${hs}–${as}</b>`;
  const four = `${m.top.length} likeliest scores`;
  const chance = m.p_score == null ? `${score} was not among the ${four} saved.`
    : `${score} had <b>${pct1(m.p_score)}</b>, ${rank < 0 ? `outside the ${four}` : rank ? `the ${ordinal(rank + 1)} likeliest score` : "the likeliest score"}.`;
  const done = file.matches.filter((x) => x.score && x.p);
  const given = done.map((x) => verdict(x).given);
  const least = 1 + given.filter((g) => g < v.given).length;
  const most = 1 + given.filter((g) => g > v.given).length;
  const [n, word] = least <= most ? [least, "least"] : [most, "most"];
  const published = done.filter((x) => x.published).length;
  const season = `${n === 1 ? `The ${word}` : `The ${ordinal(n)} ${word}`} expected result of ${done.length} in ${comp.slug === "champions-league" ? "the " : ""}${esc(comp.label)} this season, by the chance the model gave what happened (${esc(happened(m, v))}, ${pct1(v.given)}).`
    + ` ${published ? `${published} of those forecasts ${published === 1 ? "was" : "were"} published before kickoff; the rest are reconstructed.` : "Those forecasts are all reconstructed."}`;
  const row = (label, pair, d) => `<tr><td class="h"><b>${dec(pair[0], d)}</b></td><th scope="row">${label}</th><td class="a"><b>${dec(pair[1], d)}</b></td></tr>`;
  const xgNote = m.xg ? "Shot xG is Understat's, from the chances each side had." : comp.slug === "champions-league" ? "Understat has no shot xG for the Champions League." : "No shot xG from Understat for this game.";
  return `<fieldset class="frame"><legend>Forecast against result</legend>
    <p class="mp-line">${chance}</p><p class="mp-line">${season}</p>
    <div class="scroll"><table class="board mp-sides mp-vs">
      <thead><tr><th class="h">${clubName(m.home_id, m.home, "inline")}</th><th></th><th class="a">${clubName(m.away_id, m.away, "inline")}</th></tr></thead>
      <tbody>${row("Expected before kickoff (model)", m.exp, 1)}${row("Goals", m.score, 0)}${m.xg ? row("Shot xG (Understat)", m.xg, 2) : ""}</tbody></table></div>
    <p class="note">${m.published ? "The forecast was published before kickoff." : "The forecast is reconstructed: as of 00:00 UTC on match day, from results before then."} Expected goals are the model's, before kickoff. ${xgNote}</p>
  </fieldset>`;
}

/* "What it changed": season chances across the refreshes either side of the game, the stakes as saved before
   kickoff, and both clubs' ratings across the weekly rankings either side of it */
function changed(m, comp) {
  const parts = [chances(m, comp), page.pastStakes ? `<h4>What was at stake</h4>${page.pastStakes}` : "", strength(m)].filter(Boolean);
  return parts.length ? `<fieldset class="frame mp-after"><legend>What it changed</legend>${parts.join("")}</fieldset>` : "";
}

function chances(m, comp) {
  const { hist, span } = page;
  if (!span) return "";
  const kinds = stakeKinds(comp.slug);
  const seen = new Set();
  const rows = [];
  const add = (id, name, key, word, always) => {
    const [b, a] = [histValue(hist, span, id, key, "b"), histValue(hist, span, id, key, "a")];
    if (b == null || a == null || seen.has(`${id}/${key}`)) return;
    // a playing club's settled races (under 1% or over 99% either side) say nothing
    if (!always && (Math.max(a, b) < 1 || Math.min(a, b) > 99)) return;
    seen.add(`${id}/${key}`);
    // the change between the whole percentages shown, so the arrow agrees with the two columns
    const d = Math.round(a) - Math.round(b);
    const good = key === "releg" ? d < 0 : d > 0;
    const size = Math.abs(d);
    const change = Math.abs(d) < NOISE ? `<span class="mv flat" title="Less than ${NOISE} points">–</span>`
      : `<span class="mv ${good ? "up" : "down"}" aria-label="${d > 0 ? "up" : "down"} ${size} points">${d > 0 ? "▲" : "▼"}<b>${size}</b></span>`;
    rows.push(`<tr><td class="l">${clubName(id, name, "inline")} <small>${word}</small></td><td>${pct(b)}</td><td class="b">${pct(a)}</td><td>${change}</td></tr>`);
  };
  for (const [id, name] of [[m.home_id, m.home], [m.away_id, m.away]]) for (const [key, word] of kinds) add(id, name, key, word, false);
  for (const line of stakeLines(m, comp.slug)) add(line.team.id, line.team.name, line.key, line.word, true);
  if (!rows.length) return "";
  const [d1, d2] = [dayLabel(hist.dates[span.b]), dayLabel(hist.dates[span.a])];
  return `<h4>Season chances</h4>
    <div class="scroll"><table class="board stakes-table mp-chances"><thead><tr><th class="l"></th><th>${d1}</th><th>${d2}</th><th>Change</th></tr></thead>
      <tbody>${rows.slice(0, 8).join("")}</tbody></table></div>
    <p class="note">Across the refreshes of ${d1} and ${d2}, the last before kickoff and the first after it, so other results in between count too. Changes under ${NOISE} points are within simulation noise and shown as –.${m.published && m.stakes ? " Rivals are the clubs in the stakes saved before kickoff." : ""}</p>`;
}

/* rating changes between the weekly ranking frozen before the game and the next one that holds it (or today's) */
function ratingSpan(m) {
  const { weekly, clubs } = page;
  if (!weekly || !clubs) return null;
  const k = Date.parse(m.kickoff);
  const holds = (w) => (w.cutoff ? Date.parse(w.cutoff) >= k : w.date > utcDay(m.kickoff));
  const i = weekly.weeks.findLastIndex((w) => w.date <= utcDay(m.kickoff) && !holds(w));
  if (i < 0) return null;
  const next = weekly.weeks.slice(i + 1).find(holds);
  if (next) return { from: weekly.weeks[i], to: (id) => next.clubs[id], until: `Monday ${dayLabel(next.date)}` };
  if (utcDay(clubs.generated_at) <= utcDay(m.kickoff)) return null;
  const live = new Map(clubs.clubs.map((c) => [String(c.id), [c.rating, c.attack, c.defense]]));
  return { from: weekly.weeks[i], to: (id) => live.get(id), until: "today's ratings" };
}

function strength(m) {
  const span = ratingSpan(m);
  if (!span) return "";
  const cell = (id, i) => {
    const [b, a] = [span.from.clubs[id]?.[i], span.to(String(id))?.[i]];
    if (b == null || a == null) return "";
    const d = Math.round((a - b) * 10) / 10;
    const label = d ? `${d > 0 ? "up" : "down"} ${dec(Math.abs(d))}` : "unchanged";
    const mv = `<span class="mv ${d > 0 ? "up" : d < 0 ? "down" : "flat"}" aria-label="${label}">${d > 0 ? `▲<b>${dec(d)}</b>` : d < 0 ? `▼<b>${dec(-d)}</b>` : "–"}</span>`;
    return `${dec(b)} → <b>${dec(a)}</b> ${mv}`;
  };
  const rows = STRENGTH.map(([, label], i) => {
    const [h, a] = [cell(m.home_id, i), cell(m.away_id, i)];
    return h || a ? `<tr><td class="h">${h}</td><th scope="row">${label}</th><td class="a">${a}</td></tr>` : "";
  }).join("");
  if (!rows) return "";
  return `<h4>Strength</h4>
    <div class="scroll"><table class="board mp-sides">
      <thead><tr><th class="h">${clubName(m.home_id, m.home, "inline")}</th><th></th><th class="a">${clubName(m.away_id, m.away, "inline")}</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="note">Ratings from the ranking frozen on Monday ${dayLabel(span.from.date)} to ${span.until}. Every game in that span counts, not this one alone.</p>`;
}

/* ---------- chances: Understat shots, after full time ---------- */
// shot tuples are [minute, side, x, y, xg, result, situation, body, player, assister]; an OwnGoal tuple carries the
// side of the player who scored it, so it counts for the other side and is not a chance of either
const WORDS = { SavedShot: "Saved", MissedShots: "Missed", BlockedShot: "Blocked", ShotOnPost: "Post", OwnGoal: "Own goal", DirectFreekick: "Direct free kick", OtherBodyPart: "Other" };
const word = (s) => WORDS[s] || String(s).replace(/([a-z])([A-Z])/g, (_, a, b) => `${a} ${b.toLowerCase()}`);
/* Understat minutes are zero-based elapsed minutes: 0 is the first minute */
const minute = (s) => `${s[0] + 1}'`;
const own = (s) => s[5] === "OwnGoal";
const other = (side) => (side === "h" ? "a" : "h");
const surname = (name) => String(name).split(" ").slice(-1)[0];

/* cumulative xG per side as steps [{ t, v }], ending at the published match xG where we can: Understat's match xG
   counts shots from one attack as one chance, so shots in the same minute combine as 1 − ∏(1 − xG) when that gives
   the match figure, plain sums when those do (it didn't merge them), and otherwise plain sums flagged `summed` */
function xgLines(shots, m) {
  return ["h", "a"].map((side, i) => {
    const build = (combine) => {
      const by = new Map();
      for (const s of shots) if (s[1] === side && !own(s)) by.set(s[0], combine ? (by.get(s[0]) ?? 1) * (1 - s[4]) : (by.get(s[0]) ?? 0) + s[4]);
      let v = 0;
      return [...by].sort((a, b) => a[0] - b[0]).map(([t, x]) => ({ t, v: (v += combine ? 1 - x : x) }));
    };
    const total = (steps) => (steps.length ? steps[steps.length - 1].v : 0);
    const near = (steps) => m.xg != null && Math.abs(total(steps) - m.xg[i]) < 0.0051;
    const combined = build(true);
    const steps = near(combined) ? combined : build(false);
    return { steps, total: total(steps), summed: !near(steps) };
  });
}

function shotReport(m) {
  const data = page.shots;
  if (!data) return "";
  const { shots } = data;
  const names = { h: m.home, a: m.away };
  const ids = { h: m.home_id, a: m.away_id };
  const chances = shots.filter((s) => !own(s));

  // the pitch: 105 × 68, home shooting right, away mirrored to shoot left
  const end = (x0, d) => {
    const box = (depth, half) => `<path d="M${x0} ${34 - half}H${x0 + d * depth}V${34 + half}H${x0}"/>`;
    const dy = Math.sqrt(9.15 ** 2 - 5.5 ** 2).toFixed(2);
    return box(16.5, 20.16) + box(5.5, 9.16) + `<circle class="spot" cx="${x0 + d * 11}" cy="34" r=".35"/>`
      + `<path d="M${x0 + d * 16.5} ${(34 - dy).toFixed(2)}A9.15 9.15 0 0 ${d > 0 ? 1 : 0} ${x0 + d * 16.5} ${(34 + +dy).toFixed(2)}"/>`
      + `<rect x="${d > 0 ? -1.6 : 105}" y="30.34" width="1.6" height="7.32"/>`;
  };
  const lines = `<rect x="0" y="0" width="105" height="68"/><path d="M52.5 0V68"/><circle cx="52.5" cy="34" r="9.15"/><circle class="spot" cx="52.5" cy="34" r=".35"/>${end(0, 1)}${end(105, -1)}`;
  const kind = (s) => (s[5] === "Goal" ? "goal" : s[5] === "SavedShot" ? "saved" : "off");
  const tip = (s) => esc(`<b>${esc(s[8])}</b> · ${esc(names[s[1]])}<br>${minute(s)} · <b>${dec(s[4], 2)}</b> xG · ${esc(word(s[6]))}<br>${esc(word(s[5]))}, ${esc(word(s[7]).toLowerCase())}${s[9] ? ` · assist ${esc(s[9])}` : ""}`);
  // biggest chances first so small ones stay on top; goals last of all
  const dots = [...chances].sort((a, b) => (a[5] === "Goal") - (b[5] === "Goal") || b[4] - a[4]).map((s) => {
    const [x, y] = s[1] === "h" ? [s[2], s[3]] : [1 - s[2], 1 - s[3]];
    const [cx, cy, r] = [(x * 105).toFixed(2), (y * 68).toFixed(2), Math.max(0.6, 3.6 * Math.sqrt(s[4]))];
    return `<g data-tip="${tip(s)}"><circle class="hit" cx="${cx}" cy="${cy}" r="${Math.max(r, 2.2).toFixed(2)}"/><circle class="shot ${kind(s)}" cx="${cx}" cy="${cy}" r="${r.toFixed(2)}"/></g>`;
  }).join("");
  const sum = (side) => chances.filter((s) => s[1] === side);
  const say = (side) => `${names[side]} ${sum(side).length} shots, ${sum(side).filter((s) => s[5] === "Goal").length} scored`;
  const map = `<div class="mp-pitch"><svg viewBox="-2 -2 109 72" role="img" aria-label="${esc(`Shot map: ${say("h")}, shooting right; ${say("a")}, shooting left. The shot list below has every shot.`)}"><g class="pitch">${lines}</g>${dots}</svg>
    <p class="mp-dir"><span>${clubName(m.home_id, m.home, "inline")} →</span><span>← ${clubName(m.away_id, m.away, "inline")}</span></p></div>
    <p class="mp-key"><span><i class="k goal"></i>Goal</span><span><i class="k saved"></i>Saved</span><span><i class="k off"></i>Missed, blocked or post</span><span>Circle area is the shot's xG</span></p>`;

  const owns = shots.filter(own);
  const ogNote = owns.length ? ` Own goals aren't chances, so they're off the map and out of the xG lines: ${owns.map((s) => `${esc(s[8])}'s own goal (${minute(s)}) counted for ${esc(names[other(s[1])])}`).join("; ")}.` : "";
  const list = `<details class="mp-list"><summary>Shot list</summary><div class="scroll"><table class="board">
    <thead><tr><th>Min</th><th class="l">Player</th><th>xG</th><th class="l">Result</th><th class="l">Situation</th><th class="l">Body</th><th class="l">Assist</th></tr></thead>
    <tbody>${shots.map((s) => `<tr class="${s[5] === "Goal" || own(s) ? "lit" : ""}"><td>${minute(s)}</td><td class="l">${clubCrest(ids[s[1]], "inline")} ${esc(s[8])}</td><td>${own(s) ? "–" : dec(s[4], 2)}</td><td class="l">${esc(word(s[5]))}</td><td class="l">${esc(word(s[6]))}</td><td class="l">${esc(word(s[7]))}</td><td class="l">${s[9] ? esc(s[9]) : ""}</td></tr>`).join("")}</tbody></table></div></details>`;

  const sides = xgLines(shots, m);
  const key = `<p class="mp-key">${sides.map((l, i) => `<span><svg width="22" height="8" aria-hidden="true"><line x1="0" x2="22" y1="4" y2="4" class="${i ? "xa" : "xh"}"/></svg>${clubName(ids["ha"[i]], names["ha"[i]], "inline")} <b>${dec(l.total, 2)}</b>${l.summed ? " summed shot xG" : ""}</span>`).join("")}</p>`;
  const off = sides.map((l, i) => (l.summed && m.xg ? `${esc(names["ha"[i]])}'s line ends at summed shot xG, ${dec(l.total, 2)}, not the match xG of ${dec(m.xg[i], 2)}.` : "")).filter(Boolean);
  const xgNote = "Each step is a chance. Understat's match xG counts shots from one attack as one chance, so shots in the same minute combine as 1 − ∏(1 − xG) where that gives the match figure."
    + (off.length ? ` ${off.join(" ")}` : " Both lines end at the match xG above.") + " Amber bulbs are goals.";

  let retro = "";
  if (data.retro) {
    const r = data.retro;
    retro = `<h4>From the chances</h4><p class="mp-retro"><span><b>${pct1(r[0])}</b> ${esc(m.home)} win</span><span><b>${pct1(r[1])}</b> Draw</span><span><b>${pct1(r[2])}</b> ${esc(m.away)} win</span></p>
      <p class="note">After the fact, from shot xG, not a forecast: how often these chances, each taken as an independent shot, give each result. Own goals are left out.</p>`;
  }

  let stand = "";
  if (data.players) {
    const top = ["h", "a"].flatMap((side) => (data.players[side] || []).map((p) => ({ ...p, side })))
      .filter((p) => p.xg + p.xa > 0).sort((a, b) => b.xg + b.xa - (a.xg + a.xa)).slice(0, 3);
    if (top.length) stand = `<h4>Standouts</h4><div class="scroll"><table class="board mp-stand">
      <thead><tr><th class="l">Player</th><th>Min</th><th>Shots</th><th>xG</th><th>xA</th><th>Key passes</th></tr></thead>
      <tbody>${top.map((p) => `<tr><td class="l">${clubCrest(ids[p.side], "inline")} <b>${esc(p.player)}</b></td><td>${p.minutes}</td><td>${p.shots}</td><td class="b">${dec(p.xg, 2)}</td><td class="b">${dec(p.xa, 2)}</td><td>${p.key_passes}</td></tr>`).join("")}</tbody></table></div>
      <p class="note">The top three by xG + xA: the chances each player took and the chances their passes made.</p>`;
  }

  return `<fieldset class="frame mp-after mp-shots"><legend>Chances</legend>
    <h4>Shot map</h4>${map}${list}
    <h4>xG through the game</h4>${key}<div class="mp-xgline" id="mp-xgline"></div><p class="note">${xgNote}${ogNote}</p>
    ${retro}${stand}
    <p class="note">Shots, xG and players from Understat.</p>
  </fieldset>`;
}

/* the cumulative xG timeline: step lines, home solid and away dashed, goals as amber bulbs; drawn at the frame's width */
function drawXg() {
  const box = $("mp-xgline");
  if (!box || !page.shots) return;
  const { m } = page, { shots } = page.shots;
  const sides = xgLines(shots, m);
  const lines = sides.map((l) => l.steps), totals = sides.map((l) => l.total);
  const W = Math.round(Math.min(760, Math.max(300, box.clientWidth || 760)));
  const H = W < 480 ? 210 : 250, pad = { l: 34, r: 40, t: 16, b: 24 };
  const last = Math.max(90, ...shots.map((s) => s[0] + 1));
  const top = Math.max(1, Math.ceil(Math.max(...totals) * 2) / 2);
  const x = (t) => pad.l + (t / last) * (W - pad.l - pad.r);
  const y = (v) => H - pad.b - (v / top) * (H - pad.t - pad.b);
  const step = top > 3 ? 1 : 0.5;
  let grid = "";
  for (let v = 0; v <= top + 1e-9; v += step) grid += `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="tick" x="${pad.l - 6}" y="${y(v) + 3.5}" text-anchor="end">${dec(v)}</text>`;
  for (const t of [0, 15, 30, 45, 60, 75, 90]) grid += `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${H - pad.b}" y2="${H - pad.b + 4}"/><text class="tick" x="${x(t)}" y="${H - 8}" text-anchor="middle">${t}'</text>`;
  const path = (steps) => `M${x(0)} ${y(0)}${steps.map((s) => `H${x(s.t).toFixed(1)}V${y(s.v).toFixed(1)}`).join("")}H${x(last)}`;
  const at = (steps, t) => steps.reduce((v, s) => (s.t <= t ? s.v : v), 0);

  // goals (and own goals, for the side they counted for) as bulbs on that side's line, labels pushed clear of
  // each other and of every bulb
  const scorers = shots.filter((s) => s[5] === "Goal" || own(s)).map((s) => {
    const side = own(s) ? other(s[1]) : s[1];
    return { s, side, cx: x(s[0]), cy: y(at(lines[side === "h" ? 0 : 1], s[0])) };
  });
  const placed = scorers.map(({ cx, cy }) => ({ x0: cx - 5, x1: cx + 5, y0: cy - 5, y1: cy + 5 }));
  const goals = scorers.map(({ s, side, cx, cy }) => {
    const text = `${minute(s)} ${surname(s[8])}${own(s) ? " (og)" : ""}`;
    const width = text.length * 6.2;
    const right = cx + 6 + width > x(last);
    const x0 = right ? cx - 6 - width : cx + 6;
    let ly = cy - 7;
    while (placed.some((p) => x0 < p.x1 && x0 + width > p.x0 && ly - 9 < p.y1 && ly + 2 > p.y0)) ly -= 11;
    placed.push({ x0, x1: x0 + width, y0: ly - 9, y1: ly + 2 });
    const tipText = esc(`<b>${esc(s[8])}</b>${own(s) ? " (own goal)" : ""} · ${minute(s)}<br>Goal for ${esc(side === "h" ? m.home : m.away)}${own(s) ? "" : ` · ${dec(s[4], 2)} xG`}`);
    return { side, label: `${minute(s)} ${s[8]}${own(s) ? " (own goal)" : ""}`,
      svg: `<g data-tip="${tipText}"><circle class="goal" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="4.5"/><text class="glbl" x="${(right ? cx - 6 : cx + 6).toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${right ? "end" : "start"}">${esc(text)}</text></g>` };
  });
  // end totals, kept 12 px apart
  const ends = totals.map((v, i) => ({ i, y: y(v) + 3.5 }));
  if (Math.abs(ends[0].y - ends[1].y) < 12) {
    const [hi, lo] = ends[0].y <= ends[1].y ? [ends[0], ends[1]] : [ends[1], ends[0]];
    const mid = (hi.y + lo.y) / 2;
    hi.y = mid - 6; lo.y = mid + 6;
  }
  const endLabels = ends.map((e) => `<text class="end${e.i ? " away" : ""}" x="${x(last) + 5}" y="${e.y.toFixed(1)}">${dec(totals[e.i], 2)}</text>`).join("");
  const scored = goals.map((g) => g.label).join(", ");
  const aria = `xG through the game: ${m.home} ${dec(totals[0], 2)}, ${m.away} ${dec(totals[1], 2)}.${scored ? ` Goals: ${scored}.` : ""}`;
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(aria)}">${grid}
    <path class="xa" d="${path(lines[1])}"/><path class="xh" d="${path(lines[0])}"/>${endLabels}${goals.map((g) => g.svg).join("")}</svg>`;
}

let resizing;
window.addEventListener("resize", () => {
  clearTimeout(resizing);
  resizing = setTimeout(() => { if (page && !$("view-match").hidden) drawXg(); }, 150);
});

/* goals and xG per game in every competition this season, before kickoff */
function seasonGoals(files, id, before) {
  const games = files.flatMap((f) => f.matches).filter((x) => x.score && x.kickoff < before && (x.home_id === id || x.away_id === id));
  const total = (rows, field) => rows.reduce(([f, a], x) => {
    const [gf, ga] = sidePair(x[field], x.home_id === id);
    return [f + gf, a + ga];
  }, [0, 0]);
  const withXg = games.filter((x) => x.xg);
  return { n: games.length, goals: total(games, "score"), nx: withXg.length, xg: total(withXg, "xg") };
}

/* one ruled board: home values, the metric in the middle, away values */
function sides(m, comp, table, clubs, files) {
  const ucl = comp.slug === "champions-league";
  const rated = clubs ? clubs.clubs : [];
  const club = (id) => rated.find((c) => c.id === id);
  const avg = Object.fromEntries(STRENGTH.map(([k]) => [k, rated.reduce((s, c) => s + c[k], 0) / Math.max(1, rated.length)]));
  const teams = table ? table.teams : [];
  const entry = (id) => { const i = teams.findIndex((t) => t.id === id); return i < 0 ? null : { t: teams[i], projected: i + 1 }; };
  const row = (label, cell) => {
    const [h, a] = [cell(m.home_id), cell(m.away_id)];
    return h || a ? `<tr><td class="h">${h}</td><th scope="row">${label}</th><td class="a">${a}</td></tr>` : "";
  };

  const strength = (key) => (id) => {
    const c = club(id);
    return c ? `<b>${dec(c[key])}</b> ${rankTag(c[`${key}_rank`])}<span class="meter"><i style="width:${c[key]}%"></i><em style="left:${avg[key]}%" title="Average club"></em></span>` : "";
  };
  const standing = (id) => {
    const e = entry(id);
    return e ? `<b>${ordinal(e.t.position)}</b> · ${e.t.points} pts <small>after ${e.t.played}</small>` : "";
  };
  const projected = (id) => {
    const e = entry(id);
    return e ? `<b>${ordinal(e.projected)}</b> · ${Math.round(e.t.xpts)} pts <small>80%: ${e.t.p10}–${e.t.p90}</small>` : "";
  };
  const form = (id) => {
    const last = played(id, m.kickoff).slice(-5);
    return last.length ? `<span class="mp-form">${last.map((x) => `<span data-tip="${x.tip}"><span class="res r${x.r}">${"WDL"[x.r]}</span><small>${x.gf}–${x.ga}</small></span>`).join("")}</span>` : "";
  };
  const goals = Object.fromEntries([m.home_id, m.away_id].map((id) => [id, seasonGoals(files, id, m.kickoff)]));
  const games = (n) => `${n} game${n === 1 ? "" : "s"}`;
  const perGame = ([f, a], n) => `<span class="mp-pair"><b>${dec(f / n, 2)}</b> – <b>${dec(a / n, 2)}</b></span>`;
  const goalCell = (id) => {
    const g = goals[id];
    return g.n ? `${perGame(g.goals, g.n)} <small>for – against · ${games(g.n)}</small>` : "";
  };
  const xgCell = (id) => {
    const g = goals[id];
    if (!g.n) return "";
    return g.nx ? `${perGame(g.xg, g.nx)} <small>for – against · xG for ${g.nx} of ${games(g.n)}</small>` : `<small>No xG for its ${games(g.n)}</small>`;
  };
  const anyXg = goals[m.home_id].nx || goals[m.away_id].nx;

  const rows = STRENGTH.map(([key, label]) => row(label, strength(key))).join("")
    + row(ucl ? "League phase" : "Table", standing)
    + row("Projected finish", projected)
    + row("Last five", form)
    + row("Goals per game", goalCell)
    + (anyXg ? row("xG per game", xgCell) : "");
  if (!rows) return "";
  return `<fieldset class="frame"><legend>The two sides</legend>
    <div class="scroll"><table class="board mp-sides">
      <thead><tr><th class="h">${clubName(m.home_id, m.home, "inline")}</th><th></th><th class="a">${clubName(m.away_id, m.away, "inline")}</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="note">Ratings are the share of points against an average European top-flight side, ranked among ${rated.length} clubs; the tick is the average club. ${ucl ? "League-phase place and points" : "Place and points"} are today's; the projected finish is the place in the projected table, with its 80% points range. Last five and goals count every competition we cover, before kickoff; xG is Understat's chance quality, which covers the five leagues only.</p>
  </fieldset>`;
}
