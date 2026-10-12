// Champions League fixtures by round (opening on the next one to be played) or by team.
import { $, esc, getJSON, dayKey, parseDay, shortDate, verdict, expandable, clubCrest } from "./core.js";
import { matchRow, matchPanel } from "./matches.js";

const KNOCKOUTS = [
  ["PLAYOFFS", "Knockout play-offs", "PO"], ["LAST_16", "Round of 16", "R16"],
  ["QUARTER_FINALS", "Quarter-finals", "QF"], ["SEMI_FINALS", "Semi-finals", "SF"], ["FINAL", "Final", "F"],
];
let rounds = [];
let teams = [];
let mode = "round";
let chosen = null;
let team = null;
let slugs = new Map();

/* `table` is the competition's forecast: its first club is the default team */
export async function showRounds(table) {
  try {
    const [file, clubs] = await Promise.all([getJSON("matches/champions-league.json"), getJSON("clubs.json").catch(() => null)]);
    slugs = new Map((clubs ? clubs.clubs : []).map((c) => [c.id, c.slug]));
    rounds = group(file.matches);
  } catch (err) {
    $("rounds").innerHTML = `<p class="note">Fixtures could not be loaded (${esc(err.message)}).</p>`;
    return;
  }
  const names = new Map(rounds.flatMap((r) => r.matches.flatMap((m) => [[m.home_id, m.home], [m.away_id, m.away]])));
  teams = [...names].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  if (!rounds.some((r) => r.key === chosen)) chosen = upcoming(rounds).key;
  if (!teams.some((t) => t.id === team)) team = (table.teams.find((t) => names.has(t.id)) || teams[0]).id;
  render();
}

function group(matches) {
  const byKey = new Map();
  for (const m of matches) {
    const ko = KNOCKOUTS.find(([stage]) => stage === m.stage);
    const key = ko ? ko[0] : `md${m.md}`;
    if (!byKey.has(key)) {
      byKey.set(key, ko
        ? { key, label: ko[1], short: ko[2], order: 100 + KNOCKOUTS.indexOf(ko), matches: [] }
        : { key, label: `Matchday ${m.md}`, short: `MD ${m.md}`, order: m.md, matches: [] });
    }
    byKey.get(key).matches.push(m);
  }
  const list = [...byKey.values()].sort((a, b) => a.order - b.order);
  for (const r of list) r.matches.sort((a, b) => a.kickoff.localeCompare(b.kickoff) || a.id - b.id);
  return list;
}

/* the first round with a game still to play (results arrive the morning after), else the last one */
function upcoming(list) {
  const recent = Date.now() - 2 * 864e5;
  return list.find((r) => r.matches.some((m) => !m.score && new Date(m.kickoff) > recent)) || list[list.length - 1];
}

const span = (r) => {
  const first = r.matches[0].kickoff, last = r.matches[r.matches.length - 1].kickoff;
  const [a, b] = [new Date(first), new Date(last)];
  if (dayKey(a) === dayKey(b)) return shortDate(first);
  return a.getMonth() === b.getMonth() ? `${a.getDate()}–${shortDate(last)}` : `${shortDate(first)} – ${shortDate(last)}`;
};

function dayLabel(key) {
  const today = dayKey(new Date());
  const offset = Math.round((parseDay(key) - parseDay(today)) / 864e5);
  const near = { [-1]: "Yesterday", 0: "Today", 1: "Tomorrow" }[offset];
  const date = parseDay(key).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
  return near ? `${near} · ${date}` : date;
}

function record(matches) {
  const calls = matches.map(verdict).filter(Boolean);
  return calls.length ? ` · ${calls.length} played · model called <b>${calls.filter((v) => v.hit).length} of ${calls.length}</b>` : "";
}

function render() {
  const next = upcoming(rounds).key;
  const list = mode === "round" ? rounds.map((r) => [r.key, r.label + (r.key === next ? " · next" : "")]) : teams.map((t) => [t.id, t.name]);
  const value = mode === "round" ? chosen : team;
  const index = list.findIndex(([key]) => key === value);
  const noun = mode === "round" ? "round" : "team";
  $("round-nav").innerHTML = `
    <div class="seg" role="group" aria-label="Show fixtures">
      <button type="button" class="chip" data-mode="round" aria-pressed="${mode === "round"}">By round</button>
      <button type="button" class="chip" data-mode="team" aria-pressed="${mode === "team"}">By team</button>
    </div>
    <div class="rnav">
      <button type="button" class="nav-step" data-step="-1" aria-label="Previous ${noun}"${index > 0 ? "" : " disabled"}>‹</button>
      <span class="picker">${mode === "team" ? clubCrest(team) : ""}<select id="round-pick" aria-label="Choose a ${noun}">
        ${list.map(([key, label]) => `<option value="${key}"${key === value ? " selected" : ""}>${esc(label)}</option>`).join("")}
      </select></span>
      <button type="button" class="nav-step" data-step="1" aria-label="Next ${noun}"${index < list.length - 1 ? "" : " disabled"}>›</button>
    </div>`;
  // Fit the dropdown to its chosen label, so the caret sits right after the text.
  const select = $("round-pick");
  const probe = document.createElement("span");
  probe.className = "probe";
  probe.textContent = select.options[select.selectedIndex].text;
  select.after(probe);
  select.style.width = `${probe.offsetWidth + 44}px`;
  probe.remove();
  if (mode === "round") renderRound(rounds.find((r) => r.key === chosen));
  else renderTeam(teams.find((t) => t.id === team));
}

function renderRound(round) {
  const days = new Map();
  for (const m of round.matches) {
    const key = dayKey(new Date(m.kickoff));
    if (!days.has(key)) days.set(key, []);
    days.get(key).push(m);
  }
  $("rounds").innerHTML = `<p class="rsum">${round.matches.length} matches · ${esc(span(round))}${record(round.matches)}</p>`
    + [...days].map(([key, list]) => `<h3 class="dgroup">${esc(dayLabel(key))}</h3>
      <div class="mlist">${list.map((m) => matchRow(m, "champions-league")).join("")}</div>`).join("")
    + (rounds[rounds.length - 1].order < 100 ? `<p class="note">Knockout rounds join the list once they are drawn.</p>` : "");
}

function renderTeam(club) {
  const games = rounds.flatMap((r) => r.matches.filter((m) => m.home_id === club.id || m.away_id === club.id).map((m) => [r, m]));
  const profile = slugs.has(club.id) ? ` · <a href="#clubs/${slugs.get(club.id)}">club profile →</a>` : "";
  const when = (r, m) => (status) => `<b>${r.short}</b><br>${esc(shortDate(m.kickoff))}<br>${status}`;
  $("rounds").innerHTML = `<p class="rsum">${games.length} matches${record(games.map(([, m]) => m))}${profile}</p>
    <div class="mlist by-team">${games.map(([r, m]) => matchRow(m, "champions-league", when(r, m))).join("")}</div>`;
}

$("round-nav").addEventListener("click", (e) => {
  const seg = e.target.closest("button[data-mode]");
  const step = e.target.closest("button[data-step]");
  if (seg) mode = seg.dataset.mode;
  else if (step && mode === "round") chosen = rounds[rounds.findIndex((r) => r.key === chosen) + Number(step.dataset.step)].key;
  else if (step) team = teams[teams.findIndex((t) => t.id === team) + Number(step.dataset.step)].id;
  else return;
  render();
});
$("round-nav").addEventListener("change", (e) => {
  if (e.target.id !== "round-pick") return;
  if (mode === "round") chosen = e.target.value;
  else team = Number(e.target.value);
  render();
});

expandable($("rounds"), ".mrow", (row) => {
  const m = rounds.flatMap((r) => r.matches).find((x) => String(x.id) === row.dataset.id);
  return matchPanel(m, slugs);
});
