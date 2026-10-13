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
--green:   #5ad664;  /* a called result: lamp only */
--green-t: #88cb8a;  /* "Called" text */
```

`--green` came from the same generator (`--seed 145`, accent steps 9 and 11) and only marks a called result. Calls always pair a lamp with a word (Called, Missed, Exact), never colour alone.

## Components added with Matches and Clubs

- **Club crests:** full-colour original artwork beside club names; 18 px inline, 24 px in rows and brackets, 36 px on cards, 80 px in heroes (64 px on phones). Preserve proportions and keep the club name visible. Use published light or outlined variants for dark artwork; keep crest containers transparent. Charts keep their dots, with crests in hover details; native dropdown options remain text with a crest beside the selected club.

- **Logo:** the favicon's 3×3 bulb grid (five lit, four off) beside the Floodlight wordmark, in the header and the footer.
- **Section tabs** (Tables, Matches, Clubs, Model) sit beside the logo; the competition row appears only under Tables. Methodology lives only on Model; other views link to it.
- **Footer:** brand, Project links (Model, GitHub, roadmap) and Data links to every provider, above the model-run time.
- **Outcome bulbs:** a match's home/draw/away chances are three small bulbs whose brightness is the chance; the brightest is the model's pick, and a ruled box marks what actually happened.
- **Day strip:** nine days with big numerals and a game count; the chosen day is lit and underlined in amber.
- **Call strip:** on a club page, one bar per played game; its height is the chance the model gave what happened, green when that was the pick and red when not, so it agrees with the "Called N of M" line.
- **Rank plates:** category ranks (#1 attack, #1 defence, 1st in league) sit on a lit amber plate; top-ten ranks are amber text; the rest stay dim.
- **Club board:** ruled cells, not cards, with the rating as the lit number and attack/defence hairline meters.
- **Race charts:** chances through the season as thin lines on the ruled grid. The leader is lit amber (red for relegation) and the others are ink with dash patterns, never extra hues. Names sit at the line ends.

Generated with `palette.mjs --seed 67.65 --chroma balanced --harmony mono --scheme dark`; `--dim` was lifted from the ramp's step 9 to clear 4.5:1 for small labels.
