// Model view: how the forecasts and ratings are made. Static copy, plus the live league averages.
import { LEAGUES, $, dec, esc, getJSON, setStatus } from "./core.js";

import { showTrackRecord } from "./scorecard.js";

export async function showModel(section) {
  document.title = "The model · Floodlight";
  try {
    const clubs = await getJSON("clubs.json");
    setStatus(clubs.generated_at);
    $("c-factors").innerHTML = LEAGUES.map((l) => `${esc(l.label)} <b>${dec(clubs.league_averages[l.slug])}</b>`).join(" · ");
    $("c-pool").textContent = `${clubs.scale.clubs} clubs in ${clubs.scale.leagues} European top flights`;
  } catch {
    $("c-factors").textContent = "unavailable right now";
  }
  await showTrackRecord();
  if (section) $(section)?.scrollIntoView();
}
