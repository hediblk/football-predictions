// Router: #<competition> (tables), #matches[/YYYY-MM-DD], #match/<competition>/<fixture id>, #clubs[/<club>], #model[/<section>].
import { COMPS, $, loadCrests, loadRun } from "./core.js";
import { showTables } from "./tables.js";
import { showMatches } from "./matches.js";
import { showClubs } from "./clubs.js";
import { showModel } from "./model.js";
import { showMatch } from "./match.js";

const VIEWS = ["tables", "matches", "clubs", "model", "match"];
let lastComp = COMPS[0].slug;
let lastView = null;
let lastArg = null;

function route() {
  const [head = "", arg = "", sub = ""] = location.hash.slice(1).split("/");
  const view = VIEWS.includes(head) && head !== "tables" ? head : "tables";
  if (view === "tables") lastComp = COMPS.some((c) => c.slug === head) ? head : COMPS[0].slug;
  for (const v of VIEWS) $(`view-${v}`).hidden = v !== view;
  // A match page belongs to Matches.
  const tab = view === "match" ? "matches" : view;
  $("tabs").querySelectorAll("a").forEach((a) => a.setAttribute("aria-current", String(a.dataset.view === tab)));
  $("tabs").querySelector('[data-view="tables"]').href = `#${lastComp}`;
  $("subnav").hidden = view !== "tables";
  if (view === "tables") renderSubnav();
  // A new view, club or fixture starts at the top; stepping through match days keeps the place.
  const key = `${arg}/${sub}`;
  if (view !== lastView || (["clubs", "model", "match"].includes(view) && key !== lastArg)) window.scrollTo(0, 0);
  lastView = view;
  lastArg = key;
  if (view === "tables") showTables(lastComp);
  else if (view === "matches") showMatches(arg);
  else if (view === "match") showMatch(arg, sub);
  else if (view === "clubs") showClubs(arg);
  else showModel(arg);
}

function renderSubnav() {
  $("nav").innerHTML = COMPS.map((c) =>
    `<a href="#${c.slug}" aria-current="${c.slug === lastComp}">${c.label}</a>`).join("");
  const on = $("nav").querySelector('[aria-current="true"]');
  if (on) on.scrollIntoView({ block: "nearest", inline: "nearest" });
}

Promise.all([
  loadCrests().catch(() => { /* Club names remain usable if the crest manifest is unavailable. */ }),
  loadRun().catch(() => { /* Each page falls back to its own run time. */ }),
]).finally(() => {
  window.addEventListener("hashchange", route);
  route();
});
