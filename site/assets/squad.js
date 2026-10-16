// Club Squad view: the best EA-rated XI on a pitch, with its text list, and the squad grouped by line.
// Squad files are optional and loaded only when the view opens; a missing file shows one note.
// With `usage`, one competition at a time adds the most-used XI, playing time and the XI game by game.
import { COMPS, compBySlug, $, esc, dec, getJSON, shortDate, clubName } from "./core.js";
import { pitchLines } from "./match.js";

const LINES = [["GK", "Goalkeepers"], ["DEF", "Defenders"], ["MID", "Midfielders"], ["ATT", "Attackers"], ["", "Position not listed"]];
const LINE_OF = {
  GK: "GK", CB: "DEF", LB: "DEF", RB: "DEF", LWB: "DEF", RWB: "DEF",
  CDM: "MID", CM: "MID", CAM: "MID", LM: "MID", RM: "MID",
  LW: "ATT", RW: "ATT", CF: "ATT", ST: "ATT",
};
const PROVIDER_LINE = { Goalkeeper: "GK", Defence: "DEF", Midfield: "MID", Offence: "ATT" };
const STATS = ["pace", "shooting", "passing", "dribbling", "defending", "physical"];
// EA's goalkeeper cards keep diving, handling, kicking, reflexes, speed and positioning in the same six fields.
const FACES = {
  out: [["PAC", "Pace"], ["SHO", "Shooting"], ["PAS", "Passing"], ["DRI", "Dribbling"], ["DEF", "Defending"], ["PHY", "Physical"]],
  GK: [["DIV", "Diving"], ["HAN", "Handling"], ["KIC", "Kicking"], ["REF", "Reflexes"], ["SPD", "Speed"], ["POS", "Positioning"]],
};
// Where each role stands on a 105 × 68 pitch: [distance from own goal, across from the left touchline],
// for a role used once and, where formations do, twice.
const SPOTS = {
  GK: [[[6, 34]]], LB: [[[24, 9]]], RB: [[[24, 59]]], CB: [[[19, 34]], [[19, 25], [19, 43]]],
  CDM: [[[38, 34]], [[38, 25], [38, 43]]], CM: [[[52, 34]], [[54, 18], [54, 50]]], CAM: [[[68, 34]]],
  LM: [[[60, 9]]], RM: [[[60, 59]]], LW: [[[80, 11]]], RW: [[[80, 57]]], ST: [[[90, 34]], [[88, 25], [88, 43]]],
};
const PARTICLES = new Set(["de", "da", "di", "do", "dos", "del", "der", "van", "von", "ter", "ten", "la", "le", "el", "al", "ben", "bin"]);
let token = 0;
let state = null; // the open squad, its chosen competition and XI mode
// "fc27" → "FC 27"
const edition = (e) => String(e).replace(/^fc\s*(\d+)$/i, "FC $1");
const share = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const canUse = (u) => Boolean(u && u.covered > 0 && u.most_used_xi?.slots?.length);

export async function showSquad(club, season) {
  const mine = ++token;
  const box = $("p-squad");
  box.innerHTML = `<fieldset class="frame"><legend>Squad</legend><p class="note sq-wait">Loading the squad…</p></fieldset>`;
  let squad = null;
  let failed = "";
  try {
    squad = await getJSON(`squads/${season}/${club.slug}.json`);
  } catch (err) {
    failed = err.message;
  }
  if (mine !== token) return;
  if (!squad) {
    const missing = !failed || failed === "HTTP 404";
    box.innerHTML = `<fieldset class="frame sq-none"><legend>Squad</legend><p class="note">${missing
      ? "Squad data isn't available for this club yet."
      : `Squad data could not be loaded (${esc(failed)}).`}</p></fieldset>`;
    return;
  }
  if (!squad.players.length) {
    box.innerHTML = `<fieldset class="frame sq-none"><legend>Squad</legend><p class="note">${esc(squad.roster.source)} listed no players for this club on ${esc(shortDate(squad.roster.observed_at))}.</p></fieldset>`;
    return;
  }
  // usage cohorts in display order: the league before the Champions League, never pooled
  const comps = COMPS.map((c) => c.slug).filter((slug) => squad.usage?.[slug]);
  const clubs = comps.length ? await getJSON("clubs.json").catch(() => ({ clubs: [] })) : { clubs: [] };
  if (mine !== token) return;
  state = {
    squad, comps, comp: comps[0] || null, mode: canUse(squad.usage?.[comps[0]]) ? "used" : "ideal",
    byId: new Map(squad.players.map((p) => [p.id, p])), opponents: new Map(clubs.clubs.map((c) => [c.id, c.name])),
  };
  render();
}

function render(focus) {
  const { squad, comp } = state;
  const u = comp ? squad.usage[comp] : null;
  const inXi = new Set(squad.ideal_xi.slots.map((s) => s.player).filter((id) => id != null));
  $("p-squad").innerHTML = xiFrame(u) + squadTable(squad, inXi, u) + (u ? history(u, inXi) : "");
  if (focus) $("p-squad").querySelector(focus)?.focus();
}

document.addEventListener("click", (e) => {
  const chip = e.target.closest("#p-squad [data-sq-comp], #p-squad [data-sq-mode]");
  if (!chip || !state) return;
  if (chip.dataset.sqComp) {
    state.comp = chip.dataset.sqComp;
    if (!canUse(state.squad.usage[state.comp])) state.mode = "ideal";
    render(`[data-sq-comp="${state.comp}"]`);
  } else {
    state.mode = chip.dataset.sqMode;
    render(`[data-sq-mode="${state.mode}"]`);
  }
});

/* "Frenkie de Jong" → "de Jong"; single names stay whole */
function surname(name) {
  const words = String(name).trim().split(/\s+/);
  let i = words.length - 1;
  while (i > 1 && PARTICLES.has(words[i - 1].toLowerCase())) i--;
  return words.slice(i).join(" ");
}
const short = (s, n = 11) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const rated = (p) => p && p.status === "matched" && p.ea;

function place(slots) {
  const count = {};
  for (const s of slots) count[s.role] = (count[s.role] || 0) + 1;
  const seen = {};
  return slots.map((s) => {
    const i = seen[s.role] = (seen[s.role] ?? -1) + 1;
    const line = SPOTS[s.role] || [[[52, 34]]];
    const spots = line[Math.min(count[s.role], line.length) - 1];
    const [along, across] = spots[i] || [spots[0][0], spots[0][1] + 8 * i];
    // drawn upright: own goal at the bottom, left-sided players on the left
    return { ...s, x: across, y: 105 - along };
  });
}

/* competition and Ideal / Most used chips; each competition carries its covered-game count */
function controls(u) {
  const comps = state.comps.map((slug) => {
    const c = state.squad.usage[slug];
    return `<button type="button" class="chip" data-sq-comp="${slug}" aria-pressed="${slug === state.comp}">${esc(compBySlug[slug].label)} <span>${c.covered}/${c.games}<span class="vh"> games covered</span></span></button>`;
  }).join("");
  const modes = [["ideal", "Ideal"], ...(canUse(u) ? [["used", "Most used"]] : [])]
    .map(([key, label]) => `<button type="button" class="chip" data-sq-mode="${key}" aria-pressed="${key === state.mode}">${label}</button>`).join("");
  return `<div class="sq-ctl"><div class="chips" role="group" aria-label="Competition">${comps}</div><div class="chips" role="group" aria-label="XI">${modes}</div></div>`;
}

/* a dot's ring fills clockwise with the player's share of the competition's available minutes */
function ring(x, y, value) {
  const filled = Math.max(0, Math.min(1, value ?? 0)) * 100;
  return `<circle class="sq-track" cx="${x}" cy="${y}" r="3.6"/>${filled ? `<circle class="sq-fill" cx="${x}" cy="${y}" r="3.6" pathLength="100" stroke-dasharray="${dec(filled)} 100" transform="rotate(-90 ${x} ${y})"/>` : ""}`;
}

function xiFrame(u) {
  const { squad, byId } = state;
  const used = state.mode === "used";
  const xi = used ? u.most_used_xi : squad.ideal_xi;
  const compLabel = u ? compBySlug[state.comp].label : "";
  const slots = place(xi.slots);
  const r = squad.ratings;
  // the most-used XI places players by minutes, so a listed player fills a role even without an EA rating
  const filled = (p) => (used ? Boolean(p) : rated(p));
  const ovr = (p) => p.ea?.overall ?? "–";
  const mins = (id) => u?.players?.[id];
  const missingRoles = xi.slots.filter((s) => !filled(byId.get(s.player))).map((s) => s.role);
  const unrated = squad.coverage.players - squad.coverage.matched;
  // two players sharing a surname get their first initial
  const names = slots.map((s) => (filled(byId.get(s.player)) ? surname(byId.get(s.player).name) : ""));
  const label = (s, i) => {
    const full = byId.get(s.player).name;
    const twin = names.filter((n) => n === names[i]).length > 1 && full !== names[i];
    return short(twin ? `${full[0]}. ${names[i]}` : names[i]);
  };
  const dots = slots.map((s, i) => {
    const p = byId.get(s.player);
    if (!filled(p)) {
      return `<g class="sq-dot empty"><circle cx="${s.x}" cy="${s.y}" r="3.6"/><text class="sq-ovr" x="${s.x}" y="${s.y + 1}">–</text>
        <text class="sq-name" x="${s.x}" y="${s.y + 7.6}">${s.role} unfilled</text></g>`;
    }
    const tip = `${s.role} · ${p.name} · EA overall ${ovr(p)}${u ? ` · ${share(mins(p.id)?.share)} of ${compLabel} minutes` : ""}`;
    return `<g class="sq-dot${u ? " used" : ""}"><title>${esc(tip)}</title>${u ? ring(s.x, s.y, mins(p.id)?.share) : `<circle cx="${s.x}" cy="${s.y}" r="3.6"/>`}
      <text class="sq-ovr" x="${s.x}" y="${s.y + 1.05}">${ovr(p)}</text><text class="sq-name" x="${s.x}" y="${s.y + 7.6}">${esc(label(s, i))}</text></g>`;
  }).join("");
  const list = slots.map((s) => {
    const p = byId.get(s.player);
    const minutes = u ? `<span class="sq-share">${filled(p) ? `${share(mins(p.id)?.share)}<span class="vh"> of ${esc(compLabel)} minutes</span>` : ""}</span>` : "";
    return `<li class="${[filled(p) ? "" : "empty", u ? "used" : ""].filter(Boolean).join(" ")}"><span class="sq-role">${s.role}</span>${filled(p)
      ? `<span class="sq-who">${esc(p.name)}</span>${minutes}<b><span class="vh">EA overall </span>${ovr(p)}</b>`
      : `<span class="sq-who">Unfilled: no ${used ? "listed player played" : "rated player listed"} here</span>${minutes}<b aria-hidden="true">–</b>`}</li>`;
  }).join("").replaceAll('<li class="">', "<li>");
  const why = [];
  if (used) {
    if (missingRoles.length) why.push(`No player with ${compLabel} minutes fills ${missingRoles.join(", ")}.`);
    const ratedXi = xi.slots.map((s) => byId.get(s.player)).filter((p) => rated(p) && p.ea.overall != null);
    const mean = ratedXi.length === 11 ? ratedXi.reduce((t, p) => t + p.ea.overall, 0) / 11 : null;
    return `<fieldset class="frame sq-xi"><legend>Most used XI · ${esc(compLabel)}</legend>${controls(u)}
    <p class="mp-key sq-sum"><span>Formation <b>${esc(xi.formation)}</b></span>${mean == null ? "" : `<span>Mean EA overall <b>${dec(mean)}</b></span>`}
      <span>Covered <b>${u.covered}/${u.games}</b> games</span></p>
    <div class="sq-xi-in">
      <div class="mp-pitch sq-pitch"><svg viewBox="-3 -3 74 111" role="img" aria-label="${esc(`${squad.name}'s most used ${compLabel} XI in a ${xi.formation}, attacking upwards; each ring fills with the player's share of minutes. The same eleven are listed with their roles.`)}">
        <g class="pitch" transform="matrix(0 -1 1 0 0 105)">${pitchLines(68)}</g>${dots}</svg></div>
      <ol class="sq-list" aria-label="Most used XI, goalkeeper to attack">${list}</ol>
    </div>
    <p class="note">Most used XI: the ${esc(xi.formation)} roles filled by the players with the most ${esc(compLabel)} minutes this season, ties going to EA overall, from the ${u.covered} of ${u.games} games with a complete match sheet. Each ring fills with the player's share of available minutes (minutes ÷ 90 per covered game). ${why.join(" ")}
      ${minutesSource(state.comp)} The number in each dot is EA overall (${esc(edition(r.edition))}), not Floodlight's club strength.</p>
  </fieldset>`;
  }
  const status = xi.status === "complete" ? ""
    : `<span class="sq-plate">${xi.status === "provisional" ? "Provisional" : "Too few rated players"}</span>`;
  if (xi.status === "provisional" && unrated > 0) {
    why.push(`Provisional: ${unrated} squad ${unrated === 1 ? "player has" : "players have"} no EA rating, so a stronger XI could exist.`);
  } else if (xi.status === "provisional") {
    why.push("Provisional: the squad's ratings don't settle every role.");
  } else if (xi.status === "insufficient_coverage") {
    why.push("Too few squad players are rated to pick a full XI.");
  }
  if (missingRoles.length) why.push(`No rated player fills ${missingRoles.join(", ")}.`);
  if (u) why.push(`Each ring fills with the player's share of ${compLabel} minutes.`);
  return `<fieldset class="frame sq-xi"><legend>Ideal XI · EA ratings</legend>${u ? controls(u) : ""}
    <p class="mp-key sq-sum"><span>Formation <b>${esc(xi.formation)}</b></span>${xi.mean_overall == null ? "" : `<span>Mean EA overall <b>${dec(xi.mean_overall)}</b></span>`}
      <span>Rated <b>${squad.coverage.matched}/${squad.coverage.players}</b> of the squad</span>${u ? `<span>Covered <b>${u.covered}/${u.games}</b> games</span>` : ""}${status}</p>
    <div class="sq-xi-in">
      <div class="mp-pitch sq-pitch"><svg viewBox="-3 -3 74 111" role="img" aria-label="${esc(`${squad.name}'s best EA-rated XI in a ${xi.formation}, attacking upwards.${u ? ` Each ring fills with the player's share of ${compLabel} minutes.` : ""} The same eleven are listed with their roles.`)}">
        <g class="pitch" transform="matrix(0 -1 1 0 0 105)">${pitchLines(68)}</g>${dots}</svg></div>
      <ol class="sq-list" aria-label="Ideal XI, goalkeeper to attack">${list}</ol>
    </div>
    <p class="note">Best EA-rated XI from listed positions, everyone available: each role takes the highest EA overall among players EA lists there (LW/LM and RW/RM share wide roles). ${why.join(" ")}
      Ratings: ${esc(r.source)}, ${esc(edition(r.edition))}, snapshot ${esc(longDate(r.snapshot_date))}. EA overall is EA's player rating, not Floodlight's club strength, and a rating gap is not goals or a win chance.</p>
  </fieldset>`;
}

const minutesSource = (slug) => (slug === "champions-league"
  ? "Champions League minutes are UEFA's and include stoppage time, so a share can pass 100%."
  : "League minutes are Understat's, without stoppage time.");

const longDate = (iso) => new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

function ageOn(dob, when) {
  if (!dob) return null;
  const [y, m, d] = dob.split("-").map(Number);
  const at = new Date(when);
  return at.getUTCFullYear() - y - (at.getUTCMonth() + 1 < m || (at.getUTCMonth() + 1 === m && at.getUTCDate() < d) ? 1 : 0);
}

function lineOf(p) {
  if (rated(p) && p.ea.positions?.length) return LINE_OF[p.ea.positions[0]] || "";
  return PROVIDER_LINE[p.provider_position] || "";
}

/* playing-time columns for one competition; xG and xA per 90 only for league games (Understat) */
function usageCols(u) {
  if (!u) return [];
  const cols = [["ST", "Starts"], ["SUB", "Substitute appearances"], ["MIN", "Minutes"], ["MIN%", "Share of available minutes"]];
  return state.comp === "champions-league" ? cols : [...cols, ["xG90", "Shot xG per 90 minutes"], ["xA90", "Expected assists per 90 minutes"]];
}
const PER90_MIN = 90;

function usageCells(u, p) {
  const n = usageCols(u).length;
  const m = u?.players?.[p.id];
  if (!n) return "";
  // no entry: participation unknown, never zero
  if (!m) return "<td>–</td>".repeat(n);
  const per90 = (v) => (v == null || m.minutes < PER90_MIN ? "–" : dec(v / m.minutes * 90, 2));
  const cells = [m.starts, m.sub, m.minutes, share(m.share)];
  if (n > 4) cells.push(per90(m.xg), per90(m.xa));
  return cells.map((v, i) => `<td${i === 0 ? ' class="sq-u0"' : ""}>${v ?? "–"}</td>`).join("");
}

function squadTable(squad, inXi, u) {
  const observed = squad.roster.observed_at;
  const groups = LINES.map(([key, label]) => [key, label, squad.players.filter((p) => lineOf(p) === key)
    .sort((a, b) => (rated(b) ? b.ea.overall : -1) - (rated(a) ? a.ea.overall : -1) || a.name.localeCompare(b.name))])
    .filter(([, , rows]) => rows.length);
  const extra = usageCols(u);
  const cols = `<colgroup><col class="sq-c-name"><col class="sq-c-ovr"><col class="sq-c-age"><col class="sq-c-pos">${extra.map(([a]) => `<col class="sq-c-u${a === "MIN" || a === "MIN%" ? " w" : ""}">`).join("")}${STATS.map(() => "<col>").join("")}</colgroup>`;
  const tables = groups.map(([key, label, rows]) => {
    const faces = FACES[key === "GK" ? "GK" : "out"];
    const body = rows.map((p) => {
      const age = ageOn(p.dob, observed);
      const xi = inXi.has(p.id) ? `<span class="sq-mark" title="In the ideal XI" aria-hidden="true">XI</span><span class="vh">Ideal XI: </span>` : '<span class="sq-mark none" aria-hidden="true"></span>';
      const head = `<th scope="row" class="l sq-player" title="${esc(p.name)}">${xi}<span class="sq-nm">${esc(p.name)}</span></th>`;
      if (!rated(p)) {
        return `<tr class="unrated">${head}<td>–</td><td>${age ?? "–"}</td><td class="l">–</td>${usageCells(u, p)}<td class="l sq-nr" colspan="6">not rated${p.status === "ambiguous" ? " · EA match unclear" : ""}</td></tr>`;
      }
      const stats = STATS.map((k) => {
        const v = p.ea[k];
        return `<td${v == null ? "" : v >= 80 ? ' class="b"' : v < 60 ? ' class="off"' : ""}>${v ?? "–"}</td>`;
      }).join("");
      return `<tr>${head}<td class="sq-ovr-c">${p.ea.overall}</td><td>${age ?? "–"}</td><td class="l sq-pos" title="${esc(p.ea.positions.join(" "))}">${esc(p.ea.positions.join(" "))}</td>${usageCells(u, p)}${stats}</tr>`;
    }).join("");
    return `<h3 class="dgroup">${label} <span>${rows.length}</span></h3>
      <table class="board sq-table${u ? " used" : ""}">${cols}<thead><tr><th scope="col" class="l sq-player">Player</th><th scope="col"><abbr title="EA overall">OVR</abbr></th>
        <th scope="col">Age</th><th scope="col" class="l">EA pos</th>${extra.map(([a, t], i) => `<th scope="col"${i === 0 ? ' class="sq-u0"' : ""}><abbr title="${t}">${a}</abbr></th>`).join("")}${faces.map(([a, t]) => `<th scope="col"><abbr title="${t}">${a}</abbr></th>`).join("")}</tr></thead>
        <tbody>${body}</tbody></table>`;
  }).join("");
  const unrated = squad.coverage.players - squad.coverage.matched;
  const playing = u ? `<p class="note">ST, SUB and MIN count starts, substitute appearances and minutes in the ${u.covered} of ${u.games} ${esc(compBySlug[state.comp].label)} games with a complete match sheet; MIN% is minutes ÷ (90 × ${u.covered}). A dash means participation is unknown, not zero. ${minutesSource(state.comp)}
      ${extra.length > 4 ? `xG90 and xA90 are Understat shot xG and expected assists per 90 minutes, from ${PER90_MIN} minutes up; ` : "UEFA match sheets carry no xG, so xG and xA per 90 are shown for league games only; "}league and Champions League minutes are never added together.</p>` : "";
  return `<fieldset class="frame sq-squad"><legend>Squad · EA ratings${u ? ` and ${esc(compBySlug[state.comp].label)} minutes` : ""}</legend>
    <div class="scroll sq-scroll">${tables}</div>
    <p class="note">${squad.coverage.players} players as listed by ${esc(squad.roster.source)} on ${esc(shortDate(observed))}, grouped by EA's first listed position and sorted by EA overall; ages on that date.
      ${unrated ? `${unrated} not rated: no confident EA match by name and birth date. ` : ""}OVR and the six face stats are ${esc(squad.ratings.source)} ratings (${esc(edition(squad.ratings.edition))}); goalkeepers' six are EA's keeper stats. 80 and above are bold, below 60 dim.</p>${playing}
  </fieldset>`;
}

/* one row per game, newest first: who started, how many of the ideal XI, and changes since the last complete sheet */
function history(u, inXi) {
  const { byId, opponents } = state;
  const compLabel = compBySlug[state.comp].label;
  const games = [...(u.games_list || [])].sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  let previous = null;
  const rows = games.map((g) => {
    const starters = g.starters || [];
    let rotation = "–";
    if (starters.length === 11) {
      if (previous) {
        const changes = starters.filter((id) => !previous.includes(id)).length;
        rotation = changes ? `${changes} change${changes === 1 ? "" : "s"}` : "Unchanged";
      }
      previous = starters;
    } else if (g.status === "partial") {
      rotation = "Starters not all identified";
    }
    const who = opponents.get(g.opponent_id);
    const opp = who ? clubName(g.opponent_id, who, "inline") : "Unknown opponent";
    const heat = state.comp === "champions-league" && g.status !== "missing";
    const link = `<a class="sq-go" href="#match/${state.comp}/${g.fixture_id}" aria-label="${esc(`Match page${heat ? " and heatmap" : ""}${who ? ` against ${who}` : ""}`)}">${heat ? "Heatmap " : ""}→</a>`;
    const date = `<td class="l sq-h-date">${esc(shortDate(g.kickoff))}</td><td class="l sq-h-opp">${opp}</td>`;
    if (g.status === "missing") {
      return `<tr class="missing">${date}<td class="l sq-nr" colspan="3">No match sheet for this game</td><td class="sq-h-go">${link}</td></tr>`;
    }
    const known = starters.map((id) => byId.get(id));
    const order = (p) => LINES.findIndex(([key]) => key === (p ? lineOf(p) : ""));
    const strip = known.map((p, i) => ({ p, id: starters[i] })).sort((a, b) => order(a.p) - order(b.p))
      .map(({ p, id }) => `<i class="${p ? (inXi.has(id) ? "on" : "") : "unk"}" title="${esc(p ? p.name : "Not in the current squad")}"></i>`).join("")
      + '<i class="unk"></i>'.repeat(Math.max(0, 11 - starters.length));
    const spoken = `Starters: ${known.map((p) => (p ? p.name : "a player not in the current squad")).join(", ")}${starters.length < 11 ? `; ${11 - starters.length} not identified` : ""}.`;
    return `<tr>${date}<td class="l"><span class="sq-strip" aria-hidden="true">${strip}</span><span class="vh">${esc(spoken)}</span></td>
      <td>${g.ideal_started ?? "–"}/11</td><td class="sq-h-rot">${rotation}</td><td class="sq-h-go">${link}</td></tr>`;
  }).reverse().join("");
  return `<fieldset class="frame sq-hist"><legend>XI history · ${esc(compLabel)}</legend>
    <div class="scroll"><table class="board sq-htable"><thead><tr><th scope="col" class="l">Date</th><th scope="col" class="l">Opponent</th><th scope="col" class="l">Starters</th>
      <th scope="col"><abbr title="Ideal-XI players starting">Ideal</abbr></th><th scope="col">Rotation</th><th scope="col"><span class="vh">Match page</span></th></tr></thead>
      <tbody>${rows || `<tr><td class="l sq-nr" colspan="6">No ${esc(compLabel)} games played yet.</td></tr>`}</tbody></table></div>
    <p class="note">${esc(compLabel)} games this season, newest first. Bulbs are the starters, goalkeeper to attack; lit ones are in the ideal XI, and dashed ones are starters not in the current squad or not identified. Ideal counts ideal-XI players starting; rotation counts starters changed since the previous game whose eleven starters are all identified.${state.comp === "champions-league" ? " Heatmap links open the match page's activity map." : ""}</p>
  </fieldset>`;
}
