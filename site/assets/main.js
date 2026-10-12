// Router: #<competition> (tables), #matches[/YYYY-MM-DD], #clubs[/<club>].
import { COMPS, $, loadCrests } from "./core.js";
import { showTables } from "./tables.js";
import { showMatches } from "./matches.js";
import { showClubs } from "./clubs.js";

const VIEWS = ["tables", "matches", "clubs"];
let lastComp = COMPS[0].slug;
let lastView = null;
let lastArg = null;

function route() {
  const [head = "", arg = ""] = location.hash.slice(1).split("/");
  const view = head === "matches" || head === "clubs" ? head : "tables";
  if (view === "tables") lastComp = COMPS.some((c) => c.slug === head) ? head : COMPS[0].slug;
  for (const v of VIEWS) $(`view-${v}`).hidden = v !== view;
  $("tabs").querySelectorAll("a").forEach((a) => a.setAttribute("aria-current", String(a.dataset.view === view)));
  $("tabs").querySelector('[data-view="tables"]').href = `#${lastComp}`;
  $("subnav").hidden = view !== "tables";
  if (view === "tables") renderSubnav();
  // A new view or club starts at the top; stepping through match days keeps the place.
  if (view !== lastView || (view === "clubs" && arg !== lastArg)) window.scrollTo(0, 0);
  lastView = view;
  lastArg = arg;
  if (view === "tables") showTables(lastComp);
  else if (view === "matches") showMatches(arg);
  else showClubs(arg);
}

function renderSubnav() {
  $("nav").innerHTML = COMPS.map((c) =>
    `<a href="#${c.slug}" aria-current="${c.slug === lastComp}">${c.label}</a>`).join("");
  const on = $("nav").querySelector('[aria-current="true"]');
  if (on) on.scrollIntoView({ block: "nearest", inline: "nearest" });
}

loadCrests().catch(() => { /* Club names remain usable if the crest manifest is unavailable. */ }).finally(() => {
  window.addEventListener("hashchange", route);
  route();
});
