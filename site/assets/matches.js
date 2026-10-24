// Matches view: one day's fixtures across the six competitions, with the model's call on each.
import {
  COMPS, compBySlug, $, esc, getJSON, setStatus, clock, shortDate, dayKey, parseDay, shiftDay, verdict, pick, pct1, dec,
  expandable, bulb, outcome, callScore, clubName, num, pct, loadForm, formDots, streak, meetings,
} from "./core.js";

import { renderScorecardTable } from "./scorecard.js";
import { cardChips, offerCard, roundCard } from "./cards.js";

const OUTCOMES = ["Home win", "Draw", "Away win"];
export const PENDING = { POSTPONED: "Postponed", SUSPENDED: "Suspended", CANCELLED: "Cancelled" };
/* the chances a fixture's stakes track: league title, top four and drop; Champions League winner, top eight and top 24 */
const STAKES = {
  league: [["title", "Title", "Title race"], ["ucl", "Top 4", "Top-four race"], ["releg", "Drop", "Relegation battle"]],
  ucl: [["title", "Winner", "Trophy race"], ["top8", "Top 8", "Top-eight race"], ["top24", "Top 24", "Top-24 race"]],
};
export const stakeKinds = (slug) => STAKES[slug === "champions-league" ? "ucl" : "league"];
/* points a result must swing a chance by before it is shown at all: title races are the point of the site,
   while place races swing widely in most games, so small swings would tag every fixture. A Champions League
   game is an eighth of the league phase, so it moves someone's top-eight or top-24 chance by 25 points or more
   almost every time; its bar is higher still. */
export const BIG_STAKE = { title: 8, ucl: 15, releg: 15, top8: 30, top24: 30 };
/* a club's chance today from its competition table, for a stakes metric */
export const stakeNow = (t, key) => (key === "top8" ? t.r16 : key === "top24" ? t.r16 + t.playoff : t[key]);
let data = null;
let comp = "all";
let lens = "score"; // judge played games by the score, or by which side had the better chances (xG)
let day = null;
let slide = null;
let dragOffset = 0;
let matterShown = false;

async function load() {
  if (data) return data;
  const [index, clubs, ...files] = await Promise.all([
    getJSON("index.json"),
    getJSON("clubs.json").catch(() => null),
    ...COMPS.map((c) => getJSON(`matches/${c.slug}.json`).catch(() => null)),
  ]);
  const byDay = new Map();
  const comps = [];
  files.forEach((file, i) => {
    const slug = COMPS[i].slug;
    if (!file) return;
    comps.push({ slug, file });
    for (const m of file.matches) {
      const key = dayKey(new Date(m.kickoff));
      if (!byDay.has(key)) byDay.set(key, []);
      byDay.get(key).push({ comp: slug, m });
    }
  });
  for (const list of byDay.values()) list.sort((a, b) => a.m.kickoff.localeCompare(b.m.kickoff));
  const latest = index.reduce((a, b) => (a.generated_at > b.generated_at ? a : b));
  const slugs = new Map((clubs ? clubs.clubs : []).map((c) => [c.id, c.slug]));
  data = { byDay, comps, latest, slugs, missing: COMPS.filter((_, i) => !files[i]).map((c) => c.label) };
  return data;
}

export async function showMatches(param) {
  document.title = "Matches · Floodlight";
  try {
    await load();
  } catch (err) {
    $("m-day").innerHTML = `<p class="note">Matches could not be loaded (${esc(err.message)}).</p>`;
    return;
  }
  await loadForm().catch(() => {});
  setStatus(data.latest.generated_at);
  const next = /^\d{4}-\d{2}-\d{2}$/.test(param || "") ? param : dayKey(new Date());
  // Moving to another day slides the strip and the fixtures across; a finished drag slides on from where it let go.
  slide = day && next !== day ? { days: daysBetween(day, next), from: dragOffset } : null;
  dragOffset = 0;
  day = next;
  render();
  slide = null;
  if (!matterShown) { matterShown = true; await renderMatter(); }
}

const daysBetween = (a, b) => Math.round((parseDay(b) - parseDay(a)) / 864e5);
const still = matchMedia("(prefers-reduced-motion: reduce)");
const SLIDE = { duration: 260, easing: "cubic-bezier(.2, .8, .2, 1)" };

const visible = (key) => (data.byDay.get(key) || []).filter((x) => comp === "all" || x.comp === comp);

function render() {
  renderDays();
  renderChips();
  renderDay();
  renderScorecardTable(lens);
}

/* ---------- day strip ---------- */
const SPARE = 8; // days drawn either side of the chosen one, more than fit, so a drag or slide never shows a gap

function renderDays() {
  const today = dayKey(new Date());
  const cells = [];
  for (let i = -SPARE; i <= SPARE; i++) {
    const key = shiftDay(day, i);
    const d = parseDay(key);
    const n = visible(key).length;
    const label = key === today ? "Today" : d.toLocaleDateString("en-GB", { weekday: "short" });
    const off = Math.abs(i) > 4 ? ' tabindex="-1" aria-hidden="true"' : "";
    cells.push(`<a class="day${n ? "" : " empty"}" href="#matches/${key}" draggable="false"${key === day ? ' aria-current="date"' : ""}${off}
      aria-label="${esc(d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }))}, ${n} matches">
      <span class="wd">${label}</span><span class="dn">${d.getDate()}</span><span class="mo">${d.toLocaleDateString("en-GB", { month: "short" })}</span>
      <span class="ct">${n ? `${n} game${n > 1 ? "s" : ""}` : "–"}</span></a>`);
  }
  $("days").innerHTML = `
    <a class="step" href="#matches/${shiftDay(day, -1)}" aria-label="Previous day">‹</a>
    <div class="day-row"><div class="day-track" style="--total:${2 * SPARE + 1}">${cells.join("")}</div></div>
    <a class="step" href="#matches/${shiftDay(day, 1)}" aria-label="Next day">›</a>`;
  if (slide) {
    const track = $("days").querySelector(".day-track");
    const w = cellWidth(track);
    const reach = maxReach(track) / w;
    slideTrack(track, Math.max(-reach, Math.min(reach, slide.days)) * w + slide.from);
  }
}

const cellWidth = (track) => track.offsetWidth / (2 * SPARE + 1);
/* how far the strip can move before running out of spare days */
const maxReach = (track) => cellWidth(track) * (SPARE - (Number(getComputedStyle(track.parentElement).getPropertyValue("--n")) || 9) / 2);

function slideTrack(track, from) {
  if (still.matches || !from) return;
  track.animate([{ transform: `translateX(${from}px)` }, { transform: "none" }], SLIDE);
}

/* drag the strip (mouse, pen or finger) to move through the days */
let drag = null;
let dragged = false;
$("days").addEventListener("pointerdown", (e) => {
  const row = e.target.closest(".day-row");
  if (!row || e.button !== 0) return;
  drag = { id: e.pointerId, x: e.clientX, y: e.clientY, dx: 0, live: false, row, track: row.firstElementChild };
});
$("days").addEventListener("pointermove", (e) => {
  if (!drag || e.pointerId !== drag.id) return;
  const dx = e.clientX - drag.x;
  if (!drag.live) {
    if (Math.abs(dx) < 6) return;
    if (Math.abs(e.clientY - drag.y) > Math.abs(dx)) { drag = null; return; }
    drag.live = true;
    drag.row.setPointerCapture(e.pointerId);
    drag.row.classList.add("dragging");
    drag.track.getAnimations().forEach((a) => a.cancel());
  }
  const max = maxReach(drag.track);
  drag.dx = Math.max(-max, Math.min(max, dx));
  drag.track.style.transform = `translateX(${drag.dx}px)`;
});
function endDrag(e) {
  if (!drag || e.pointerId !== drag.id) return;
  const { live, dx, row, track } = drag;
  drag = null;
  if (!live) return;
  row.classList.remove("dragging");
  // Swallow the click that ends a drag so it doesn't also open the day under the pointer.
  dragged = true;
  setTimeout(() => { dragged = false; });
  const cells = Math.abs(dx) / cellWidth(track);
  const shift = e.type === "pointercancel" ? 0 : -Math.sign(dx) * Math.round(cells + 0.2);
  track.style.transform = "";
  if (!shift) { slideTrack(track, dx); return; }
  dragOffset = dx;
  location.hash = `#matches/${shiftDay(day, shift)}`;
}
$("days").addEventListener("pointerup", endDrag);
$("days").addEventListener("pointercancel", endDrag);
$("days").addEventListener("click", (e) => { if (dragged) { e.preventDefault(); e.stopPropagation(); } }, true);
$("days").addEventListener("dragstart", (e) => e.preventDefault());

function renderChips() {
  const all = data.byDay.get(day) || [];
  const chips = [{ slug: "all", label: "All" }, ...COMPS].map((c) => {
    const n = c.slug === "all" ? all.length : all.filter((x) => x.comp === c.slug).length;
    return `<button type="button" class="chip" data-comp="${c.slug}" aria-pressed="${comp === c.slug}">${c.label}<span>${n}</span></button>`;
  });
  $("m-chips").innerHTML = chips.join("");
}
$("m-chips").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-comp]");
  if (!b) return;
  comp = b.dataset.comp;
  render();
});

$("m-lens").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-lens]");
  if (!b || b.dataset.lens === lens) return;
  lens = b.dataset.lens;
  $("m-lens").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  render();
});

/* the call judged on chances: did the model's favourite out-xG its opponent? From the exported `miss.xg`, where a
   margin of 0.5 xG or less is level (see the site data contract); null before full time or without a forecast */
function xgVerdict(m) {
  if (!m.score || !m.p) return null;
  return { won: "hit", lost: "miss", level: "level" }[m.miss && m.miss.xg] || "none";
}

/* ---------- the day's fixtures ---------- */
function renderDay() {
  const list = visible(day);
  const d = parseDay(day);
  const title = d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
  const calls = list.map((x) => verdict(x.m)).filter(Boolean);
  const hits = calls.filter((v) => v.hit).length;
  const summary = list.length
    ? `${list.length} match${list.length > 1 ? "es" : ""}${calls.length ? ` · ${calls.length} played · ${lens === "xg" ? xgSummary(list) : `model called <b>${hits} of ${calls.length}</b>`}` : ""}`
    : "No matches in the competitions we cover.";
  // "How we did": the round card of the day's finished games with a forecast, for the competitions on show
  const played = list.filter((x) => x.m.score && x.m.p);
  if (played.length) {
    const shown = comp === "all" ? COMPS.filter((c) => played.some((x) => x.comp === c.slug)) : [compBySlug[comp]];
    const scope = shown.length > 1 ? "All competitions" : stageLabel(shown[0], played);
    offerCard("round", () => roundCard(played.map((x) => x.m), { day: { key: day, label: title }, scope }));
  }
  let html = `<div class="day-head"><h1>${esc(title)}</h1><p>${summary}</p>${list.length ? "" : nearby()}${played.length ? cardChips("round", "how we did") : ""}</div>`;
  for (const c of COMPS) {
    const rows = list.filter((x) => x.comp === c.slug);
    if (!rows.length) continue;
    html += `<fieldset class="frame comp-day"><legend>${esc(stageLabel(c, rows))}</legend>
      <div class="mlist">${rows.map((x) => matchRow(x.m, x.comp, null, "", lens)).join("")}</div></fieldset>`;
  }
  if (data.missing.length) html += `<p class="note">No fixture data yet for ${esc(data.missing.join(", "))}.</p>`;
  $("m-day").innerHTML = html;
  if (slide && !still.matches) {
    const x = `${Math.sign(slide.days) * 28}px`;
    $("m-day").animate([{ opacity: 0, transform: `translateX(${x})` }, { opacity: 1, transform: "none" }], SLIDE);
  }
}

/* "favourite had the better chances in 5 of 6 · 2 level · 1 without xG": level games are left out of the rate */
function xgSummary(list) {
  const n = { hit: 0, miss: 0, level: 0, none: 0 };
  list.map((x) => xgVerdict(x.m)).filter(Boolean).forEach((k) => n[k]++);
  const clear = n.hit + n.miss;
  return [clear ? `favourite had the better chances in <b>${n.hit} of ${clear}</b>` : "no clear xG winner",
    n.level && `${n.level} level`, n.none && `${n.none} without xG`].filter(Boolean).join(" · ");
}

export function stageLabel(c, rows) {
  const md = [...new Set(rows.map((x) => x.m.md).filter(Boolean))];
  const stage = rows[0].m.stage;
  if (stage && stage !== "LEAGUE_STAGE") return `${c.label} · ${stage.replace(/_/g, " ").toLowerCase().replace(/^\w/, (s) => s.toUpperCase())}`;
  return md.length === 1 ? `${c.label} · Matchday ${md[0]}` : c.label;
}

/* the nearest days with fixtures, for an empty day */
function nearby() {
  const keys = [...data.byDay.keys()].filter((k) => visible(k).length).sort();
  const before = keys.filter((k) => k < day).pop();
  const after = keys.find((k) => k > day);
  const link = (k, text) => `<a href="#matches/${k}">${text} ${esc(parseDay(k).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }))}</a>`;
  return `<p class="jump">${[before && link(before, "← Previous:"), after && link(after, "Next:")].filter(Boolean).join(" · ")}</p>`;
}

export function probCells(m, labels = ["H", "D", "A"]) {
  if (!m.p) return `<span class="m-probs none">No forecast</span>`;
  const top = Math.max(...m.p);
  const actual = m.score ? outcome(m.score) : -1;
  return `<span class="m-probs">${m.p.map((p, i) => `<span class="pc${p === top ? " fav" : ""}${i === actual ? " act" : ""}"
      data-tip="${esc(`${OUTCOMES[i]}: <b>${(p * 100).toFixed(1)}%</b>${i === actual ? " · happened" : ""}`)}">
      <i style="background:${bulb(p, top)}"></i><b>${labels[i]}</b>${Math.round(p * 100)}</span>`).join("")}</span>`;
}

const XG_BADGE = { hit: "Called", miss: "Missed", level: "Level" };
function verdictBadge(m, lens = "score") {
  const v = verdict(m);
  if (v && lens === "xg") {
    const k = xgVerdict(m);
    const [h, a] = m.xg || [];
    const tip = k === "none" ? "No xG for this game" : `xG ${dec(h, 2)}–${dec(a, 2)}: ${k === "level" ? "within 0.5, too close to call"
      : `the model's favourite ${k === "hit" ? "had" : "gave up"} the better chances`}`;
    return k === "none" ? `<span class="m-verdict wait" title="${tip}">No xG</span>`
      : `<span class="m-verdict ${k}" title="${esc(tip)}">${XG_BADGE[k]}</span>`;
  }
  if (v) {
    return `<span class="m-verdict ${v.hit ? "hit" : "miss"}">${v.hit ? "Called" : "Missed"}${v.exact ? `<em>Exact</em>` : ""}</span>`;
  }
  const reported = PENDING[m.reported || m.status];
  if (reported) return `<span class="m-verdict wait">${reported}</span>`;
  if (new Date(m.kickoff) < Date.now()) return `<span class="m-verdict wait">Result pending</span>`;
  if (!m.p) return "";
  const [h, a] = callScore(m);
  return `<span class="m-verdict pick">Pick <b>${h}–${a}</b></span>`;
}

/* the chances a result moves a lot, as {team, key, word, race, values} with the biggest swing first;
   null values are results too rare in the simulations to show */
const spread = (values) => Math.max(...values.filter((v) => v != null)) - Math.min(...values.filter((v) => v != null));
export function stakeLines(m, slug) {
  const lines = (m.stakes ? m.stakes.teams : []).flatMap((t) => stakeKinds(slug).filter(([key]) => t[key]).map(([key, word, race]) => ({ team: t, key, word, race, values: t[key] })));
  return lines.filter((line) => spread(line.values) >= BIG_STAKE[line.key]).sort((a, b) => spread(b.values) - spread(a.values));
}

/* a ruled tag on fixtures where a result moves someone's title, top-four or relegation chance a lot */
function stakeBadge(m, slug) {
  const [top] = stakeLines(m, slug);
  if (!top) return "";
  const known = top.values.filter((v) => v != null);
  return `<span class="m-stake" title="${esc(`${top.race}: ${top.team.name} ${num(Math.min(...known))}–${num(Math.max(...known))}%`)}">Stakes</span>`;
}

/* `when` replaces the kickoff column, e.g. with the round and date when listing one team's games; `note` is a
   line under the row; `lens` "xg" judges a played game's call by the chances instead of the score */
export function matchRow(m, slug, when = null, note = "", lens = "score") {
  const status = m.score ? "FT" : PENDING[m.reported || m.status] ? "–" : clock(m.kickoff);
  const [hs, as] = m.score || ["", ""];
  const win = m.score ? outcome(m.score) : -1;
  return `<div class="mrow" role="button" tabindex="0" aria-expanded="false" data-c="${slug}" data-id="${m.id}">
    <span class="m-when">${when ? when(status) : status}</span>
    <span class="m-home${win === 0 ? " won" : ""}">${clubName(m.home_id, m.home)}${formDots(m.home_id, m.kickoff)}</span>
    <span class="m-hs">${hs}</span><span class="m-sep">${m.score ? "–" : "v"}</span><span class="m-as">${as}</span>
    <span class="m-away${win === 2 ? " won" : ""}">${clubName(m.away_id, m.away)}${formDots(m.away_id, m.kickoff)}</span>
    <span class="m-foot">${stakeBadge(m, slug)}${probCells(m)}<span class="m-exp">${m.exp ? `${dec(m.exp[0])}–${dec(m.exp[1])}` : ""}</span>${verdictBadge(m, lens)}</span>${note}
  </div>`;
}

/* a forecast fixture's likeliest scores, goal markets and the model's call, as three blocks shared by the
   expanded row and the match page; `links` closes the call block */
export function forecastBlocks(m, links = "") {
  const v = verdict(m);
  const fav = pick(m.p);
  const [ch, ca] = callScore(m);
  const max = m.top[0][2];
  const scores = m.top.map(([h, a, p]) => {
    const hit = m.score && m.score[0] === h && m.score[1] === a;
    const call = h === ch && a === ca;
    return `<li class="${hit ? "hit" : ""}${call ? " call" : ""}${outcome([h, a]) === fav ? "" : " off"}"><span>${h}–${a}</span><i style="width:${((p / max) * 100).toFixed(0)}%"></i><b>${pct1(p)}</b></li>`;
  }).join("");
  const spread = outcome(m.top[0]) !== fav
    ? `<p class="note">${m.top[0][0]}–${m.top[0][1]} tops the list, but a ${OUTCOMES[fav].toLowerCase()} is likelier overall: its chance is split across more scores.</p>` : "";
  const xg = m.xg ? `<dt>xG (Understat)</dt><dd>${dec(m.xg[0], 2)}–${dec(m.xg[1], 2)}</dd>` : "";
  const origin = new Date(m.at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  let call;
  if (v) {
    const result = OUTCOMES[v.actual].toLowerCase().replace("draw", "the draw");
    call = (v.hit
      ? `<p>Called it: the model picked a ${OUTCOMES[fav].toLowerCase()} (<b>${pct1(m.p[fav])}</b>), ${ch}–${ca}.`
      : `<p>Missed it: the model picked a ${OUTCOMES[fav].toLowerCase()} (<b>${pct1(m.p[fav])}</b>), ${ch}–${ca}; ${result} had <b>${pct1(v.given)}</b>.`)
      + (v.exact ? ` Exact score, too.</p>` : m.p_score != null ? ` The actual ${m.score[0]}–${m.score[1]} had <b>${pct1(m.p_score)}</b>.</p>`
        : ` The actual ${m.score[0]}–${m.score[1]} was not among the saved likeliest scores.</p>`)
      + `<p class="dim">${m.published ? `Published before kickoff, from the model run of ${new Date(m.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" })} UTC, ${new Date(m.at).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" })}.` : "Reconstructed: forecast as of 00:00 UTC on match day, from results before then."}</p>`;
  } else {
    call = `<p>Pick: <b>${OUTCOMES[fav].toLowerCase()}, ${ch}–${ca}</b> (${pct1(m.p[fav])} for the result).</p><p class="dim">Forecast from the model run of ${origin} UTC.</p>`;
  }
  return `<div><h4>Likeliest scores</h4><ol class="scores">${scores}</ol>${spread}</div>
    <div><h4>Goals</h4><dl class="kv"><dt>Expected goals</dt><dd>${dec(m.exp[0])}–${dec(m.exp[1])}</dd>${xg}
      <dt>Both teams score</dt><dd>${pct1(m.btts)}</dd><dt>Over 2.5 goals</dt><dd>${pct1(m.o25)}</dd></dl></div>
    <div class="call"><h4>The call</h4>${call}${links ? `<p class="links">${links}</p>` : ""}</div>`;
}

/* expanded: form, recent meetings and the forecast; `slugs` maps team ids to club profiles, `league` is the
   competition slug, which also links the match page */
export function matchPanel(m, slugs = null, league = null) {
  const panel = document.createElement("div");
  panel.className = "panel";
  const clubLinks = slugs ? [[m.home_id, m.home], [m.away_id, m.away]]
    .filter(([id]) => slugs.has(id))
    .map(([id, name]) => `<a class="more" href="#clubs/${slugs.get(id)}">${clubName(id, name, "inline")} →</a>`).join("") : "";
  const links = (league ? `<a class="more" href="#match/${league}/${m.id}">Match page →</a>` : "") + clubLinks;
  if (!m.p) {
    panel.innerHTML = `<p class="note">No forecast for this fixture.</p>${links ? `<p class="links">${links}</p>` : ""}`;
    return panel;
  }
  const form = (id, name) => {
    const dots = formDots(id, m.kickoff);
    const run = streak(id, m.kickoff);
    return dots ? `<span class="pform">${clubName(id, name, "inline")}${dots}${run ? `<small>${run}</small>` : ""}</span>` : "";
  };
  const formRow = form(m.home_id, m.home) + form(m.away_id, m.away);
  const past = meetings(m.home_id, m.away_id, m.kickoff);
  const h2h = past.length ? `<div class="pforms h2h"><h4>Head to head</h4>${past.map((x) => {
    const [hs, as] = x.h ? [x.gf, x.ga] : [x.ga, x.gf];
    return `<span class="pform"><small>${shortDate(x.k)}</small>${esc(x.h ? m.home : m.away)} <b>${hs}–${as}</b> ${esc(x.h ? m.away : m.home)}</span>`;
  }).join("")}</div>` : "";
  panel.innerHTML = `${formRow ? `<div class="pforms"><h4>Form</h4>${formRow}</div>` : ""}${h2h}${forecastBlocks(m, links)}`;
  if (league) addStakes(panel, m, league);
  return panel;
}

async function addStakes(panel, m, league) {
  const html = await stakesTable(m, league);
  if (!html) return;
  const block = document.createElement("div");
  block.className = "stakes";
  block.innerHTML = `<h4>What's at stake</h4>${html}`;
  panel.append(block);
}

/* "What's at stake": each affected team's chance now and under each result, from the league file's baseline;
   empty when no result swings a chance past the bar. After full time, `past` = { day, before(id, key) } shows it
   as saved before kickoff: the chance from the last refresh before the game, with the result that happened lit. */
export async function stakesTable(m, league, past = null) {
  const lines = stakeLines(m, league).slice(0, 6);
  if (!lines.length) return "";
  const table = past ? null : await getJSON(`${league}.json`).catch(() => null);
  const now = new Map((table ? table.teams : []).map((t) => [t.id, t]));
  const base = (id, key) => (past ? past.before(id, key) : now.has(id) ? stakeNow(now.get(id), key) : null);
  const lit = past ? outcome(m.score) : pick(m.p);
  const cell = (v, i) => (v == null
    ? `<td class="dim" title="Too few simulations">–</td>`
    : `<td${i === lit ? ' class="lit"' : ""}>${pct(v)}</td>`);
  const rows = lines.map(({ team, key, word, values }) => `<tr><td class="l">${clubName(team.id, team.name, "inline")} <small>${word}</small></td>
    <td class="b">${base(team.id, key) == null ? "–" : pct(base(team.id, key))}</td>${values.map(cell).join("")}</tr>`).join("");
  return `<div class="scroll"><table class="board stakes-table"><thead><tr><th class="l"></th><th>${past ? "Before" : "Now"}</th>
    <th>If ${esc(m.home)} win</th><th>Draw</th><th>If ${esc(m.away)} win</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="note">${league === "champions-league"
      ? `A club's chance of winning the trophy, or of a top-eight or top-24 league-phase finish, once this result is in. Only swings of ${BIG_STAKE.title} points or more in a trophy chance, or ${BIG_STAKE.top8} in a top-eight or top-24 chance, are shown.`
      : `A team's chance of the title, a top-four finish or relegation once this result is in. Only swings of ${BIG_STAKE.title} points or more in a title chance, or ${BIG_STAKE.ucl} in a top-four or relegation chance, are shown.`}${past ? ` As saved before kickoff: “Before” is the chance at the refresh of ${esc(past.day)}, and the result that happened is lit.` : ""}</p>`;
}

const openRow = (row) => {
  const file = data.comps.find((c) => c.slug === row.dataset.c).file;
  return matchPanel(file.matches.find((m) => String(m.id) === row.dataset.id), data.slugs, row.dataset.c);
};
expandable($("m-day"), ".mrow", openRow);
expandable($("m-matter-list"), ".mrow", openRow);

/* ---------- games that matter ---------- */
/* Across every competition, the unplayed fixtures of the next seven days whose result swings a shown stakes line
   the most, as a multiple of that race's BIG_STAKE bar (so a title swing can outrank a bigger Champions League
   top-24 one), earlier kickoff first on a tie. */
const weight = (line) => spread(line.values) / BIG_STAKE[line.key];
async function renderMatter() {
  const now = Date.now();
  const games = data.comps.flatMap(({ slug, file }) => file.matches
    .filter((m) => !m.score && !PENDING[m.reported || m.status] && new Date(m.kickoff) > now && new Date(m.kickoff) <= now + 7 * 864e5)
    .map((m) => ({ slug, m, line: stakeLines(m, slug).reduce((a, b) => (!a || weight(b) > weight(a) ? b : a), null) }))
    .filter((x) => x.line))
    .sort((a, b) => weight(b.line) - weight(a.line) || a.m.kickoff.localeCompare(b.m.kickoff))
    .slice(0, 3);
  if (!games.length) return;
  const tables = new Map(await Promise.all([...new Set(games.map((x) => x.slug))]
    .map(async (slug) => [slug, await getJSON(`${slug}.json`).catch(() => null)])));
  $("m-matter-list").innerHTML = games.map(({ slug, m, line }) => {
    const c = compBySlug[slug];
    const when = (status) => `<b>${c.short}</b><br>${esc(new Date(m.kickoff).toLocaleDateString("en-GB", { weekday: "short", day: "numeric" }))}<br>${status}`;
    return matchRow(m, slug, when, swingLine(m, line, tables.get(slug)));
  }).join("");
  $("m-matter").hidden = false;
}

/* "Title: Barcelona 93% → 84% if they lose.": the chance now, and under the result that moves it furthest */
function swingLine(m, { team, key, word, values }, table) {
  const row = table && team.id != null ? table.teams.find((t) => t.id === team.id) : null;
  const from = row ? stakeNow(row, key) : values[pick(m.p)];
  const to = [0, 1, 2].filter((i) => values[i] != null).reduce((a, b) => (Math.abs(values[b] - from) > Math.abs(values[a] - from) ? b : a));
  const side = team.id != null ? [m.home_id, m.away_id].indexOf(team.id) : [m.home, m.away].indexOf(team.name);
  const result = side < 0 ? [`if ${m.home} win`, "with a draw", `if ${m.away} win`][to]
    : to === 1 ? "if they draw" : to === 2 * side ? "if they win" : "if they lose";
  return `<span class="m-swing">${esc(`${word}: ${team.name} ${pct(from)} → ${pct(values[to])} ${result}.`)}</span>`;
}

/* ---------- season record ---------- */
export function record(matches) {
  const played = matches.filter((m) => m.score && m.p);
  const calls = played.map(verdict);
  const n = played.length;
  return {
    n,
    hits: calls.filter((v) => v.hit).length,
    exact: calls.filter((v) => v.exact).length,
    home: played.filter((m) => outcome(m.score) === 0).length,
    given: n ? calls.reduce((s, v) => s + v.given, 0) / n : 0,
  };
}
