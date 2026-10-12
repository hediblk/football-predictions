// Matches view: one day's fixtures across the six competitions, with the model's call on each.
import {
  COMPS, compBySlug, $, esc, getJSON, setStatus, clock, dayKey, parseDay, shiftDay, verdict, pick, pct1, dec,
  expandable, bulb, outcome, callScore, clubName,
} from "./core.js";

const OUTCOMES = ["Home win", "Draw", "Away win"];
const PENDING = { POSTPONED: "Postponed", SUSPENDED: "Suspended", CANCELLED: "Cancelled" };
let data = null;
let comp = "all";
let day = null;
let slide = null;
let dragOffset = 0;

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
  document.title = "Matches · Final Table";
  try {
    await load();
  } catch (err) {
    $("m-day").innerHTML = `<p class="note">Matches could not be loaded (${esc(err.message)}).</p>`;
    return;
  }
  setStatus(data.latest.generated_at);
  const next = /^\d{4}-\d{2}-\d{2}$/.test(param || "") ? param : dayKey(new Date());
  // Moving to another day slides the strip and the fixtures across; a finished drag slides on from where it let go.
  slide = day && next !== day ? { days: daysBetween(day, next), from: dragOffset } : null;
  dragOffset = 0;
  day = next;
  render();
  slide = null;
}

const daysBetween = (a, b) => Math.round((parseDay(b) - parseDay(a)) / 864e5);
const still = matchMedia("(prefers-reduced-motion: reduce)");
const SLIDE = { duration: 260, easing: "cubic-bezier(.2, .8, .2, 1)" };

const visible = (key) => (data.byDay.get(key) || []).filter((x) => comp === "all" || x.comp === comp);

function render() {
  renderDays();
  renderChips();
  renderDay();
  renderRecord();
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

/* ---------- the day's fixtures ---------- */
function renderDay() {
  const list = visible(day);
  const d = parseDay(day);
  const title = d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
  const calls = list.map((x) => verdict(x.m)).filter(Boolean);
  const hits = calls.filter((v) => v.hit).length;
  const summary = list.length
    ? `${list.length} match${list.length > 1 ? "es" : ""}${calls.length ? ` · ${calls.length} played · model called <b>${hits} of ${calls.length}</b>` : ""}`
    : "No matches in the competitions we cover.";
  let html = `<div class="day-head"><h1>${esc(title)}</h1><p>${summary}</p>${list.length ? "" : nearby()}</div>`;
  for (const c of COMPS) {
    const rows = list.filter((x) => x.comp === c.slug);
    if (!rows.length) continue;
    html += `<fieldset class="frame comp-day"><legend>${esc(stageLabel(c, rows))}</legend>
      <div class="mlist">${rows.map((x) => matchRow(x.m, x.comp)).join("")}</div></fieldset>`;
  }
  if (data.missing.length) html += `<p class="note">No fixture data yet for ${esc(data.missing.join(", "))}.</p>`;
  $("m-day").innerHTML = html;
  if (slide && !still.matches) {
    const x = `${Math.sign(slide.days) * 28}px`;
    $("m-day").animate([{ opacity: 0, transform: `translateX(${x})` }, { opacity: 1, transform: "none" }], SLIDE);
  }
}

function stageLabel(c, rows) {
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

function probCells(m, labels = ["H", "D", "A"]) {
  if (!m.p) return `<span class="m-probs none">No forecast</span>`;
  const top = Math.max(...m.p);
  const actual = m.score ? outcome(m.score) : -1;
  return `<span class="m-probs">${m.p.map((p, i) => `<span class="pc${p === top ? " fav" : ""}${i === actual ? " act" : ""}"
      data-tip="${esc(`${OUTCOMES[i]}: <b>${(p * 100).toFixed(1)}%</b>${i === actual ? " · happened" : ""}`)}">
      <i style="background:${bulb(p, top)}"></i><b>${labels[i]}</b>${Math.round(p * 100)}</span>`).join("")}</span>`;
}

function verdictBadge(m) {
  const v = verdict(m);
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

/* `when` replaces the kickoff column, e.g. with the round and date when listing one team's games */
export function matchRow(m, slug, when = null) {
  const status = m.score ? "FT" : PENDING[m.reported || m.status] ? "–" : clock(m.kickoff);
  const [hs, as] = m.score || ["", ""];
  const win = m.score ? outcome(m.score) : -1;
  return `<div class="mrow" role="button" tabindex="0" aria-expanded="false" data-c="${slug}" data-id="${m.id}">
    <span class="m-when">${when ? when(status) : status}</span>
    <span class="m-home${win === 0 ? " won" : ""}">${clubName(m.home_id, m.home)}</span>
    <span class="m-hs">${hs}</span><span class="m-sep">${m.score ? "–" : "v"}</span><span class="m-as">${as}</span>
    <span class="m-away${win === 2 ? " won" : ""}">${clubName(m.away_id, m.away)}</span>
    <span class="m-foot">${probCells(m)}<span class="m-exp">${m.exp ? `${dec(m.exp[0])}–${dec(m.exp[1])}` : ""}</span>${verdictBadge(m)}</span>
  </div>`;
}

/* expanded: likeliest scores, goal markets and the model's call; `slugs` maps team ids to club profiles */
export function matchPanel(m, slugs = null) {
  const panel = document.createElement("div");
  panel.className = "panel";
  if (!m.p) {
    panel.innerHTML = `<p class="note">No forecast for this fixture.</p>`;
    return panel;
  }
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
      + (v.exact ? ` Exact score, too.</p>` : ` The actual ${m.score[0]}–${m.score[1]} had <b>${pct1(m.p_score || 0)}</b>.</p>`)
      + `<p class="dim">Forecast as of ${origin} UTC on match day, from results before then.</p>`;
  } else {
    call = `<p>Pick: <b>${OUTCOMES[fav].toLowerCase()}, ${ch}–${ca}</b> (${pct1(m.p[fav])} for the result).</p><p class="dim">Forecast from the model run of ${origin} UTC.</p>`;
  }
  const clubLinks = slugs ? [[m.home_id, m.home], [m.away_id, m.away]]
    .filter(([id]) => slugs.has(id))
    .map(([id, name]) => `<a class="more" href="#clubs/${slugs.get(id)}">${clubName(id, name, "inline")} →</a>`).join("") : "";
  panel.innerHTML = `
    <div><h4>Likeliest scores</h4><ol class="scores">${scores}</ol>${spread}</div>
    <div><h4>Goals</h4><dl class="kv"><dt>Expected goals</dt><dd>${dec(m.exp[0])}–${dec(m.exp[1])}</dd>${xg}
      <dt>Both teams score</dt><dd>${pct1(m.btts)}</dd><dt>Over 2.5 goals</dt><dd>${pct1(m.o25)}</dd></dl></div>
    <div class="call"><h4>The call</h4>${call}${clubLinks ? `<p class="links">${clubLinks}</p>` : ""}</div>`;
  return panel;
}

expandable($("m-day"), ".mrow", (row) => {
  const file = data.comps.find((c) => c.slug === row.dataset.c).file;
  return matchPanel(file.matches.find((m) => String(m.id) === row.dataset.id), data.slugs);
});

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

function renderRecord() {
  const rows = data.comps.map(({ slug, file }) => ({ label: compBySlug[slug].label, ...record(file.matches) }));
  const total = record(data.comps.flatMap((c) => c.file.matches));
  const share = (k, n) => (n ? `${Math.round((100 * k) / n)}%` : "–");
  const line = (r, cls = "") => `<tr class="${cls}"><td class="club l">${esc(r.label)}</td><td>${r.n}</td>
    <td class="b">${r.hits}</td><td class="lit">${share(r.hits, r.n)}</td><td>${share(r.exact, r.n)}</td>
    <td>${share(r.home, r.n)}</td><td>${r.n ? pct1(r.given) : "–"}</td></tr>`;
  $("m-record-table").innerHTML = `<thead><tr><th class="club l">Competition</th><th>Played</th><th>Called</th><th>Hit rate</th>
      <th>Exact score</th><th>Home-win baseline</th><th>Avg chance given</th></tr></thead>
    <tbody>${rows.map((r) => line(r)).join("")}${line({ label: "All", ...total }, "total")}</tbody>`;
}
