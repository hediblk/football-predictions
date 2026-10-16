// Club Squad view: the best EA-rated XI on a pitch, with its text list, and the squad grouped by line.
// Squad files are optional and loaded only when the view opens; a missing file shows one note.
import { $, esc, dec, getJSON, shortDate } from "./core.js";
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
  const byId = new Map(squad.players.map((p) => [p.id, p]));
  const inXi = new Set(squad.ideal_xi.slots.map((s) => s.player).filter((id) => id != null));
  box.innerHTML = idealXi(squad, byId) + squadTable(squad, inXi);
}

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

function idealXi(squad, byId) {
  const xi = squad.ideal_xi;
  const slots = place(xi.slots);
  const r = squad.ratings;
  const missingRoles = xi.slots.filter((s) => !rated(byId.get(s.player))).map((s) => s.role);
  const unrated = squad.coverage.players - squad.coverage.matched;
  // two players sharing a surname get their first initial
  const names = slots.map((s) => (rated(byId.get(s.player)) ? surname(byId.get(s.player).name) : ""));
  const label = (s, i) => {
    const full = byId.get(s.player).name;
    const twin = names.filter((n) => n === names[i]).length > 1 && full !== names[i];
    return short(twin ? `${full[0]}. ${names[i]}` : names[i]);
  };
  const dots = slots.map((s, i) => {
    const p = byId.get(s.player);
    if (!rated(p)) {
      return `<g class="sq-dot empty"><circle cx="${s.x}" cy="${s.y}" r="3.6"/><text class="sq-ovr" x="${s.x}" y="${s.y + 1}">–</text>
        <text class="sq-name" x="${s.x}" y="${s.y + 7.6}">${s.role} unfilled</text></g>`;
    }
    return `<g class="sq-dot"><title>${esc(`${s.role} · ${p.name} · EA overall ${p.ea.overall}`)}</title><circle cx="${s.x}" cy="${s.y}" r="3.6"/>
      <text class="sq-ovr" x="${s.x}" y="${s.y + 1.05}">${p.ea.overall}</text><text class="sq-name" x="${s.x}" y="${s.y + 7.6}">${esc(label(s, i))}</text></g>`;
  }).join("");
  const list = slots.map((s) => {
    const p = byId.get(s.player);
    return `<li${rated(p) ? "" : ' class="empty"'}><span class="sq-role">${s.role}</span>${rated(p)
      ? `<span class="sq-who">${esc(p.name)}</span><b><span class="vh">EA overall </span>${p.ea.overall}</b>`
      : `<span class="sq-who">Unfilled: no rated player listed here</span><b aria-hidden="true">–</b>`}</li>`;
  }).join("");
  const status = xi.status === "complete" ? ""
    : `<span class="sq-plate">${xi.status === "provisional" ? "Provisional" : "Too few rated players"}</span>`;
  const why = [];
  if (xi.status === "provisional" && unrated > 0) {
    why.push(`Provisional: ${unrated} squad ${unrated === 1 ? "player has" : "players have"} no EA rating, so a stronger XI could exist.`);
  } else if (xi.status === "provisional") {
    why.push("Provisional: the squad's ratings don't settle every role.");
  } else if (xi.status === "insufficient_coverage") {
    why.push("Too few squad players are rated to pick a full XI.");
  }
  if (missingRoles.length) why.push(`No rated player fills ${missingRoles.join(", ")}.`);
  return `<fieldset class="frame sq-xi"><legend>Ideal XI · EA ratings</legend>
    <p class="mp-key sq-sum"><span>Formation <b>${esc(xi.formation)}</b></span><span>Mean EA overall <b>${dec(xi.mean_overall)}</b></span>
      <span>Rated <b>${squad.coverage.matched}/${squad.coverage.players}</b> of the squad</span>${status}</p>
    <div class="sq-xi-in">
      <div class="mp-pitch sq-pitch"><svg viewBox="-3 -3 74 111" role="img" aria-label="${esc(`${squad.name}'s best EA-rated XI in a ${xi.formation}, attacking upwards. The same eleven are listed with their roles.`)}">
        <g class="pitch" transform="matrix(0 -1 1 0 0 105)">${pitchLines(68)}</g>${dots}</svg></div>
      <ol class="sq-list" aria-label="Ideal XI, goalkeeper to attack">${list}</ol>
    </div>
    <p class="note">Best EA-rated XI from listed positions, everyone available: each role takes the highest EA overall among players EA lists there (LW/LM and RW/RM share wide roles). ${why.join(" ")}
      Ratings: ${esc(r.source)}, ${esc(r.edition)} edition, snapshot ${esc(longDate(r.snapshot_date))}. EA overall is EA's player rating, not Floodlight's club strength, and a rating gap is not goals or a win chance.</p>
  </fieldset>`;
}

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

function squadTable(squad, inXi) {
  const observed = squad.roster.observed_at;
  const groups = LINES.map(([key, label]) => [key, label, squad.players.filter((p) => lineOf(p) === key)
    .sort((a, b) => (rated(b) ? b.ea.overall : -1) - (rated(a) ? a.ea.overall : -1) || a.name.localeCompare(b.name))])
    .filter(([, , rows]) => rows.length);
  const cols = `<colgroup><col class="sq-c-name"><col class="sq-c-age"><col class="sq-c-pos"><col class="sq-c-ovr">${STATS.map(() => "<col>").join("")}</colgroup>`;
  const tables = groups.map(([key, label, rows]) => {
    const faces = FACES[key === "GK" ? "GK" : "out"];
    const body = rows.map((p) => {
      const age = ageOn(p.dob, observed);
      const xi = inXi.has(p.id) ? `<span class="sq-mark" title="In the ideal XI" aria-hidden="true">XI</span><span class="vh">Ideal XI: </span>` : '<span class="sq-mark none" aria-hidden="true"></span>';
      const head = `<th scope="row" class="l sq-player" title="${esc(p.name)}">${xi}<span class="sq-nm">${esc(p.name)}</span></th><td>${age ?? "–"}</td>`;
      if (!rated(p)) {
        return `<tr class="unrated">${head}<td class="l">–</td><td class="l sq-nr" colspan="7">not rated${p.status === "ambiguous" ? " · EA match unclear" : ""}</td></tr>`;
      }
      const stats = STATS.map((k) => {
        const v = p.ea[k];
        return `<td${v == null ? "" : v >= 80 ? ' class="b"' : v < 60 ? ' class="off"' : ""}>${v ?? "–"}</td>`;
      }).join("");
      return `<tr>${head}<td class="l sq-pos" title="${esc(p.ea.positions.join(" "))}">${esc(p.ea.positions.join(" "))}</td><td class="sq-ovr-c">${p.ea.overall}</td>${stats}</tr>`;
    }).join("");
    return `<h3 class="dgroup">${label} <span>${rows.length}</span></h3>
      <table class="board sq-table">${cols}<thead><tr><th scope="col" class="l sq-player">Player</th><th scope="col">Age</th><th scope="col" class="l">EA pos</th>
        <th scope="col"><abbr title="EA overall">OVR</abbr></th>${faces.map(([a, t]) => `<th scope="col"><abbr title="${t}">${a}</abbr></th>`).join("")}</tr></thead>
        <tbody>${body}</tbody></table>`;
  }).join("");
  const unrated = squad.coverage.players - squad.coverage.matched;
  return `<fieldset class="frame sq-squad"><legend>Squad · EA ratings</legend>
    <div class="scroll sq-scroll">${tables}</div>
    <p class="note">${squad.coverage.players} players as listed by ${esc(squad.roster.source)} on ${esc(shortDate(observed))}, grouped by EA's first listed position and sorted by EA overall; ages on that date.
      ${unrated ? `${unrated} not rated: no confident EA match by name and birth date. ` : ""}OVR and the six face stats are ${esc(squad.ratings.source)} ratings (${esc(squad.ratings.edition)}); goalkeepers' six are EA's keeper stats. 80 and above are bold, below 60 dim.</p>
  </fieldset>`;
}
