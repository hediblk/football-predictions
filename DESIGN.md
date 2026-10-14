# Floodlight — design DNA

Chosen from four dealt directions (design-for-ai dealer, project `final-table-football-forecasts`, 2026-10-11, hand 3). Dark only, by request.

## Scoreboard

GROUNDING   1980s stadium electronic scoreboards' dot-matrix bulb numerals + Bloomberg Terminal's dense, ruled tables.
The page reads like the board at the ground: one lit number you see from the stands, then rows of small print you lean in for.

TYPE        Big Shoulders Display (condensed civic signage, 600–900) for names, labels and the hero numeral, over JetBrains Mono (400–700) for every number and running text. Hierarchy by weight, caps and tracking, not size steps; one huge jump for the hero.
COLOR       seed amber (h68) · warm near-black ground · mono harmony · one lit accent (amber) plus a red bulb reserved for relegation/elimination.
COMPOSITION Poster Bleed (Terminal/Mono-Core) — the favourite's percentage is set at poster scale and bleeds off the frame's right edge; everything else is caption-rank and ruled.
MOTION      State-only and short: the hero numeral "powers on" in four steps (≤150 ms, stepped) when the competition changes; changing match day slides the day strip and the fixtures across (260 ms ease-out), and the strip can be dragged. Nothing else moves. Off under `prefers-reduced-motion`.
REGISTER    Product structure (tables, nav) · expressive at: the hero numeral only.
DNA         Terminal/Mono-Core base + type voice borrowed from Swiss/International (a condensed grotesk instead of mono display) · dominant: color (the single lit amber).
SIGNATURE   Section headings are legends cut into their frame's top border, like the labels on a stadium board; probabilities are drawn as bulbs whose brightness is the chance.

## Tokens

```css
--bg:      #131312;  /* page */
--panel:   #1a1919;  /* frames, sticky cells */
--bulb-off:#221f1b;  /* unlit bulb */
--rule:    #3f3b36;  /* frame borders, cut lines */
--rule-2:  #262421;  /* row rules */
--ink:     #ebe7e3;  /* primary text, 14.3:1 on panel */
--ink-2:   #bcb6b0;  /* secondary text, 8.7:1 */
--dim:     #8a837c;  /* labels, 4.9:1 */
--amber:   #eaa85e;  /* the lit accent */
--amber-t: #d7af86;  /* amber text on dark, 8.7:1 */
--red:     #e1524f;  /* relegation / elimination bulb; a missed call */
--green:   #5ad664;  /* a called result, or a rank gained: lamp / arrow */
--green-t: #88cb8a;  /* "Called" text */
--draw:    #8a8f98;  /* a drawn game: form boxes and dots */
```

`--green` came from the same generator (`--seed 145`, accent steps 9 and 11); it marks a called result and, with `--green-t`, a rank gained. Calls always pair a lamp with a word (Called, Missed, Exact), never colour alone.

## Components added with Matches and Clubs

- **Club crests:** full-colour original artwork beside club names; 18 px inline, 24 px in rows and brackets, 36 px on cards, 80 px in heroes (64 px on phones). Preserve proportions and keep the club name visible. Use published light or outlined variants for dark artwork; keep crest containers transparent. Charts keep their dots, with crests in hover details; native dropdown options remain text with a crest beside the selected club.

- **Logo:** the favicon's 3×3 bulb grid (five lit, four off) beside the Floodlight wordmark, in the header and the footer.
- **Section tabs** (Tables, Matches, Clubs, Model) sit beside the logo; the competition row appears only under Tables. Methodology lives only on Model; other views link to it.
- **Footer:** brand, Project links (Model, GitHub, roadmap) and Data links to every provider, above the model-run time.
- **Outcome bulbs:** a match's home/draw/away chances are three small bulbs whose brightness is the chance; the brightest is the model's pick, and a ruled box marks what actually happened.
- **Forecast origin:** the dim line in a finished match's "The call" block names a saved pre-kickoff forecast as "Published before kickoff", with the model run's UTC time and date. Otherwise it says "Reconstructed", using results before 00:00 UTC on match day.
- **Day strip:** nine days with big numerals and a game count; the chosen day is lit and underlined in amber.
- **Call strip:** on a club page, one bar per played game; its height is the chance the model gave what happened, green when that was the pick and red when not, so it agrees with the "Called N of M" line.
- **Rank plates:** category ranks (#1 attack, #1 defence, 1st in league) sit on a lit amber plate; top-ten ranks are amber text; the rest stay dim.
- **Stakes:** a fixture's conditional chances for each result, with the likeliest result lit amber. They're shown only when a result swings a chance by at least 2 points and by more than three standard errors, so simulation noise never reads as stakes. On top of that, a title swing must be 8 points or more and a top-four or relegation swing 15, so only games that really matter carry a Stakes tag, a stakes table or a place in "Games that decide our season". Champions League games use the same trophy bar (8) but 30 points for the top eight and top 24, since one league-phase game moves those by 25 or more almost every time; a club in both lists its league and Champions League games under separate ruled headings.
- **Club board:** ruled cells, not cards, with the rating as the lit number and attack/defence hairline meters. Champions League clubs from outside the five leagues show a country code where a league would go, and their pages follow the Champions League season.
- **Movement arrows:** weekly rank changes use a green ▲ with the number of places gained or a red ▼ with the places dropped, a dim dash when unchanged and dim "new" for clubs without a previous week; colour never stands alone. This extends `--green`/`--green-t` (otherwise reserved for called results) and `--red` (relegation, misses) to rank movement.
- **Form:** results use the standard colours: win green, draw grey (`--draw`), loss red. The club page shows its last six as lettered boxes; the standings (a Form column) and an opened match (under both clubs' names, as they stood before kickoff) show the last five as 7 px dots with the result in a hover tip and a spoken label.
- **Form extras:** match rows carry both clubs' dots under their names; opened panels add streaks (3+ wins or losses, 4+ unbeaten or winless) and recent meetings this season; the club hero shows dots and the streak, and the season card home and away dots. Fixture strength (`#rank`, red for the top ten, green for the bottom thirty) sits beside each upcoming opponent; the number is always shown. Standings headers sort descending on press (press again to restore); cut lines hide while sorted.
- **Race charts:** chances through the season as thin lines on the ruled grid. The leader is lit amber (red for relegation) and the others are ink with dash patterns, never extra hues. Names sit at the line ends.
- **Match page** (`#match/<competition>/<fixture id>`): one page per fixture, under the Matches tab with no competition row, opened from "Match page →" in every expanded match and, on club pages, from a dim "→" at the end of each game row (its own tab stop; the rest of the row still expands) and from each call-strip bar. A "← Matches, <day>" crumb leads back. The hero names both clubs with 80 px crests (64 px on phones) and sets the favourite's chance as the poster numeral, labelled with the outcome ("Away win") and with the three outcome bulbs under it; a finished fixture shows the final score there instead. Below it, "The forecast" reuses the expanded match's likeliest scores, goals and call ("The forecast before kickoff" once played), "What's at stake" reuses the stakes table and hides when nothing passes the bar, and "The two sides" is one ruled board: home values right-aligned, the metric in the middle, away values left-aligned. Ratings carry rank plates and hairline meters with the average-club tick; last five are lettered result boxes with scores, oldest first; goals and xG per game state their xG coverage. Champions League clubs from outside the five leagues have no xG, so their side says so. An unknown fixture shows one note linking back to Matches.
- **Match page after full time:** a finished fixture with a forecast gets "After · Before" chips in its hero (After by default); Before is the pre-game page unchanged. After keeps the final score as the numeral and the outcome bulbs with the ruled box on the result, plus one sentence on the chance the model gave it and whether that forecast was published before kickoff or reconstructed. "Forecast against result" gives the actual score's chance and its place in the likeliest scores, the result's rank this season by the chance given to what happened (least or most expected, whichever is nearer), and a paired board with exact labels: "Expected before kickoff (model)", "Goals" and, where Understat has it, "Shot xG (Understat)". "What it changed" shows season chances at the refreshes either side of the game (both clubs' live races, plus rivals from stakes saved before kickoff) with ▲▼ changes, coloured green when good for that club and red when bad (a rising relegation chance is red), and a dim dash under 2 points; the stakes table as saved before kickoff, its "Before" column from the last refresh before the game and the result that happened lit; and both clubs' ratings from the weekly ranking frozen before the game to the next one (or today's), labelled as covering every game in that span. Each part hides without its data.
- **Shot report ("Chances"):** in a finished league game's After mode, between "Forecast against result" and "What it changed", when Understat has its shots; the Champions League has none. The **shot map** is one full pitch in `--rule` lines on `--panel`, home shooting right and away mirrored to shoot left, with the clubs named under it and arrows for direction. Circle area is the shot's xG; goals are filled amber bulbs, saved shots filled `--ink-2`, everything else outlined. Hover or tap shows the player, minute, xG, situation and outcome, and a `<details>` "Shot list" table under the map is its text equivalent. Own goals aren't chances: they stay off the map and out of the xG lines, and the note names them. The **xG timeline** draws cumulative shot xG as step lines from 0' to the last minute played, home solid ink and away dashed `--ink-2`, with the totals at the line ends and goals as amber bulbs on the scoring side's line, labelled with the minute and surname ("(og)" for an own goal, on the line of the side it counted for). Shots in the same minute combine as 1 − ∏(1 − xG) when that gives Understat's match xG, plain sums when those do; a side that matches neither is labelled "summed shot xG". "From the chances" gives the after-the-fact home/draw/away chances as three plain numbers, never bulbs, labelled as not a forecast; "Standouts" is a ruled board of the top three players by xG + xA.

Generated with `palette.mjs --seed 67.65 --chroma balanced --harmony mono --scheme dark`; `--dim` was lifted from the ramp's step 9 to clear 4.5:1 for small labels.
