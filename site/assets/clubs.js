// Clubs view: a strength ranking for the five leagues and a profile for every club.
import {
  LEAGUES, compBySlug, $, esc, getJSON, setStatus, ordinal, pct, pct1, dec, verdict, sideProbs, sidePair,
  outcome, expandable, bulb, shortDate, clock,
} from "./core.js";
import { matchPanel, record } from "./matches.js";
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
const leagueTables = () => Promise.all(LEAGUES.map((l) => getJSON(`${l.slug}.json`).catch(() => null)));
const rowFor = (tables, club) => {
  const table = tables.find((t) => t && t.slug === club.league);
  return table ? table.teams.find((t) => t.id === club.id) : null;
};

/* ---------- index ---------- */
async function showIndex() {
  document.title = "Clubs · Final Table";
  const tables = await leagueTables();
  const list = clubs.clubs;
  const [best] = list;
  const topAttack = list.find((c) => c.attack_rank === 1);
  const topDefense = list.find((c) => c.defense_rank === 1);
  $("c-legend").textContent = `Club strength · ${clubs.season}`;
  $("c-hero").innerHTML = `
    <div class="who">
      <h1><a href="#clubs/${best.slug}">${esc(best.name)}</a></h1>
      <p class="caption">The strongest club in Europe's top five leagues: it would take <b>${Math.round(best.rating)}%</b> of the points off an average side ·
        best attack <b>${esc(topAttack.name)} ${dec(topAttack.attack)}</b> · best defence <b>${esc(topDefense.name)} ${dec(topDefense.defense)}</b> · ${list.length} clubs rated</p>
    </div>
    <div class="numeral on" role="img" aria-label="${esc(`${best.name}: rating ${dec(best.rating)}`)}">${Math.round(best.rating)}<sup>%</sup></div>`;

  $("c-board").innerHTML = clubs.featured.map((id) => {
    const c = list.find((x) => x.id === id);
    const row = rowFor(tables, c);
    const place = row ? `${ordinal(row.position)} in ${leagueName(c.league)}` : leagueName(c.league);
    return `<a class="cell" href="#clubs/${c.slug}">
      <span class="nm">${esc(c.name)}</span>
      <span class="lg">${esc(place)}</span>
      <span class="rt">${dec(c.rating)}</span>
      <span class="rk">#${c.rating_rank}</span>
      <span class="ad"><span>Att</span><i style="--w:${c.attack}%"></i><b>${dec(c.attack)}</b></span>
      <span class="ad def"><span>Def</span><i style="--w:${c.defense}%"></i><b>${dec(c.defense)}</b></span>
    </a>`;
  }).join("");

  renderRanking(tables);
  renderScatter();
  $("c-factors").innerHTML = LEAGUES.map((l) => `${esc(l.label)} <b>${clubs.league_factors[l.slug].toFixed(2)}</b>`).join(" · ");
}

function renderRanking(tables) {
  const chips = [{ slug: "all", label: "All leagues" }, ...LEAGUES];
  $("c-chips").innerHTML = chips.map((l) => `<button type="button" class="chip" data-league="${l.slug}" aria-pressed="${leagueFilter === l.slug}">${esc(l.label)}</button>`).join("");
  const shown = clubs.clubs.filter((c) => leagueFilter === "all" || c.league === leagueFilter)
    .sort((a, b) => b[sortKey] - a[sortKey] || a.rating_rank - b.rating_rank);
  const limit = showAll || leagueFilter !== "all" ? shown.length : 25;
  const sortable = (key, label) => `<th aria-sort="${sortKey === key ? "descending" : "none"}"><button type="button" data-sort="${key}">${label}${sortKey === key ? " ▾" : ""}</button></th>`;
  $("c-rank").innerHTML = `<thead><tr><th class="rk l">#</th><th class="club l">Club</th><th class="l">League</th>
      ${sortable("rating", "Rating")}${sortable("attack", "Attack")}${sortable("defense", "Defence")}
      <th>Scores</th><th>Concedes</th><th>Now</th></tr></thead>
    <tbody>${shown.slice(0, limit).map((c, i) => {
      const row = rowFor(tables, c);
      return `<tr class="${clubs.featured.includes(c.id) ? "featured" : ""}">
        <td class="rk l">${String(i + 1).padStart(2, "0")}</td>
        <td class="club l"><a href="#clubs/${c.slug}">${esc(c.name)}</a></td>
        <td class="l lg">${esc(compBySlug[c.league].short)}</td>
        <td class="b">${dec(c.rating)}</td>
        <td>${dec(c.attack)} <small>#${c.attack_rank}</small></td>
        <td>${dec(c.defense)} <small>#${c.defense_rank}</small></td>
        <td>${dec(c.gf, 2)}</td><td>${dec(c.ga, 2)}</td>
        <td>${row ? ordinal(row.position) : "–"}</td></tr>`;
    }).join("")}</tbody>`;
  $("c-more").hidden = limit >= shown.length;
  $("c-more").textContent = `Show all ${shown.length} clubs`;
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
    const tip = `<b>${esc(c.name)}</b> · ${esc(leagueName(c.league))}<br>Attack <b>${dec(c.attack)}</b> · Defence <b>${dec(c.defense)}</b> · Rating <b>${dec(c.rating)}</b>`;
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
  document.title = `${club.name} · Final Table`;
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
  const played = all.filter((m) => m.score);

  // Hero: rating as the lit number, the season in the caption.
  const leaguePlayed = league.filter((m) => m.score);
  const wdl = [0, 0, 0];
  for (const m of leaguePlayed) wdl[sideResult(m)]++;
  $("p-legend").textContent = `${comp.label} · ${table.season} · Strength`;
  $("p-hero").innerHTML = `
    <div class="who">
      <h1>${esc(club.name)}</h1>
      <p class="caption">${ordinal(team.position)} in ${esc(comp.label)} after ${team.played} · <b>${team.points}</b> pts (W${wdl[0]} D${wdl[1]} L${wdl[2]})
        · projected <b>${Math.round(team.xpts)}</b> pts · <b>#${club.rating_rank}</b> of ${clubs.clubs.length} clubs by strength</p>
    </div>
    <div class="numeral on" role="img" aria-label="${esc(`${club.name}: rating ${dec(club.rating)}`)}">${Math.round(club.rating)}<sup>%</sup></div>`;

  // Outlook tiles.
  const zones = Object.fromEntries(table.zones.map((z) => [z.key, z]));
  const mode = team.probs.indexOf(Math.max(...team.probs)) + 1;
  const calls = played.map(verdict).filter(Boolean);
  const tiles = [
    ["Projected points", Math.round(team.xpts), `80% range ${team.p10}–${team.p90}`],
    ["Likeliest finish", ordinal(mode), `${pct(team.probs[mode - 1])} chance`],
    ["Title", pct(team.title), "finish first"],
    [`Top ${zones.ucl.to}`, pct(team.ucl), "Champions League places"],
  ];
  if (team.releg >= 1) tiles.push(["Relegation", pct(team.releg), `${ordinal(zones.releg.from)} or lower`]);
  if (uclTeam) tiles.push(["Wins the UCL", pct(uclTeam.title), `Top 8 ${pct(uclTeam.r16)} · final ${pct(uclTeam.stages.final)}`]);
  tiles.push(["Model on their games", calls.length ? `${calls.filter((v) => v.hit).length}/${calls.length}` : "–", calls.length ? "results called" : "no games yet"]);
  $("p-tiles").innerHTML = tiles.map(([label, value, sub]) => `<div class="tile"><h2>${label}</h2><b>${value}</b><span>${sub}</span></div>`).join("");

  renderSeason(league, europe, uclTeam);
  renderGoals(club, league);
  renderNext(all);
  renderResults(club, all, league);
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
    const tip = `${RESULT_WORD[r]} ${gf}–${ga} ${m.isHome ? "v" : "at"} <b>${esc(m.isHome ? m.away : m.home)}</b> · ${shortDate(m.kickoff)}`;
    return `<span class="form r${r}" data-tip="${esc(tip)}" tabindex="0">${RESULT[r]}</span>`;
  }).join("");
  $("p-season").innerHTML = `<div class="scroll"><table class="board stats"><thead><tr><th class="l"></th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>xG</th><th>xGA</th><th>Pts</th></tr></thead>
    <tbody>${rows.map(([label, s]) => line(label, s)).join("")}</tbody></table></div>
    <p class="formline"><span class="lbl">Form</span>${lamps || "No games yet"}<span class="lbl">oldest → latest</span></p>
    ${uclTeam ? `<p class="note">Champions League league phase: ${ordinal(uclTeam.position)} on ${uclTeam.points} pts after ${uclTeam.played}.</p>` : ""}`;
}

/* actual goals and xG per game against what the model expects in the rest of the season, home and away */
function renderGoals(club, league) {
  const per = (rows, pick) => (rows.length ? rows.reduce((s, m) => s + pick(m), 0) / rows.length : null);
  const block = (home) => {
    const played = league.filter((m) => m.score && m.isHome === home);
    const withXg = played.filter((m) => m.xg);
    const ahead = league.filter((m) => !m.score && m.exp && m.isHome === home);
    const v = (rows, field, i) => per(rows, (m) => sidePair(m[field], home)[i]);
    return {
      gf: v(played, "score", 0), ga: v(played, "score", 1),
      xg: v(withXg, "xg", 0), xga: v(withXg, "xg", 1),
      pre: v(played.filter((m) => m.exp), "exp", 0), prea: v(played.filter((m) => m.exp), "exp", 1),
      next: v(ahead, "exp", 0), nexta: v(ahead, "exp", 1), games: ahead.length,
    };
  };
  const h = block(true), a = block(false);
  const cell = (val) => `<td>${val == null ? "–" : dec(val, 2)}</td>`;
  const row = (label, s, k) => `<tr><td class="l">${label}</td>${cell(s[k[0]])}${cell(s[k[1]])}${cell(s[k[2]])}<td class="lit">${s[k[3]] == null ? "–" : dec(s[k[3]], 2)}</td></tr>`;
  const head = `<thead><tr><th class="l"></th><th>Goals</th><th>xG</th><th>Model pre-match</th><th>Model, rest of season</th></tr></thead>`;
  $("p-goals").innerHTML = `
    <h3 class="sub">Scored per game</h3>
    <div class="scroll"><table class="board stats">${head}<tbody>${row("Home", h, ["gf", "xg", "pre", "next"])}${row("Away", a, ["gf", "xg", "pre", "next"])}</tbody></table></div>
    <h3 class="sub">Conceded per game</h3>
    <div class="scroll"><table class="board stats">${head}<tbody>${row("Home", h, ["ga", "xga", "prea", "nexta"])}${row("Away", a, ["ga", "xga", "prea", "nexta"])}</tbody></table></div>
    <p class="note">League games. xG is Understat's chance quality; the model's expected goals blend team strengths from goals and xG. The last column averages its expectation over the ${h.games} home and ${a.games} away league games left.</p>`;
}

function clubRow(m) {
  const opp = m.isHome ? m.away : m.home;
  const p = sideProbs(m, m.isHome);
  const top = Math.max(...(p || [0]));
  const r = m.score ? sideResult(m) : -1;
  const cells = p ? `<span class="m-probs">${p.map((q, i) => `<span class="pc${q === top ? " fav" : ""}${i === r ? " act" : ""}"
      data-tip="${esc(`${RESULT_WORD[i]}: <b>${(q * 100).toFixed(1)}%</b>`)}"><i style="background:${bulb(q, top)}"></i><b>${RESULT[i]}</b>${Math.round(q * 100)}</span>`).join("")}</span>` : "";
  const score = m.score ? (() => { const [gf, ga] = sidePair(m.score, m.isHome); return `<span class="res r${r}">${RESULT[r]}</span> ${gf}–${ga}`; })()
    : (m.exp ? (() => { const [f, a] = sidePair(m.exp, m.isHome); return `<span class="xp">${dec(f)}–${dec(a)}</span>`; })() : "");
  const v = verdict(m);
  const badge = v ? `<span class="m-verdict ${v.hit ? "hit" : "miss"}">${v.hit ? "Called" : "Missed"}${v.exact ? "<em>Exact</em>" : ""}</span>`
    : `<span class="m-verdict pick">${new Date(m.kickoff) < Date.now() ? "Result pending" : clock(m.kickoff)}</span>`;
  const when = new Date(m.kickoff).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
  return `<div class="crow" role="button" tabindex="0" aria-expanded="false" data-key="${m.comp}:${m.id}">
    <span class="c-when">${when}</span><span class="c-comp">${esc(compBySlug[m.comp].short)}</span>
    <span class="c-opp"><small>${m.isHome ? "v" : "at"}</small> ${esc(opp)}</span>
    <span class="c-score">${score}</span>${cells}${badge}</div>`;
}

function renderNext(all) {
  const ahead = all.filter((m) => !m.score).slice(0, 6);
  $("p-next").innerHTML = ahead.length
    ? `<div class="clist">${ahead.map(clubRow).join("")}</div><p class="note">W/D/L chances from this club's side; the score column is the model's expected goals.</p>`
    : `<p class="note">No fixtures left.</p>`;
}

function renderResults(club, all, league) {
  const played = all.filter((m) => m.score).reverse();
  const r = record(played);
  const avg = r.n ? pct1(r.given) : "–";
  $("p-results").innerHTML = played.length ? `
    <p class="lead">Called <b>${r.hits} of ${r.n}</b> results · <b>${r.exact}</b> exact score${r.exact === 1 ? "" : "s"} · gave the actual result <b>${avg}</b> on average.</p>
    ${pointsChart(club, league)}
    <div class="clist">${played.map(clubRow).join("")}</div>
    <p class="note">Each forecast was made at 00:00 UTC on match day from earlier results only. Tap a game for the scorelines the model expected.</p>`
    : `<p class="note">No games played yet.</p>`;
}

/* league points against the points the pre-match forecasts expected, game by game */
function pointsChart(club, league) {
  const games = league.filter((m) => m.score && m.p);
  if (games.length < 2) return "";
  let pts = 0, xpts = 0;
  const series = games.map((m) => {
    const [w, d] = sideProbs(m, m.isHome);
    pts += [3, 1, 0][sideResult(m)];
    xpts += 3 * w + d;
    return { m, pts, xpts };
  });
  const W = Math.round(Math.min(780, Math.max(300, $("p-results").clientWidth || 640)));
  const H = W < 500 ? 200 : 220, pad = { l: 30, r: 78, t: 14, b: 30 };
  const top = Math.max(3, Math.ceil(Math.max(pts, xpts) / 5) * 5);
  const x = (i) => pad.l + (i / (series.length - 1)) * (W - pad.l - pad.r);
  const y = (v) => H - pad.b - (v / top) * (H - pad.t - pad.b);
  const path = (k) => series.map((s, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(s[k]).toFixed(1)}`).join("");
  const grid = [];
  for (let v = 0; v <= top; v += top > 30 ? 10 : 5) grid.push(`<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="tick" x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text>`);
  const band = (W - pad.l - pad.r) / Math.max(1, series.length - 1);
  const hits = series.map((s, i) => {
    const opp = s.m.isHome ? s.m.away : s.m.home;
    const [gf, ga] = sidePair(s.m.score, s.m.isHome);
    const tip = `Game ${i + 1}: ${gf}–${ga} ${s.m.isHome ? "v" : "at"} <b>${esc(opp)}</b><br>Points <b>${s.pts}</b> · expected <b>${s.xpts.toFixed(1)}</b>`;
    return `<rect class="band" x="${x(i) - band / 2}" y="${pad.t}" width="${band}" height="${H - pad.t - pad.b}" data-tip="${esc(tip)}"/>`;
  }).join("");
  const last = series[series.length - 1];
  const diff = last.pts - last.xpts;
  const end = (v, cls, text) => `<text class="end ${cls}" x="${x(series.length - 1) + 8}" y="${y(v) + 4}">${text}</text>`;
  const apart = Math.abs(y(last.pts) - y(last.xpts)) < 14;
  return `<div class="chart">
    <p class="key"><span><i class="k-line"></i>Points won</span><span><i class="k-line exp"></i>Points the forecasts expected</span>
      <span>${diff >= 0 ? "+" : ""}${diff.toFixed(1)} against expectation</span></p>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${club.name} won ${last.pts} league points; pre-match forecasts expected ${last.xpts.toFixed(1)}`)}">
      ${grid.join("")}
      <path class="line exp" d="${path("xpts")}"/><path class="line" d="${path("pts")}"/>
      ${series.map((s, i) => `<circle class="pt" cx="${x(i)}" cy="${y(s.pts)}" r="3.5"/>`).join("")}
      ${end(last.pts, "", `${last.pts} won`)}${end(apart ? last.xpts + (last.xpts > last.pts ? 1 : -1) * top * 0.08 : last.xpts, "exp", `${last.xpts.toFixed(1)} exp.`)}
      <text class="tick" x="${pad.l}" y="${H - 8}">Game 1</text><text class="tick" x="${x(series.length - 1)}" y="${H - 8}" text-anchor="end">Game ${series.length}</text>
      ${hits}
    </svg></div>`;
}

function renderStrength(club) {
  const n = clubs.clubs.length;
  const avg = clubs.clubs.reduce((s, c) => s + c.rating, 0) / n;
  const members = clubs.clubs.filter((c) => c.league === club.league).length;
  const meter = (label, value, rank, note) => `<div class="gauge">
      <h3>${label}</h3><b>${dec(value)}</b><span class="rank">#${rank} of ${n}</span>
      <span class="meter big"><i style="width:${value}%"></i><em style="left:${avg}%" title="Average club"></em></span>
      <span class="note">${note}</span></div>`;
  $("p-strength").innerHTML = `<div class="gauges">
      ${meter("Overall", club.rating, club.rating_rank, `#${club.league_rank} of ${members} in ${esc(leagueName(club.league))}`)}
      ${meter("Attack", club.attack, club.attack_rank, `Scores ${dec(club.gf, 2)} a game against an average ${esc(leagueName(club.league))} side`)}
      ${meter("Defence", club.defense, club.defense_rank, `Concedes ${dec(club.ga, 2)} a game against the same side`)}
    </div>
    <p class="note">Share of points against an average side on a neutral pitch: <b>${dec(club.home)}</b> at home, <b>${dec(club.away)}</b> away. Within ${esc(leagueName(club.league))} the club rates ${dec(club.league_rating)}; the league factor ${clubs.league_factors[club.league].toFixed(2)} puts it on the five-league scale. The tick on each bar is the ${n}-club average.</p>`;
}

expandable($("p-next"), ".crow", (row) => panelFor(row));
expandable($("p-results"), ".crow", (row) => panelFor(row));
// Links lead to the other club's profile; the open club's own link is dropped.
const panelFor = (row) => {
  const m = profile.get(row.dataset.key);
  const others = new Map(clubs.clubs.filter((c) => c.id !== (m.isHome ? m.home_id : m.away_id)).map((c) => [c.id, c.slug]));
  return matchPanel(m, others);
};
