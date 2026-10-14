# Football features and post-match research

Research date: 14 October 2026. Recommendations for Floodlight; this document does not change the implementation roadmap.

Repository update before publication: `main` at `1c06bdc` now includes UCL match stakes, UCL clubs outside the five leagues in the power ranking, versioned assets and automated browser checks ([ADR 0002](adr/0002-site-browser-checks.md)). These changes landed after the initial research. The inventory and recommendations below reflect them; the original 36-idea list retains UCL stakes as a completed item.

The strongest direction is to connect three things in one place: **what the forecast expected, what happened in the match, and how the season outlook changed**. Floodlight already has much of the numerical foundation. Better post-match reports, round recaps, forecast evaluation and shareable graphics would make that foundation easier to understand and more useful throughout the week.

**Scope and evidence**

Reviewed nine core products: Opta Analyst, FotMob, Sofascore, WhoScored, Understat, FBref, ClubElo, Euro Club Index and Forebet. Hudl StatsBomb, Twenty3 and Markstats provide additional analysis and publishing references. These are different kinds of products: consumer match centres, statistical reference sites, forecast publishers and professional analytics tools. Forebet is included as a feature benchmark, without an endorsement of prediction accuracy.

Research used official product pages, current interfaces, methodology/help pages, articles and official social examples. Historical articles are identified where relevant. Social access was uneven: some Instagram and Telegram posts were directly inspectable, while many X pages were blocked. Embedded posts and publishers' own documented examples supplement that evidence. The recurrence below is qualitative within this sample, not a measured market-wide frequency ranking or engagement study. A feature mentioned in an official guide is not proof that every competition has it.

The project review covered README, CONTEXT, ROADMAP, PLAN, DESIGN, ADRs 0001 and 0002, the site data contract and the relevant exporter/model/site implementation. It excluded inactive deferred material.

**1. What the established products repeatedly show**

| Product | Verified features and artifacts | Best lesson for Floodlight |
| --- | --- | --- |
| **Opta Analyst** | Match outcome probabilities, predicted final positions and competition chances in its [forecast hub](https://theanalyst.com/articles/opta-football-predictions). [Actual / Expected / Predicted table controls](https://theanalyst.com/competition/premier-league/table). A [current match report](https://theanalyst.com/articles/arsenal-vs-leeds-stats-premier-league-10-2026) combines recap, xG, team/player statistics and links to passing/chalkboard tools. | Connect forecasts to results and competition consequences. Keep observed performance and future forecasts visibly distinct. |
| **FotMob** | Its [current glossary and FAQ](https://www.fotmob.com/faq) cover xG, xGOT, ratings, player traits, goals prevented and the xG table. A [current player page](https://www.fotmob.com/en-GB/players/815006/phil-foden) includes shot/heat maps, percentile traits, per-90 views and recent match ratings. | Make advanced numbers easy to read in context; use a focused match or club view as the entry point. Player depth is a separate data investment. |
| **Sofascore** | [Official feature explanation](https://www.sofascore.com/news/from-expected-goals-to-player-of-the-match-decoding-key-football-statistics-for-better-insights) covers xG/xA, Attack Momentum, player ratings, attribute radar, comparison and team of the week. Its [rating description](https://corporate.sofascore.com/about/rating) explains its own algorithm. | Chronology, player summaries and comparisons are familiar fan formats. A provider's rating or momentum metric needs its own definition. |
| **WhoScored** | A [current preview](https://www.whoscored.com/matches/2029121/preview/europe-champions-league-2026-2027-manchester-city-paris-saint-germain) has probable formations, absences, team news, head-to-head, standings and a score prediction. A [completed match](https://www.whoscored.com/matches/2029132/live/europe-champions-league-2026-2027-arsenal-lille) has timeline, player statistics, chalkboard and heatmaps. [Methodology](https://www.whoscored.com/explanations) describes proprietary ratings. | Provide context around the forecast. Lineups and injuries would require reliable new inputs; historical head-to-head is context, not evidence to activate a model adjustment. |
| **Understat** | The [league view](https://understat.com/league/EPL) compares actual and expected goals/points with home/away and date controls. A [current match view](https://understat.com/match/31239) has a shot map, cumulative xG timeline with goal markers, shots, PPDA and retrospective result chances. | Shot map plus xG timeline is a compact post-match explanation. Retrospective chances must be labelled separately from pre-match probabilities. |
| **ClubElo** | [Fixtures](https://clubelo.com/Fixtures) show 1X2 and season-objective chances conditional on win/draw/loss, including UCL top-eight/top-24 stakes. [Club pages](https://clubelo.com/Arsenal) connect results with rating changes and rank. | Reuse Floodlight's existing domestic/UCL stakes in reports and cards. Explain rating movement with a dated ledger and trend. |
| **Euro Club Index** | [Methodology](https://www.euroclubindex.com/methodology/) describes European club strength, weekly changes, match probabilities and league winner chances with projected points/ranges. [League odds](https://www.euroclubindex.com/league-odds/) exposes league-flow and chance-matrix sections; [team comparison](https://www.euroclubindex.com/teams-comparison/) is a dedicated view. Some table rows remained client-rendered during text inspection. | Ratings, forecasts, history and comparisons form a coherent product. Compare clubs on Floodlight's existing common scale. |
| **Forebet** | Its [official feature inventory](https://www.forebet.com/en/soccer-picks-system/) lists 1X2, exact-score predictions, average goals, totals, BTTS, results, form, calendar, favorites and comparison. Its [favorite predictions table](https://www.forebet.com/en/favourite-predictions/) places predictions beside results. | Most forecast quantities already exist in Floodlight. Favorites, filters and legible forecast/result comparisons are useful additions. |
| **FBref** | Basic historical statistics remain, but Sports Reference's [20 January 2026 notice](https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/) says provider-supplied advanced data was removed after access ended. | Borrow reference-table clarity. Do not plan around the former free advanced-stat/scouting dataset being available today. |

**Recurrence by feature family**

| Recurring family | Evidence in the reviewed products | Assessment for Floodlight |
| --- | --- | --- |
| Fixture/result hub, form and team context | FotMob, WhoScored, Forebet, ClubElo | Basic fan utility. Much is already present. Improve match navigation and focused pages before adding more small statistics. |
| Match xG and observed performance | FotMob, Sofascore, Understat, Opta | A core analysis layer. Floodlight already displays observed match-total xG; the opportunity is a clearer report and trend charts. |
| Player ratings and standout-player summaries | FotMob, Sofascore, WhoScored | Repeated consumer pattern, especially on social. Expensive to reproduce credibly without player data. |
| 1X2 probabilities | Opta, ClubElo, Euro Club Index, Forebet | Core forecast utility, already covered. Emphasise the full probability distribution and its origin. |
| Competition chances and projected tables | Opta, ClubElo, Euro Club Index | Core forecast product pattern, already covered. Add movement, context and shareable artifacts. |
| Club strength, movement and comparison | Opta Power Rankings, ClubElo, Euro Club Index | Fits the existing Clubs tab; historical comparison adds more than another current ranking. |
| Spatial and chronological match analysis | Understat, WhoScored, Opta; StatsBomb references below | Shot maps and xG timelines are the best first extension once shot data is available. Pass networks require more data. |
| Goals markets and exact scores | Particularly prominent in Forebet | Floodlight already has likely scores, BTTS and over 2.5. Keep them as match detail rather than adding a broad betting interface. |

Conditional season stakes were especially clear in ClubElo. They are highly relevant even though this research does not establish them as ubiquitous. Public forecast scorecards are also a strong fit because Floodlight explicitly values evaluation; the review does not establish their absence from other products.

**2. What their socials and post-match publishing teach us**

| Verified example | Artifact format | Adaptation for Floodlight |
| --- | --- | --- |
| Stats Perform's [OptaJoe retrospective, 2024](https://www.statsperform.com/insights/optajoe-turns-15-in-2024/) documents its recognisable number/fact format, with real examples and shot/pass/xG/momentum graphics. | One contextual fact, easily recognised in a feed. | One grounded forecast or season-change takeaway per graphic. Develop Floodlight's own writing and visual identity. |
| [Opta's 10 October 2026 match report](https://theanalyst.com/articles/arsenal-vs-leeds-stats-premier-league-10-2026) embeds an [official social post](https://x.com/OptaAnalyst/status/2108906570633642494). The embedded content was readable; direct X access was blocked. | A surprising match fact travels separately from the full report. | A small card linking back to the forecast/result report. Use comparisons supported by our actual coverage. |
| WhoScored official Instagram: [player of the week](https://www.instagram.com/officialwhoscored/p/DecBxjqjaxD/), [last-five ratings](https://www.instagram.com/officialwhoscored/p/DecGn2LDRWL/) and [team of the week](https://www.instagram.com/officialwhoscored/p/Deb-QwMDUoy/), inspected in its October 2026 feed. | Large headline metric, short supporting stats, repeatable player/rating template. | Weekly club-strength movers, rolling team performance and revised competition chances using our existing club data. |
| FotMob official Instagram: [Premier League team of the week](https://www.instagram.com/fotmobapp/p/Debagd7IRH9/), [La Liga team of the week](https://www.instagram.com/fotmobapp/p/DebyVeIiAEd/) and [match-event/player takeaway](https://www.instagram.com/fotmobapp/p/Decv3izCCx1/), inspected in October 2026. | Pitch XIs or a recognisable match-interface element plus one takeaway. | Reuse Floodlight's bulbs, rows and probability display in social cards. A club or race recap is feasible before player ratings. |
| Sofascore official Instagram: [full-time performance summary](https://www.instagram.com/sofascore_football/p/DecxSYluk7H/), [two-player comparison](https://www.instagram.com/sofascore_football/p/Dec4T1POamj/) and [historical scoring leaderboard](https://www.instagram.com/sofascore_football/p/Dec2tLjH8rk/), inspected in October 2026. | Final score with a small set of explanatory stats; paired metrics; a ranked historical comparison. | A forecast/result/xG summary is immediately relevant. Use club comparisons before investing in individual player data. |
| Twenty3's [20 December 2024 publishing showcase](https://www.twenty3.sport/news/showcase-how-our-toolbox-graphics-were-utilised-in-2024) documents Squawka prediction videos, Sky Sports weekly debriefs and social match-centre graphics. | Reusable graphics across articles, video and social; weekly editorial packages. | One source dataset feeding a web report, short recap and image export. A weekly recap is a useful editorial rhythm to test. |
| Markstats' official Telegram [field-tilt explanation](https://t.me/markstats/428) and [retrospective shot-based outcome simulation](https://t.me/markstats/441), February 2021, show how definitions accompany advanced reports. A current [match report example](https://t.me/markmatch/3495) uses a concise goals/xG/xThreat caption. | A structured match-stat caption and attached analytical report. | Keep the initial summary short and link to definitions. Add advanced metrics only when the underlying events exist. |

These establish actual formats, not which format produces the most clicks. Direct social samples were small and access-dependent. The lesson is consistent packaging and a specific football question, rather than publishing the entire dashboard in every post.

**Recommended social artifact set**

1. **Match preview:** fixture, kickoff, 1X2, two or three likely scores, forecast origin and a meaningful stakes line.
2. **Full-time report:** score, observed xG where available, pre-match probabilities and the probability assigned to the observed win/draw/loss outcome.
3. **Race movers:** the largest title/top-four/relegation or UCL-stage changes over a stated round or date interval, in percentage points.
4. **Weekly power ranking:** rating and rank movement, plus attack/defence change. Publish as a compact list or carousel.
5. **Weekend review:** most surprising result under the prior forecast, biggest race change and one club trend, with links to the underlying evidence.
6. **Later, shot report:** shot map and cumulative xG timeline from the same shot feed.

Each artifact should include fixture/competition, date, source, forecast origin where applicable, an accessible text equivalent and a link to the relevant report. Exporting cards is a product feature; posting them to social accounts is a separate action.

**3. What Floodlight already supports**

The implementation already contains match 1X2, likely scorelines, BTTS, over 2.5, pre-match expected goal rates, observed Understat match-total xG, form, home/away goal and xG summaries, projected points with an 80% simulation range, final-position distributions, season-race history, domestic and UCL league-phase result-conditioned stakes including effects on other clubs, UCL stage chances and an illustrative bracket, common-scale club ratings including UCL clubs outside the five leagues, weekly movers and an attack/defence scatter plot.

These should be improved or repackaged rather than counted as new features. The club page also already lists its next fixtures: a fixture-difficulty feature would add difficulty and expected-points context to that list.

Two implementation details matter for the recommendations:

- `season_match_forecasts()` reconstructs played-match forecasts at the beginning of their match day using prior results. This supports retrospective evaluation under its recorded assumptions. It does not by itself prove those exact numbers were published before kickoff. A public receipt should use a saved published forecast where one exists; otherwise label it as reconstructed. Preserve actual publications prospectively.
- Competition history stores rounded chance series and can revise its latest point when no new results arrive. It is useful for trends and interval changes, but is not an immutable archive of every publication or a per-match causal explanation. Weekly rating freezes likewise do not identify one match's effect.

**4. Ranked additions that fit the current project**

Priority reflects fit, usefulness and dependency size; it is a product recommendation, not a calendar estimate. “Existing data” means no new provider, not necessarily no exporter or persistence changes.

| Rank | Feature / graph | Concrete scope and benefit | Data and effort |
| --- | --- | --- | --- |
| **1** | **Dedicated post-match report** | Stable fixture link with score, preserved/reconstructed pre-match 1X2, probability of the observed win/draw/loss outcome, scoring expectation, observed xG and links to both clubs. Gives a reason to visit after full time. | Existing fields; modest page work. Prospective receipt persistence is additional exporter/archive work. |
| **2** | **Round recap and race-movers board** | Sorted diverging bars showing the largest changes in title/top-four/relegation or UCL stage chances. Include affected rivals, not just the teams that played. | Existing history; modest aggregation. State interval and rounding; use finer saved values for close comparisons. |
| **3** | **Downloadable preview and recap cards** | Reusable image exports of the match preview, full-time report, race movement and ranking. Gives the project a consistent social artifact. | Existing data and DESIGN tokens; modest rendering/export work. |
| **4** | **Forecast scorecard** | Log loss, Brier, calibration/reliability plot, rolling performance and coverage. Compare with sensible probability baselines, Elo and timestamp-matched market quotes when available. | Existing roadmap item. Needs evaluation exports and provenance handling; moderate work. Sparse market history limits early conclusions. |
| **5** | **Rolling xG form** | Last-five/last-ten league-match xG for and against, plus xG difference. Show actual performance through time beside current strength. | Observed match-total xG already exported; small aggregation. Display coverage and gaps. |
| **6** | **Points against pre-match expectations** | Cumulative actual points and cumulative `3P(win) + P(draw)`; a league ranking of the residual. Answers who has exceeded the model's expectations. | Existing prior-only match probabilities; small aggregation. Separate published and reconstructed series. This is not shot-based xPts. |
| **7** | **Next-five difficulty and expected points** | Extend the existing fixture list with venue, opponent strength, per-match expected points and a five-match total. | Existing ratings, fixtures and 1X2; modest UI/aggregation. Keep opponent quality distinct from the club's own chance of winning. |
| **8** | **UCL match stakes — completed** | Top-eight/top-24 and trophy chances under home win/draw/away win in the league phase. | Implemented on `main` before this document was published; reuse in reports and cards. |
| **9** | **Rating-history and club comparison** | Weekly rating/attack/defence trends, with two-club comparison and absolute rating changes as well as rank changes. | Existing weekly history; modest work. The ranking already exposes UCL clubs outside the five leagues. |
| **10** | **Annotated race history** | Click a substantial change to see the results included in that interval and the before/after chances. | Existing matches/history; modest work. “Changed after this round” is supportable; exact single-match attribution requires a separate calculation. |
| **11** | **Match importance explorer** | Sort upcoming games by the conditional range of a selected season chance. Include games involving rivals. | Reuses existing domestic and UCL stakes. Keep simulation-count and noise filters. |
| **12** | **Favorites and useful fixture filters** | Pin clubs locally; filter for their games, high-stakes matches, balanced contests or high expected goal totals. | Existing data; small client-side addition. No account system needed for an initial version. |

Opta's [next-five difficulty article](https://theanalyst.com/articles/premier-league-fixture-difficulty-hardest-next-five-games-october-november-2026) is a concrete reference for item 7. Its [results-versus-difficulty article](https://theanalyst.com/articles/premier-league-results-vs-fixture-difficulty-stats) explains why shot-based retrospective xPts is a different quantity from item 6.

**Suggested post-match report layout**

1. Final score, competition and kickoff; final/result-pending status.
2. The forecast made before the match: three outcome probabilities, origin and published/reconstructed label.
3. Scoring expectation versus goals and observed shot-xG, with clear metric labels.
4. The probability the forecast assigned to the observed win/draw/loss outcome; one factual takeaway. Keep this distinct from the probability of the exact final score.
5. Season chances before and after the stated refresh interval, with rivals where relevant.
6. Links to club profiles, methodology and the forecast record.

Illustrative copy, with invented values: “The away win had a 19% pre-match probability. The match finished 0–1; observed shot-xG was 1.6–0.8. The home club's title chance fell from 41% to 34% across the weekend's refreshes.” This makes the observation clear without calling the result impossible, claiming the losing team deserved to win or assigning the entire title change to that fixture.

**5. Further ideas, with their actual dependencies**

| Feature / graph | Why it might fit | Dependency and priority |
| --- | --- | --- |
| Full scoreline heatmap | Reveals uncertainty hidden by one score pick. | Export the complete model score distribution, consistent with blended 1X2. The current list of top scores is insufficient. Good second-stage addition. |
| Final-points histogram | Shows skew and multiple plausible outcomes beyond the existing 10th–90th range. | Export histogram bins from simulations; do not infer a distribution from two quantiles. Optional. |
| “Finish above a rival” probability | A direct fan question for derbies and races. | Joint simulation outcomes; cannot recover from two marginal finish distributions alone. Good targeted simulation extension. |
| Points-threshold probabilities | Chance of reaching a specified points total. | Additional simulation summary. Do not call a historically typical threshold a guaranteed qualification requirement. Optional. |
| Limited what-if scenarios | Let a reader choose one result and inspect changed season chances. | Existing domestic and UCL league-phase conditional stakes cover one-result cases. Multiple simultaneous results require new offline scenario calculations; do not reimplement the model in the browser. |
| Preseason versus current outlook | Shows how expectations evolved over a season. | Genuine saved preseason snapshots or explicitly labelled reconstructions. Good once the archive is dependable. |
| Team performance table | Actual points, observed xG difference, forecast strength and projected finish in one compact view. | Existing fields/aggregation; keep column definitions distinct. Good alternative view rather than a new model. |
| Goals minus xG comparison | Highlights finishing and concession differences over a stated period. | Existing goals/xG, matched coverage. Useful descriptive chart; not proof of luck or repeatable skill. |
| npxG trends and open-play/set-piece splits | Adds context when penalties or restarts dominate. | Some npxG/PPDA values may exist in cached source payloads, but are not normalized/exported today. Inspect coverage and definitions; set-piece splits need suitable shot/event data. |
| Model versus market chart | Shows disagreement in 1X2 and evaluates both on the same matches. | Dated archived quotes, fixture matching, same origin/horizon, coverage and margin removal. Good later scorecard extension; disagreement is not proof of betting value. |
| **Shot map** | Shows where chances came from, their quality and whether they became goals. | New individual-shot ingestion: coordinates, xG, time, outcome and fixture mapping. Highest-priority external-data extension. |
| **Cumulative xG timeline** | Shows when chances occurred and whether chance creation was sustained or concentrated. | Individual-shot xG and times; goal/card markers need events. Build alongside shot maps from the same feed. |
| Shot-quality distribution | Separates many low-quality attempts from a few large chances. | Same shot feed; explicit bins or a shot list. Useful small companion chart. |
| Retrospective shot-based result chances / xPts | Summarises alternative scoring outcomes from the observed chances. | Individual-shot xG and an explicit replay method. Label retrospective and acknowledge game-state/rebound assumptions. |
| First-half/second-half and 11v11 splits | Adds context around red cards, goals and tactical changes. | Shot times and relevant match events; coverage required. Good after reliable shot ingestion. |
| Passing networks and pass maps | Explains player involvement and connections. | Pass events, locations, recipients, lineups/substitutions and consistent time windows. A larger second data step. |
| Field tilt / territory | Helps distinguish possession from attacking territory. | Defined final-third touches or passes with locations. Match possession percentage alone cannot supply it. |
| xT, OBV or possession-value timelines | Describes threat from actions that do not end in shots. | Rich event feed plus a named, documented model or licensed metric. Later specialist feature. |
| Player percentile bars / radars | Useful for scouting and player comparison. | Minutes, positions and a sufficiently complete player dataset; thoughtful comparison groups. Lower fit until player work is active. |
| Team/player of the week | Familiar social and editorial format. | Reliable player-match statistics and an explicit selection/rating rule. Do club movers first with existing data. |
| Goalkeeper xGOT / goals-prevented analysis | Adds a specific post-match explanation. | Post-shot xG and keeper-shot attribution. Ordinary shot-xG does not establish goalkeeper shot-stopping value. |
| Lineup / absence context | Important information around a forecast and a future model input. | Reliable timed player, injury, suspension and lineup feed. A lineup card does not itself justify a calibrated probability adjustment. |
| Live scores, momentum and in-play probabilities | Strong matchday utility. | Live ingestion, event freshness and a validated in-play model. Poor near-term fit with daily refresh. |
| Historical head-to-head strip | Familiar preview context. | Existing results may support it, but offers less new value than schedule/strength context. Keep the currently disabled H2H model adjustment unchanged. |

For chart choices, prefer common-scale position/length for comparisons, a line for a time series, diverging bars for change and an actual histogram for a distribution. These follow Munzner's expressiveness/effectiveness principles and the perceptual ranking discussed in [her visualization teaching material](https://www.cs.ubc.ca/~tmm/talks/minicourse14/vad17canberra-afternoon-4x4.pdf). The recommendation is to use these simple charts inside Floodlight's existing design, with direct labels and redundant symbols/dash patterns. Player radars are a recognised reference format, but aligned percentile bars are easier to compare precisely.

**6. Data decisions that determine what is feasible**

**Start with existing data.** Current published match JSON is enough for the first post-match summary, rolling league xG and points-versus-prior-expectation charts. Current competition history and weekly rating snapshots support recaps and trends. New derived exports should pass through `scripts/build_site_data.py` and the existing contract, preserving retained-file timestamps and missing-value behaviour.

**Separate the three meanings of expected goals/points.** Pre-match goal rates predict scoring before the match. Observed shot-xG measures the quality of chances actually taken. Expected final points is the season projection. Additionally, pre-match expected points is `3P(win) + P(draw)`, while shot-based post-match xPts is retrospective. The existing table field `xpts` means projected final points; it should not silently be reused for either new quantity.

**Get shots before buying a complete analytics stack.** One suitable shot feed can unlock maps, timelines and shot-quality summaries. Passing networks, field tilt and action-value models need additional event types. Hudl's [shot-map help](https://hudl.my.site.com/support/s/article/match-shot-map-statsbomb?language=en_US&topic=Statsbomb_Live) illustrates the shot properties and filters involved. Twenty3's [2021 xG-timeline explanation](https://www.twenty3.sport/news/twenty3-introducing-our-xg-timelines-visualisations) describes a per-shot chronological report. StatsBomb's [passing-network explanation](https://blogarchive.statsbomb.com/articles/soccer/explaining-xgchain-passing-networks/) shows why full passing analysis is a further step and why average locations need context.

**Do not manufacture momentum from aggregate statistics.** Opta's [2021 explanation](https://theanalyst.com/articles/what-is-match-momentum) uses on-ball actions and possession value; it is not a graph of possession percentage. StatsBomb's [OBV explanation](https://blogarchive.statsbomb.com/news/introducing-on-ball-value-obv/) describes another model. These and xT are related concepts with different definitions, not interchangeable labels for one metric.

**Treat sites as references and data feeds as a separate decision.** FotMob's [published terms](https://www.fotmob.com/tos.txt) prohibit scraping and redistribution without consent. Understat's existing unofficial integration does not establish permission or long-term coverage for a new shot-data product. Check permitted display, historical storage and derived image publication for any proposed feed.

**Existing-provider upgrades can add context but do not guarantee shots.** The current [football-data.org pricing page](https://www.football-data.org/pricing) lists lineups/substitutions in paid packages and aggregate statistics as an add-on. Its [match schema](https://docs.football-data.org/general/v4/match.html) includes formations, events and box-score statistics. This is a plausible route to richer summaries; it is not evidence of a per-shot coordinate/xG feed. Sportmonks advertises an [xG add-on](https://www.sportmonks.com/football-api/xg-data/), but its own [event-data explanation](https://www.sportmonks.com/blogs/modeling-expected-goals-xg-from-match-event-data/) says standard events do not return per-shot coordinates. Verify exact payloads and competition coverage before selecting a provider for shot maps.

**Use open data to prototype, with its actual limits.** [Hudl/StatsBomb Open Data](https://github.com/hudl/open-data) supplies selected competitions, seasons and matches, with events/lineups and selected 360 data. It is useful for experimenting with charts; it is not a dependable complete live feed for the current five leagues and UCL. Follow its attribution and licence terms.

**Make forecast evaluation honest.** Show prospective published forecasts separately from reconstructed replays. A naive home-result baseline must have a sensible probability distribution to be scored with log loss; a hard 100% home pick produces infinite loss on other outcomes. Use a defined prior-only league-frequency baseline and Elo, then compare the market on matched fixtures and common cutoffs. Include sample sizes and uncertainty, avoid overlapping-window independence claims and retain the qualification that calibrated historical seasons are not independent holdouts. Domestic site forecasts do not use the direct odds blend; UCL strengths already incorporate archived market evidence, so their market comparison is not independent.

**Keep the football meanings precise.** Show chance changes in percentage points. Do not infer certainty from zero observed successes in a finite simulation. Separate a 90-minute UCL result probability from advancement through a tie. Continue to label domestic finish bands as positions rather than guaranteed qualification or relegation. Display xG coverage rather than treating missing matches as zero. Use identical data definitions and comparable scales across each family of social cards.

**7. Recommended sequence**

**First release: make the existing forecasts useful after the match.** Build the focused match report and prospective publication receipts, round race movers and two image templates: preview and full time. Add rolling xG and points-versus-pre-match-expectation views. These largely reuse today's data and make a coherent user journey.

**Next: explain the season and demonstrate forecast quality.** Complete the already-planned scorecard, add the next-five difficulty context, weekly rating trends and annotated race history, and build on the existing domestic/UCL stakes and full club ranking. Prioritize correct origins, coverage and matched comparisons over adding more prediction outputs.

**Then: one deliberate shot-data expansion.** Verify source rights, current domestic/UCL coverage and representative payloads. Add shot map and xG timeline together, followed by selected chronological/game-state breakdowns. Decide on passing networks and player features only after these prove useful.

The proposed positioning is: **European football forecasts with a visible record, clear match stakes and an explanation of how results change the race.** That builds directly on Floodlight's existing model and dated outputs. A large player database, broad betting markets and a live match engine can wait for a specific need and a suitable data source.
