import { dec, esc, shortDate } from "./core.js";

const forecastedResult = (m, leaguePhaseOnly) => m.status === "FINISHED"
  && Array.isArray(m.score) && m.score.length === 2
  && Array.isArray(m.p) && m.p.length === 3 && m.p.every(Number.isFinite)
  && (!leaguePhaseOnly || m.stage === "LEAGUE_STAGE");

const pointsFor = (m, home) => {
  const [hg, ag] = m.score;
  const actual = hg === ag ? 1 : (hg > ag) === home ? 3 : 0;
  const expected = m.p[1] + 3 * m.p[home ? 0 : 2];
  return { actual, expected };
};

export function pointsForClub(matches, clubId, leaguePhaseOnly = false) {
  const rows = matches.filter((m) => forecastedResult(m, leaguePhaseOnly)
      && (m.home_id === clubId || m.away_id === clubId))
    .map((match) => {
      const isHome = match.home_id === clubId;
      return { match, isHome, ...pointsFor(match, isHome) };
    })
    .sort((a, b) => a.match.kickoff.localeCompare(b.match.kickoff));
  let actual = 0;
  let expected = 0;
  const games = rows.map((row) => {
    actual += row.actual;
    expected += row.expected;
    return { ...row, actualTotal: actual, expectedTotal: expected };
  });
  const published = games.filter((g) => g.match.published === true).length;
  return { games, n: games.length, published, actual, expected, delta: actual - expected };
}

export function pointsByClub(matches, leaguePhaseOnly = false) {
  const ids = new Set(matches.flatMap((m) => [m.home_id, m.away_id]).filter((id) => id != null));
  return new Map([...ids].map((id) => [id, pointsForClub(matches, id, leaguePhaseOnly)]));
}

const signed = (n) => `${n < 0 ? "−" : "+"}${Math.abs(n).toFixed(1)}`;
const result = (points) => points === 3 ? "Win" : points === 1 ? "Draw" : "Loss";

export function pointsComparison(club, matches, leaguePhaseOnly = false) {
  const stats = pointsForClub(matches, club.id, leaguePhaseOnly);
  if (!stats.n) return `<p class="note">No finished games with forecasts yet. <b>0</b> published forecasts.</p>`;

  const width = 720, height = 220, pad = { l: 48, r: 14, t: 12, b: 30 };
  const max = Math.max(1, Math.ceil(Math.max(...stats.games.map((g) => Math.max(g.actualTotal, g.expectedTotal)))));
  const x = (game) => pad.l + (game / stats.n) * (width - pad.l - pad.r);
  const y = (points) => height - pad.b - (points / max) * (height - pad.t - pad.b);
  const points = (key) => [{ [key]: 0 }, ...stats.games].map((g, i) => `${i ? "L" : "M"}${x(i)},${y(g[key] ?? 0)}`).join(" ");
  const grid = [...new Set([0, Math.ceil(max / 2), max])].map((v) => `<g><line class="grid" x1="${pad.l}" x2="${width - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="tick" x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text></g>`).join("");
  const gameRows = stats.games.map((g, i) => {
    const m = g.match;
    const opponent = g.isHome ? m.away : m.home;
    const origin = m.published === true ? "Published before kickoff" : "Reconstructed before match day";
    return `<tr><td>${i + 1}</td><td>${shortDate(m.kickoff)}</td><td class="l">${esc(opponent)}</td><td>${result(g.actual)}</td>
      <td>${g.actualTotal}</td><td>${dec(g.expectedTotal, 1)}</td><td class="l">${origin}</td></tr>`;
  }).join("");
  const source = `${stats.published} of ${stats.n} forecasts were published before kickoff; ${stats.n - stats.published} were reconstructed.`;
  const sentence = `${club.name} have ${stats.actual} point${stats.actual === 1 ? "" : "s"} from games the model expected to yield ${dec(stats.expected, 1)} (${signed(stats.delta)}).`;

  return `<p class="lead">${esc(sentence)}</p>
    <p class="note pm-source">${source}${leaguePhaseOnly ? " Champions League points cover the league phase." : ""}</p>
    <figure class="pm-chart">
      <div class="key"><span><i class="pm-key actual"></i>Actual points</span><span><i class="pm-key expected"></i>Model-expected points</span></div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(`${club.name}: cumulative actual and model-expected points across ${stats.n} finished games with forecasts`)}">
        ${grid}<path class="actual" d="${points("actualTotal")}"/><path class="expected" d="${points("expectedTotal")}"/>
        <text class="tick" x="${pad.l}" y="${height - 6}">Start</text><text class="tick" x="${width - pad.r}" y="${height - 6}" text-anchor="end">Game ${stats.n}</text>
      </svg>
      <figcaption class="note">Cumulative points by game number. Actual points use the finished result; expected points are 3 × win probability + draw probability.</figcaption>
    </figure>
    <details class="pm-list"><summary>Game-by-game points and forecast origin</summary><div class="scroll"><table class="board">
      <thead><tr><th>Game</th><th>Date</th><th class="l">Opponent</th><th>Result</th><th>Actual pts</th><th>Model pts</th><th class="l">Forecast</th></tr></thead>
      <tbody>${gameRows}</tbody></table></div></details>`;
}

const validXg = (m) => Array.isArray(m.xg) && m.xg.length === 2 && m.xg.every(Number.isFinite);
function xgWindow(games) {
  const covered = games.filter(validXg);
  if (!covered.length) return { n: 0, total: games.length, for: null, against: null, difference: null };
  const forSum = covered.reduce((sum, m) => sum + m.xg[m.isHome ? 0 : 1], 0);
  const againstSum = covered.reduce((sum, m) => sum + m.xg[m.isHome ? 1 : 0], 0);
  const xgFor = forSum / covered.length;
  const xgAgainst = againstSum / covered.length;
  return { n: covered.length, total: games.length, for: xgFor, against: xgAgainst, difference: xgFor - xgAgainst };
}

export function rollingXg(club, matches) {
  const played = matches.filter((m) => m.status === "FINISHED" && Array.isArray(m.score))
    .sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  const windows = [5, 10].map((size) => ({ size, ...xgWindow(played.slice(-size)) }));
  const cells = windows.map((w) => `<tr><td class="l" aria-label="Last ${w.size}, xG coverage ${w.n} of ${w.total} games">Last ${w.size} <small>${w.n}/${w.total}</small></td>
    <td>${dec(w.for, 2)}</td><td>${dec(w.against, 2)}</td><td>${w.difference == null ? "–" : signed(w.difference)}</td></tr>`).join("");
  const rolling = played.map((_, i) => {
    const window = played.slice(Math.max(0, i - 4), i + 1);
    const stats = xgWindow(window);
    return stats.difference == null ? null : { game: i + 1, ...stats };
  });
  const available = rolling.filter(Boolean);
  const chart = available.length ? sparkline(club, rolling) : `<p class="note">No xG was reported for the completed games shown; coverage is listed above.</p>`;
  const detail = available.length ? `<details class="pm-list"><summary>Five-game rolling xG values</summary><div class="scroll"><table class="board">
    <thead><tr><th>After game</th><th>Difference / game</th><th>Coverage</th></tr></thead>
    <tbody>${available.map((v) => `<tr><td>${v.game}</td><td>${signed(v.difference)}</td><td>${v.n} of ${v.total} games</td></tr>`).join("")}</tbody>
    </table></div></details>` : "";
  return `<h3 class="sub">Rolling xG · last 5 and last 10</h3>
    <div class="scroll"><table class="board stats pm-xg-table"><thead><tr><th class="l">Window / xG</th><th>xG for</th><th>xG against</th><th>Difference</th></tr></thead><tbody>${cells}</tbody></table></div>
    <p class="note">The small count is games with xG / games in the window; averages use only games with xG.</p>
    <figure class="pm-spark">${chart}<figcaption class="note">Five-game rolling xG difference per covered game; windows without xG are left blank.</figcaption></figure>${detail}`;
}

function sparkline(club, rolling) {
  const width = 600, height = 112, pad = { l: 8, r: 8, t: 8, b: 22 };
  const values = rolling.filter(Boolean);
  const range = Math.max(0.1, ...values.map((v) => Math.abs(v.difference))) * 1.1;
  const x = (game) => pad.l + ((game - 1) / Math.max(1, rolling.length - 1)) * (width - pad.l - pad.r);
  const y = (value) => pad.t + ((range - value) / (range * 2)) * (height - pad.t - pad.b);
  const parts = [];
  let segment = [];
  const flush = () => {
    if (segment.length) parts.push(`<path d="${segment.map((v, i) => `${i ? "L" : "M"}${x(v.game)},${y(v.difference)}`).join(" ")}"/>`);
    segment = [];
  };
  for (const value of rolling) { if (value) segment.push(value); else flush(); }
  flush();
  const dots = values.map((v) => `<circle cx="${x(v.game)}" cy="${y(v.difference)}" r="2.5"/>`).join("");
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(`${club.name}: five-game rolling xG difference, ${values.length} windows with xG`)}">
    <line class="zero" x1="${pad.l}" x2="${width - pad.r}" y1="${y(0)}" y2="${y(0)}"/><g class="line">${parts.join("")}${dots}</g>
    <text class="tick" x="${pad.l}" y="${height - 5}">Game 1</text>${rolling.length > 1 ? `<text class="tick" x="${width - pad.r}" y="${height - 5}" text-anchor="end">Game ${rolling.length}</text>` : ""}
    </svg>`;
}
