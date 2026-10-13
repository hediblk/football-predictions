// Clubs view: a strength ranking for the five leagues and a profile for every club.
import {
  LEAGUES, compBySlug, $, esc, getJSON, setStatus, ordinal, pct, pct1, dec, verdict, sideProbs, sidePair,
  outcome, expandable, bulb, shortDate, clock, callScore, clubName,
} from "./core.js";
import { matchPanel, record, BIG_STAKE } from "./matches.js";
import { spreadPanel } from "./tables.js";

const RESULT = ["W", "D", "L"];
const RESULT_WORD = ["Win", "Draw", "Loss"];
let clubs = null;
let leagueFilter = "all";
let sortKey = "rating";
let showAll = false;
let profile = null; // matches shown on the open profile, by id

export async function showClubs(slug) {
  try {
    clubs = await getJSON("clubs.json");
  } catch (err) {
    $("clubs-index").hidden = false;
    $("club-profile").hidden = true;
    $("c-hero").innerHTML = `<div class="who"><h1>No signal</h1><p class="caption">Club ratings could not be loaded (${esc(err.message)}).</p></div>`;
    return;
  }
  setStatus(clubs.generated_at);
  const club = slug && clubs.clubs.find((c) => c.slug === slug);
  $("clubs-index").hidden = Boolean(club);
  $("club-profile").hidden = !club;
  if (club) await showProfile(club);
  else await showIndex();
}

const leagueName = (slug) => compBySlug[slug].label;
/* a category rank: #1 lit, top ten warm, the rest dim */
const rankTag = (rank, tag = "small", cls = "") => `<${tag} class="crk${rank === 1 ? " first" : rank <= 10 ? " top" : ""}${cls}">#${rank}</${tag}>`;
const leagueTables = () => Promise.all(LEAGUES.map((l) => getJSON(`${l.slug}.json`).catch(() => null)));
const rowFor = (tables, club) => {
  const table = tables.find((t) => t && t.slug === club.league);
  return table ? table.teams.find((t) => t.id === club.id) : null;
};

/* ---------- weekly ranks ---------- */
const KEYS = ["rating", "attack", "defense"];
const weekDay = (iso) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
/* one frozen Monday's values for the given clubs, with ranks (descending; ties share the better rank) */
function weekRanks(week, ids) {
  const out = {};
  for (const id of ids) {
    const v = week?.clubs[id];
    if (v) out[id] = Object.fromEntries(KEYS.map((k, i) => [k, { v: v[i] }]));
  }
  for (const k of KEYS) {
    const vals = Object.values(out).map((o) => o[k].v);
    for (const o of Object.values(out)) o[k].rank = 1 + vals.filter((x) => x > o[k].v).length;
  }
  return out;
}
/* places climbed (positive) or lost, as arrow + number with a spoken label; "new" for a club without a previous week */
function move(delta, since) {
  if (delta == null) return "";
  if (delta === "new") return `<span class="mv new" aria-label="new this week" title="new this week">new</span>`;
  const label = delta === 0 ? `unchanged since ${since}` : `${delta > 0 ? "up" : "down"} ${Math.abs(delta)} ${Math.abs(delta) === 1 ? "place" : "places"} since ${since}`;
  const body = delta > 0 ? `▲<b>${delta}</b>` : delta < 0 ? `▼<b>${-delta}</b>` : "–";
  return `<span class="mv ${delta > 0 ? "up" : delta < 0 ? "down" : "flat"}" aria-label="${label}" title="${label}">${body}</span>`;
}
/* the Monday (UTC) of the week holding `iso`, as YYYY-MM-DD */
const mondayOf = (iso) => {
  const d = new Date(iso);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
};
/* The ranking shows the live clubs.json values and ranks, the same numbers as the hero, the profiles and the scatter.
   Arrows compare each live rank with the last Monday frozen before this week, so a Monday refresh still shows the
   week's movement. With no earlier Monday there are no arrows; a club missing from it is "new". */
function weeklyView(history) {
  const monday = mondayOf(clubs.generated_at);
  const base = (history?.weeks || []).filter((w) => w.date < monday).at(-1);
  const prev = weekRanks(base, clubs.clubs.map((c) => c.id));
  const byId = {};
  for (const c of clubs.clubs) {
    byId[c.id] = Object.fromEntries(KEYS.map((k) => {
      const rank = c[`${k}_rank`];
      const before = prev[c.id]?.[k];
      return [k, { v: c[k], rank, d: !base ? null : before ? before.rank - rank : "new" }];
    }));
  }
  return { byId, since: base ? base.date : null };
}
let view = null;

/* ---------- index ---------- */
async function showIndex() {
  document.title = "Clubs · Floodlight";
  const [tables, history] = await Promise.all([
    leagueTables(),
    getJSON(`history/${clubs.season.split("/")[0]}/clubs.json`).catch(() => null),
  ]);
  view = weeklyView(history);
  const list = clubs.clubs;
  const [best] = list;
  const topAttack = list.find((c) => c.attack_rank === 1);
  const topDefense = list.find((c) => c.defense_rank === 1);
  $("c-legend").textContent = `Club strength · ${clubs.season}`;
  $("c-hero").innerHTML = `
    <div class="who">
      <h1><a href="#clubs/${best.slug}">${clubName(best.id, best.name, "hero")}</a></h1>
      <p class="caption">The strongest club in Europe's top five leagues: it would take <b>${Math.round(best.rating)}%</b> of the points off an average European top-flight side ·
        best attack <b>${clubName(topAttack.id, topAttack.name, "inline")} ${dec(topAttack.attack)}</b> · best defence <b>${clubName(topDefense.id, topDefense.name, "inline")} ${dec(topDefense.defense)}</b> · ${list.length} clubs rated</p>
    </div>
    <div class="numeral on" role="img" aria-label="${esc(`${best.name}: rating ${dec(best.rating)}`)}">${Math.round(best.rating)}<sup>%</sup></div>`;

  $("c-board").innerHTML = clubs.featured.map((id) => {
    const c = list.find((x) => x.id === id);
    const row = rowFor(tables, c);
    const place = row ? `${ordinal(row.position)} in ${leagueName(c.league)}` : leagueName(c.league);
    return `<a class="cell" href="#clubs/${c.slug}">
      <span class="nm">${clubName(c.id, c.name, "card")}</span>
      <span class="lg">${esc(place)}</span>
      <span class="rt">${dec(c.rating)}</span>
      ${rankTag(c.rating_rank, "span", " rk")}
      <span class="ad"><span>Att</span><i style="--w:${c.attack}%"></i><b>${dec(c.attack)}</b></span>
      <span class="ad def"><span>Def</span><i style="--w:${c.defense}%"></i><b>${dec(c.defense)}</b></span>
    </a>`;
  }).join("");

  renderRanking(tables);
  renderScatter();
}

function renderRanking(tables) {
  const chips = [{ slug: "all", label: "All leagues" }, ...LEAGUES];
  $("c-chips").innerHTML = chips.map((l) => `<button type="button" class="chip" data-league="${l.slug}" aria-pressed="${leagueFilter === l.slug}">${esc(l.label)}</button>`).join("");
  const w = (c) => view.byId[c.id];
  const shown = clubs.clubs.filter((c) => leagueFilter === "all" || c.league === leagueFilter)
    .sort((a, b) => w(b)[sortKey].v - w(a)[sortKey].v || w(a)[sortKey].rank - w(b)[sortKey].rank || a.rating_rank - b.rating_rank);
  const limit = showAll || leagueFilter !== "all" ? shown.length : 25;
  const sortable = (key, label) => `<th aria-sort="${sortKey === key ? "descending" : "none"}"><button type="button" data-sort="${key}">${label}${sortKey === key ? " ▾" : ""}</button></th>`;
  const since = view.since && weekDay(view.since);
  /* a strength cell: the value in bold, then its rank and movement, with a hairline meter underneath */
  const strength = (m, tag) => `<td class="ad"><b>${dec(m.v)}</b>${tag ? ` ${rankTag(m.rank)}${move(m.d, since)}` : ""}<i style="--w:${m.v}%"></i></td>`;
  $("c-rank").innerHTML = `<thead><tr><th class="rk l">#</th><th class="mvc" title="Rating places gained or lost since last week" aria-label="Rating places gained or lost since last week">±</th><th class="club l">Club</th><th class="l">League</th>
      ${sortable("rating", "Rating")}${sortable("attack", "Attack")}${sortable("defense", "Defence")}
      <th class="sec">Scores</th><th class="sec">Concedes</th><th>Now</th></tr></thead>
    <tbody>${shown.slice(0, limit).map((c, i) => {
      const row = rowFor(tables, c);
      const m = w(c);
      return `<tr class="${clubs.featured.includes(c.id) ? "featured" : ""}">
        <td class="rk l">${String(i + 1).padStart(2, "0")}</td>
        <td class="mvc">${move(m.rating.d, since)}</td>
        <td class="club l"><a href="#clubs/${c.slug}">${clubName(c.id, c.name)}</a></td>
        <td class="l lg">${esc(compBySlug[c.league].short)}</td>
        ${strength(m.rating)}${strength(m.attack, true)}${strength(m.defense, true)}
        <td class="sec">${dec(c.gf, 2)}</td><td class="sec">${dec(c.ga, 2)}</td>
        <td>${row ? (row.position === 1 ? `<span class="crk first">1st</span>` : ordinal(row.position)) : "–"}</td></tr>`;
    }).join("")}</tbody>`;
  $("c-more").hidden = limit >= shown.length;
  $("c-more").textContent = `Show all ${shown.length} clubs`;
  $("c-rank-note").textContent = since
    ? `Live ratings, the same as on each club's page. Arrows show places gained or lost since the ranking frozen on Monday ${since}.`
    : "Live ratings, the same as on each club's page. Movement appears once a Monday ranking has been frozen.";
  renderMoves(shown);
}

/* the three biggest risers and fallers by rank change, per measure, among the clubs on show */
function renderMoves(shown) {
  $("c-moves-frame").hidden = !view.since;
  if (!view.since) return;
  const since = weekDay(view.since);
  $("c-moves-legend").textContent = `Since Monday ${since}`;
  const list = (k, sign) => shown.filter((c) => typeof view.byId[c.id][k].d === "number" && view.byId[c.id][k].d * sign > 0)
    .sort((a, b) => (view.byId[b.id][k].d - view.byId[a.id][k].d) * sign || view.byId[a.id][k].rank - view.byId[b.id][k].rank)
    .slice(0, 3).map((c) => {
      const m = view.byId[c.id][k];
      return `<li><a href="#clubs/${c.slug}">${clubName(c.id, c.name)}</a>${move(m.d, since)}<small>#${m.rank}</small></li>`;
    }).join("") || `<li class="empty">None</li>`;
  $("c-moves").innerHTML = [["rating", "Overall"], ["attack", "Attack"], ["defense", "Defence"]].map(([k, label]) => `
    <section><h3>${label}</h3>
      <h4>Risers</h4><ol>${list(k, 1)}</ol>
      <h4>Fallers</h4><ol>${list(k, -1)}</ol></section>`).join("");
}

$("c-chips").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-league]");
  if (!b) return;
  leagueFilter = b.dataset.league;
  renderRanking(await leagueTables());
  renderScatter();
});
$("c-rank").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-sort]");
  if (!b) return;
  sortKey = b.dataset.sort;
  renderRanking(await leagueTables());
});
$("c-more").addEventListener("click", async () => {
  showAll = true;
  renderRanking(await leagueTables());
});

/* attack against defence: one dot per club, the featured (or filtered) clubs lit and named where they fit */
function renderScatter() {
  const all = clubs.clubs;
  const lit = leagueFilter === "all" ? new Set(clubs.featured) : new Set(all.filter((c) => c.league === leagueFilter).map((c) => c.id));
  // Drawn at the container's width so text stays legible on phones.
  const W = Math.round(Math.min(640, Math.max(300, $("c-scatter").clientWidth || 640)));
  const H = Math.round(Math.max(300, W * 0.66)), pad = { l: 40, r: 12, t: 16, b: 40 };
  const xs = all.map((c) => c.attack), ys = all.map((c) => c.defense);
  const lo = Math.floor(Math.min(...xs, ...ys) / 10) * 10, hi = Math.ceil(Math.max(...xs, ...ys) / 10) * 10;
  const x = (v) => pad.l + ((v - lo) / (hi - lo)) * (W - pad.l - pad.r);
  const y = (v) => H - pad.b - ((v - lo) / (hi - lo)) * (H - pad.t - pad.b);
  const mean = (k) => all.reduce((sum, c) => sum + c[k], 0) / all.length;
  const ticks = [];
  for (let v = lo; v <= hi; v += 10) {
    ticks.push(`<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="${pad.t}" y2="${H - pad.b}"/><text class="tick" x="${x(v)}" y="${H - pad.b + 16}" text-anchor="middle">${v}</text>`);
    ticks.push(`<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="tick" x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text>`);
  }
  const mx = x(mean("attack")), my = y(mean("defense"));

  // Greedy labels: brightest clubs first, each tries right, left, above, below and is skipped if it would collide.
  const taken = [];
  const free = (b) => b.x1 >= pad.l && b.x2 <= W - pad.r && b.y1 >= pad.t && b.y2 <= H - pad.b
    && !taken.some((t) => b.x1 < t.x2 && b.x2 > t.x1 && b.y1 < t.y2 && b.y2 > t.y1);
  const corners = [["Strong at both ends", W - pad.r - 4, pad.t + 14, "end"], ["Defence first", pad.l + 6, pad.t + 14, "start"],
    ["Attack first", W - pad.r - 4, H - pad.b - 8, "end"], ["Weak at both ends", pad.l + 6, H - pad.b - 8, "start"]];
  for (const [text, cx, cy, anchor] of corners) {
    const w = text.length * 7.4;
    taken.push({ x1: anchor === "end" ? cx - w : cx, x2: anchor === "end" ? cx : cx + w, y1: cy - 11, y2: cy + 3 });
  }
  const litClubs = all.filter((c) => lit.has(c.id)).sort((a, b) => b.rating - a.rating);
  for (const c of litClubs) taken.push({ x1: x(c.attack) - 6, x2: x(c.attack) + 6, y1: y(c.defense) - 6, y2: y(c.defense) + 6 });
  const labels = [];
  for (const c of litClubs.slice(0, 16)) {
    const w = c.name.length * 6.4 + 2, cx = x(c.attack), cy = y(c.defense);
    const above = { y1: cy - 22, y2: cy - 8 }, below = { y1: cy + 8, y2: cy + 22 };
    const spots = [
      [cx + 9, cy + 4, "start", { x1: cx + 8, x2: cx + 9 + w, y1: cy - 8, y2: cy + 5 }],
      [cx - 9, cy + 4, "end", { x1: cx - 9 - w, x2: cx - 8, y1: cy - 8, y2: cy + 5 }],
      [cx, cy - 11, "middle", { x1: cx - w / 2, x2: cx + w / 2, ...above }],
      [cx, cy + 20, "middle", { x1: cx - w / 2, x2: cx + w / 2, ...below }],
      [cx + 4, cy - 11, "end", { x1: cx + 4 - w, x2: cx + 4, ...above }],
      [cx + 4, cy + 20, "end", { x1: cx + 4 - w, x2: cx + 4, ...below }],
      [cx - 4, cy - 11, "start", { x1: cx - 4, x2: cx - 4 + w, ...above }],
      [cx - 4, cy + 20, "start", { x1: cx - 4, x2: cx - 4 + w, ...below }],
    ];
    const spot = spots.find(([, , , box]) => free(box));
    if (!spot) continue;
    taken.push(spot[3]);
    labels.push(`<text class="lbl" x="${spot[0]}" y="${spot[1]}" text-anchor="${spot[2]}">${esc(c.name)}</text>`);
  }
  const order = [...all].sort((a, b) => lit.has(a.id) - lit.has(b.id));
  const dots = order.map((c) => {
    const on = lit.has(c.id);
    const tip = `${clubName(c.id, c.name, "inline")} · ${esc(leagueName(c.league))}<br>Attack <b>${dec(c.attack)}</b> · Defence <b>${dec(c.defense)}</b> · Rating <b>${dec(c.rating)}</b>`;
    return `<a href="#clubs/${c.slug}" class="pt${on ? " on" : ""}" data-tip="${esc(tip)}" tabindex="-1">
      <circle class="hit" cx="${x(c.attack)}" cy="${y(c.defense)}" r="12"/><circle class="dot" cx="${x(c.attack)}" cy="${y(c.defense)}" r="${on ? 5 : 3.5}"/></a>`;
  }).join("");
  $("c-scatter").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Attack rating against defence rating for every club; the ranking table lists the same values">
    ${ticks.join("")}
    <line class="avg" x1="${mx}" x2="${mx}" y1="${pad.t}" y2="${H - pad.b}"/><line class="avg" x1="${pad.l}" x2="${W - pad.r}" y1="${my}" y2="${my}"/>
    <line class="diag" x1="${x(lo)}" y1="${y(lo)}" x2="${x(hi)}" y2="${y(hi)}"/>
    ${corners.map(([text, cx, cy, anchor]) => `<text class="quad" x="${cx}" y="${cy}" text-anchor="${anchor}">${text}</text>`).join("")}
    <text class="axis" x="${W - pad.r}" y="${H - 6}" text-anchor="end">Attack rating →</text>
    <text class="axis" x="12" y="${pad.t}" transform="rotate(-90 12 ${pad.t})" text-anchor="end">Defence rating →</text>
    ${dots}${labels.join("")}</svg>`;
  $("c-scatter-note").textContent = (leagueFilter === "all"
    ? "The twelve big clubs are lit. "
    : `${leagueName(leagueFilter)} clubs are lit. `)
    + "Hover a dot for its numbers. The lines mark the five-league average; clubs on the diagonal are as strong in attack as in defence.";
}

/* ---------- profile ---------- */
async function showProfile(club) {
  document.title = `${club.name} · Floodlight`;
  const comp = compBySlug[club.league];
  const [table, leagueMatches, ucl, uclMatches] = await Promise.all([
    getJSON(`${club.league}.json`),
    getJSON(`matches/${club.league}.json`).catch(() => null),
    club.ucl ? getJSON("champions-league.json").catch(() => null) : null,
    club.ucl ? getJSON("matches/champions-league.json").catch(() => null) : null,
  ]);
  const team = table.teams.find((t) => t.id === club.id);
  const mine = (file, slug) => (file ? file.matches : [])
    .filter((m) => m.home_id === club.id || m.away_id === club.id)
    .map((m) => ({ ...m, comp: slug, isHome: m.home_id === club.id }));
  const league = mine(leagueMatches, club.league);
  const europe = mine(uclMatches, "champions-league");
  const all = [...league, ...europe].sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  profile = new Map(all.map((m) => [`${m.comp}:${m.id}`, m]));
  const uclTeam = ucl ? ucl.teams.find((t) => t.id === club.id) : null;

  // Hero: rating as the lit number, the season in the caption.
  const leaguePlayed = league.filter((m) => m.score);
  const wdl = [0, 0, 0];
  for (const m of leaguePlayed) wdl[sideResult(m)]++;
  $("p-legend").textContent = `${comp.label} · ${table.season} · Strength`;
  $("p-hero").innerHTML = `
    <div class="who">
      <h1>${clubName(club.id, club.name, "hero")}</h1>
      <p class="caption">${ordinal(team.position)} in ${esc(comp.label)} · <b>${team.points}</b> pts from ${team.played} (W${wdl[0]} D${wdl[1]} L${wdl[2]})
        · the big number is its strength, <b>#${club.rating_rank}</b> of ${clubs.clubs.length}: the share of points it would take off an average European top-flight side</p>
    </div>
    <div class="numeral on" role="img" aria-label="${esc(`${club.name}: rating ${dec(club.rating)}`)}">${Math.round(club.rating)}<sup>%</sup></div>`;

  // Outlook tiles.
  const zones = Object.fromEntries(table.zones.map((z) => [z.key, z]));
  const tiles = [
    ["Projected points", Math.round(team.xpts), `80% range ${team.p10}–${team.p90}`],
    ["Title", pct(team.title), "finish first"],
    [`Top ${zones.ucl.to}`, pct(team.ucl), "Champions League places"],
  ];
  if (team.releg >= 1) tiles.push(["Relegation", pct(team.releg), `${ordinal(zones.releg.from)} or lower`]);
  if (uclTeam) tiles.push(["Wins the UCL", pct(uclTeam.title), `Top 8 ${pct(uclTeam.r16)} · final ${pct(uclTeam.stages.final)}`]);
  $("p-tiles").innerHTML = tiles.map(([label, value, sub]) => `<div class="tile"><h2>${label}</h2><b>${value}</b><span>${sub}</span></div>`).join("");

  renderSeason(league, europe, uclTeam);
  renderGoals(league);
  renderNext(all);
  renderStakes(club, team, leagueMatches);
  renderResults(all);
  renderStrength(club);
  $("p-finish").innerHTML = spreadPanel(team, zones.releg.from);
}

/* points, goals and xG from the club's side of a played match */
const sideResult = (m) => { const o = outcome(m.score); return m.isHome ? o : 2 - o; };

function renderSeason(league, europe, uclTeam) {
  const split = (rows) => {
    const s = { p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, xg: 0, xga: 0, xgn: 0, pts: 0 };
    for (const m of rows.filter((r) => r.score)) {
      const [gf, ga] = sidePair(m.score, m.isHome);
      const r = sideResult(m);
      s.p++; s.gf += gf; s.ga += ga; s[["w", "d", "l"][r]]++; s.pts += [3, 1, 0][r];
      if (m.xg) { const [x, xa] = sidePair(m.xg, m.isHome); s.xg += x; s.xga += xa; s.xgn++; }
    }
    return s;
  };
  const line = (label, s) => `<tr><td class="l">${label}</td><td>${s.p}</td><td>${s.w}</td><td>${s.d}</td><td>${s.l}</td>
    <td class="b">${s.gf}</td><td>${s.ga}</td><td>${s.xgn ? dec(s.xg) : "–"}</td><td>${s.xgn ? dec(s.xga) : "–"}</td><td class="b">${s.pts}</td></tr>`;
  const rows = [["Home", split(league.filter((m) => m.isHome))], ["Away", split(league.filter((m) => !m.isHome))], ["League", split(league)]];
  if (europe.some((m) => m.score)) rows.push(["Champions League", split(europe)]);
  const form = [...league, ...europe].filter((m) => m.score).sort((a, b) => b.kickoff.localeCompare(a.kickoff)).slice(0, 6).reverse();
  const lamps = form.map((m) => {
    const r = sideResult(m);
    const [gf, ga] = sidePair(m.score, m.isHome);
    const tip = `${RESULT_WORD[r]} ${gf}–${ga} ${m.isHome ? "v" : "at"} ${clubName(m.isHome ? m.away_id : m.home_id, m.isHome ? m.away : m.home, "inline")} · ${shortDate(m.kickoff)}`;
    return `<span class="form r${r}" data-tip="${esc(tip)}" tabindex="0">${RESULT[r]}</span>`;
  }).join("");
  $("p-season").innerHTML = `<div class="scroll"><table class="board stats"><thead><tr><th class="l"></th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>xG</th><th>xGA</th><th>Pts</th></tr></thead>
    <tbody>${rows.map(([label, s]) => line(label, s)).join("")}</tbody></table></div>
    <p class="formline"><span class="lbl">Form</span>${lamps || "No games yet"}<span class="lbl">oldest → latest</span></p>
    ${uclTeam ? `<p class="note">Champions League league phase: ${ordinal(uclTeam.position)} on ${uclTeam.points} pts after ${uclTeam.played}.</p>` : ""}`;
}

/* goals and xG per league game against what the model expects in the games left */
function renderGoals(league) {
  const per = (rows, f, i, home) => (rows.length ? rows.reduce((t, m) => t + sidePair(m[f], home)[i], 0) / rows.length : null);
  const line = (label, home, i) => {
    const played = league.filter((m) => m.score && m.isHome === home);
    const ahead = league.filter((m) => !m.score && m.exp && m.isHome === home);
    const cells = [per(played, "score", i, home), per(played.filter((m) => m.xg), "xg", i, home), per(ahead, "exp", i, home)];
    return `<tr><td class="l">${label}</td>${cells.map((v, k) => `<td${k === 2 ? ' class="lit"' : ""}>${v == null ? "–" : dec(v, 2)}</td>`).join("")}</tr>`;
  };
  const left = league.filter((m) => !m.score).length;
  $("p-goals").innerHTML = `<div class="scroll"><table class="board stats">
    <thead><tr><th class="l">Per game</th><th>Goals</th><th>xG</th><th>Model, next ${left}</th></tr></thead>
    <tbody>${line("Scored at home", true, 0)}${line("Scored away", false, 0)}${line("Conceded at home", true, 1)}${line("Conceded away", false, 1)}</tbody></table></div>
    <p class="note">League games. xG is Understat's chance quality; the last column is the model's expected goals over the games left.</p>`;
}

function clubRow(m) {
  const opp = m.isHome ? m.away : m.home;
  const p = sideProbs(m, m.isHome);
  const top = Math.max(...(p || [0]));
  const r = m.score ? sideResult(m) : -1;
  const cells = p ? `<span class="m-probs">${p.map((q, i) => `<span class="pc${q === top ? " fav" : ""}${i === r ? " act" : ""}"
      data-tip="${esc(`${RESULT_WORD[i]}: <b>${(q * 100).toFixed(1)}%</b>`)}"><i style="background:${bulb(q, top)}"></i><b>${RESULT[i]}</b>${Math.round(q * 100)}</span>`).join("")}</span>` : "";
  const score = m.score ? (() => { const [gf, ga] = sidePair(m.score, m.isHome); return `<span class="res r${r}">${RESULT[r]}</span> ${gf}–${ga}`; })()
    : (m.p ? (() => { const [f, a] = sidePair(callScore(m), m.isHome); return `<span class="xp">${f}–${a}</span>`; })() : "");
  const v = verdict(m);
  const badge = v ? `<span class="m-verdict ${v.hit ? "hit" : "miss"}">${v.hit ? "Called" : "Missed"}${v.exact ? "<em>Exact</em>" : ""}</span>`
    : `<span class="m-verdict pick">${new Date(m.kickoff) < Date.now() ? "Result pending" : clock(m.kickoff)}</span>`;
  const when = new Date(m.kickoff).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  return `<div class="crow" role="button" tabindex="0" aria-expanded="false" data-key="${m.comp}:${m.id}">
    <span class="c-when">${when}</span><span class="c-comp">${esc(compBySlug[m.comp].short)}</span>
    <span class="c-opp"><small>${m.isHome ? "v" : "at"}</small> ${clubName(m.isHome ? m.away_id : m.home_id, opp)}</span>
    <span class="c-score">${score}</span>${cells}${badge}</div>`;
}

function renderNext(all) {
  const ahead = all.filter((m) => !m.score).slice(0, 6);
  $("p-next").innerHTML = ahead.length
    ? `<div class="clist">${ahead.map(clubRow).join("")}</div><p class="note">W/D/L chances from this club's side; the score is the model's pick, the likeliest score for its likeliest result.</p>`
    : `<p class="note">No fixtures left.</p>`;
}

/* the chance this club cares about most, then the next round's games that move it most (rivals' games included) */
function stakesMetric(team) {
  if (team.title >= 2) return ["title", "title chance"];
  if (team.ucl >= 3 && team.ucl <= 97) return ["ucl", "top-four chance"];
  if (team.releg >= 2) return ["releg", "relegation chance"];
  return null;
}

function renderStakes(club, team, leagueMatches) {
  const metric = stakesMetric(team);
  const range = (values) => Math.max(...values.filter((v) => v != null)) - Math.min(...values.filter((v) => v != null));
  const rows = metric && leagueMatches
    ? leagueMatches.matches
      .map((m) => ({ m, values: ((m.stakes ? m.stakes.teams : []).find((t) => t.id === club.id) || {})[metric[0]] }))
      .filter((x) => x.values && x.values.filter((v) => v != null).length > 1 && range(x.values) >= BIG_STAKE[metric[0]])
      .sort((a, b) => range(b.values) - range(a.values)).slice(0, 5)
    : [];
  $("p-stakes-frame").hidden = !rows.length;
  if (!rows.length) return;
  const line = ({ m, values }) => {
    const labels = [`${m.home} win`, "Draw", `${m.away} win`];
    const lit = m.p.indexOf(Math.max(...m.p));
    const own = m.home_id === club.id || m.away_id === club.id;
    return `<div class="srow${own ? " own" : ""}"><span class="s-fix">${clubName(m.home_id, m.home, "inline")} <small>v</small> ${clubName(m.away_id, m.away, "inline")}
      <small>${shortDate(m.kickoff)}${own ? " · own game" : ""}</small></span>
      <span class="s-res">${values.map((v, i) => `<span${i === lit ? ' class="lit"' : ""}${v == null ? ' title="Too few simulations"' : ""}>${esc(labels[i])} <b>${v == null ? "–" : pct(v)}</b></span>`).join("")}</span></div>`;
  };
  $("p-stakes").innerHTML = `<div class="slist">${rows.map(line).join("")}</div>
    <p class="note">${esc(club.name)}'s ${metric[1]} is <b>${pct(team[metric[0]])}</b> now. Under each result of these games it would be as shown; the likeliest result is lit. Only games where a result moves it by ${BIG_STAKE[metric[0]]} points or more are listed.</p>`;
}

function renderResults(all) {
  const played = all.filter((m) => m.score).reverse();
  const r = record(played);
  const avg = r.n ? pct1(r.given) : "–";
  $("p-results").innerHTML = played.length ? `
    <p class="lead">Called <b>${r.hits} of ${r.n}</b> results · <b>${r.exact}</b> exact score${r.exact === 1 ? "" : "s"} · gave the actual result <b>${avg}</b> on average.</p>
    ${callStrip([...played].reverse())}
    <div class="clist">${played.map(clubRow).join("")}</div>
    <p class="note">Each forecast was made at 00:00 UTC on match day from earlier results only. Tap a game for the scorelines the model expected.</p>`
    : `<p class="note">No games played yet.</p>`;
}

/* one bar per game, oldest first: its height is the chance the model gave what happened, lit green when it was the pick */
function callStrip(games) {
  const rows = games.filter((m) => m.p);
  if (rows.length < 2) return "";
  const bars = rows.map((m) => {
    const v = verdict(m);
    const r = sideResult(m);
    const [gf, ga] = sidePair(m.score, m.isHome);
    const tip = `${RESULT_WORD[r]} ${gf}–${ga} ${m.isHome ? "v" : "at"} ${clubName(m.isHome ? m.away_id : m.home_id, m.isHome ? m.away : m.home, "inline")} · ${shortDate(m.kickoff)}<br>`
      + `${v.hit ? "Called" : "Missed"}: the model gave it <b>${pct1(v.given)}</b>`;
    return `<span class="cs ${v.hit ? "hit" : "miss"}" data-tip="${esc(tip)}" tabindex="0"><i style="height:${Math.round(v.given * 100)}%"></i><b>${RESULT[r]}</b></span>`;
  }).join("");
  return `<div class="callstrip" role="img" aria-label="Chance the model gave each actual result">
    <span class="cs-axis"><em>100%</em><em>50%</em><em>0</em></span><div class="cs-bars">${bars}</div></div>
    <p class="key"><span><i class="k-lamp hit"></i>Called: the result was the model's pick</span><span><i class="k-lamp miss"></i>Missed</span><span>Bar height: chance it gave what happened</span></p>`;
}

function renderStrength(club) {
  const n = clubs.clubs.length;
  const avg = clubs.clubs.reduce((s, c) => s + c.rating, 0) / n;
  const members = clubs.clubs.filter((c) => c.league === club.league).length;
  const meter = (label, value, rank, note) => `<div class="gauge">
      <h3>${label}</h3><b>${dec(value)}</b><span class="rank">${rankTag(rank, "span")} of ${n}</span>
      <span class="meter big"><i style="width:${value}%"></i><em style="left:${avg}%" title="Average club"></em></span>
      <span class="note">${note}</span></div>`;
  $("p-strength").innerHTML = `<div class="gauges">
      ${meter("Overall", club.rating, club.rating_rank, `#${club.league_rank} of ${members} in ${esc(leagueName(club.league))}`)}
      ${meter("Attack", club.attack, club.attack_rank, `Scores ${dec(club.gf, 2)} a game against an average European top-flight side`)}
      ${meter("Defence", club.defense, club.defense_rank, `Concedes ${dec(club.ga, 2)} a game against the same side`)}
    </div>
    <p class="note">Share of points against an average European top-flight side: <b>${dec(club.home)}</b> at home, <b>${dec(club.away)}</b> away. Against an average ${esc(leagueName(club.league))} side it would take ${dec(club.league_rating)}%. The tick on each bar is the ${n}-club average.</p>`;
}

expandable($("p-next"), ".crow", (row) => panelFor(row));
expandable($("p-results"), ".crow", (row) => panelFor(row));
// Links lead to the other club's profile; the open club's own link is dropped.
const panelFor = (row) => {
  const m = profile.get(row.dataset.key);
  const others = new Map(clubs.clubs.filter((c) => c.id !== (m.isHome ? m.home_id : m.away_id)).map((c) => [c.id, c.slug]));
  return matchPanel(m, others, m.comp);
};
