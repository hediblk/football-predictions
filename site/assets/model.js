// Model view: how the forecasts and ratings are made. Static copy, plus the live league factors.
import { LEAGUES, $, esc, getJSON, setStatus } from "./core.js";

export async function showModel(section) {
  document.title = "The model · Floodlight";
  try {
    const clubs = await getJSON("clubs.json");
    setStatus(clubs.generated_at);
    $("c-factors").innerHTML = LEAGUES.map((l) => `${esc(l.label)} <b>${clubs.league_factors[l.slug].toFixed(2)}</b>`).join(" · ");
  } catch {
    $("c-factors").textContent = "unavailable right now";
  }
  if (section) $(section)?.scrollIntoView();
}
