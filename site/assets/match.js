// Match page: everything known about one fixture before kickoff. Finished fixtures use the same page.
import {
  COMPS, compBySlug, $, esc, getJSON, setStatus, ordinal, dec, dayKey, pick, sidePair, clubName, loadForm, played,
} from "./core.js";
import { forecastBlocks, stakesTable, stageLabel, probCells, PENDING } from "./matches.js";
import { rankTag } from "./clubs.js";

const OUTCOMES = ["Home win", "Draw", "Away win"];
const STRENGTH = [["rating", "Rating"], ["attack", "Attack"], ["defense", "Defence"]];
let showing = 0;

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
  const stakes = await stakesTable(m, slug);
  if (ticket !== showing) return;
  document.title = `${m.home} v ${m.away} · Floodlight`;
  setStatus(file.generated_at);
  const slugs = new Map((clubs ? clubs.clubs : []).map((c) => [c.id, c.slug]));
  $("view-match").innerHTML = hero(m, comp, slugs)
    + (m.p ? `<fieldset class="frame"><legend>${m.score ? "The forecast before kickoff" : "The forecast"}</legend><div class="panel mp-fc">${forecastBlocks(m)}</div></fieldset>` : "")
    + (stakes ? `<fieldset class="frame"><legend>What's at stake</legend>${stakes}</fieldset>` : "")
    + sides(m, comp, table, clubs, all.filter(Boolean));
}

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
  let board = "";
  if (m.score) {
    board = `<div class="numeral on" role="img" aria-label="Final score ${m.score[0]}–${m.score[1]}">${m.score[0]}–${m.score[1]}</div>`;
  } else if (m.p) {
    board = `<p class="mp-lbl">${OUTCOMES[fav]}</p>
      <div class="numeral on" role="img" aria-label="${esc(`${OUTCOMES[fav]}: ${Math.round(m.p[fav] * 100)}% chance`)}">${Math.round(m.p[fav] * 100)}<sup>%</sup></div>`;
  }
  return `<p class="crumbs"><a href="#matches/${dayKey(day)}">← Matches, ${esc(day.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }))}</a></p>
    <fieldset class="frame hero mp-hero">
      <legend>${esc(stageLabel(comp, [{ m }]))}</legend>
      <div class="hero-in">
        <div class="who">
          <h1>${side(m.home_id, m.home)}<span class="mp-v">v</span>${side(m.away_id, m.away)}</h1>
          <p class="caption">${when}${facts}</p>
        </div>
        ${board || m.p ? `<div class="mp-board">${board}${m.p ? probCells(m) : ""}</div>` : ""}
      </div>
    </fieldset>`;
}

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
