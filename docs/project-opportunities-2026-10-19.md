# Floodlight: product, model and data opportunities

Research date: **19 October 2026**. This records opportunities beyond the current roadmap, with evidence, dependencies and relative effort. It is a research catalogue, not an implementation commitment or a change to accepted architecture.

The strongest product direction is an interactive guide to a club's season: **what can happen, what would change it, and why the model thinks so**. Floodlight already connects match forecasts, season simulations, European club ratings and a visible forecasting record. Scenarios and explanations could make that foundation more useful to supporters throughout the week.

**Scope and evidence**

The review covered the repository, its experiment reports, the live Tables and Clubs views, competing products, provider documentation and research papers. The earlier [football feature research](football-feature-research-2026-10-14.md) remains a separate record. Dedicated match reports, shot maps, xG timelines, squad views, club characteristics, rating comparisons, race movers, download cards and the scorecard are existing features, rather than new recommendations here.

Competitor features and provider coverage below are based on public interfaces and documentation. Paid feeds were not purchased or independently audited. Advertised coverage does not establish completeness, latency, historical availability or forecast quality. Prices are advertised entry prices checked at the research date; competition limits, billing terms and add-ons can change the total. Research findings motivate local experiments, not claims of gains for Floodlight.

**1. What comparable products demonstrate**

| Product | Evidence | Implication for Floodlight |
| --- | --- | --- |
| [Opta Analyst](https://theanalyst.com/articles/opta-football-predictions) | Match probabilities and season simulations; its [live-probability explanation](https://theanalyst.com/articles/live-win-probability) connects game events with changing outcomes. | Connect the match, its season consequences and an explanation of the change. |
| [ClubElo](https://clubelo.com/Fixtures) | Fixture probabilities and season objectives conditional on a win, draw or loss. | Build an interactive supporter experience around the stakes Floodlight already calculates. |
| [Euro Club Index](https://www.euroclubindex.com/league-odds/) | European ratings, league odds and a dedicated [club comparison](https://www.euroclubindex.com/teams-comparison/) view. Some content is client-rendered. | Use the common European scale to answer concrete matchup questions. |
| [Kickoff.ai](https://kickoff.ai/about) | Dynamic team-strength histories and an accessible explanation of probabilistic forecasting. | Make strength changes and their interpretation easier to explore. |
| [The Football Simulator](https://thefootballsimulator.com/) | Its public site advertises saved club dashboards and advanced counterfactual tools with Pro. These capabilities were not tested behind a subscription. | Give visitors a personal starting point and reasons to explore different futures. |

The proposed position is **forecasts, scenarios, explanations and a visible record**. Other products offer parts of this combination. This review does not establish an exclusive feature gap, comparative accuracy or demand for any particular addition.

**2. Product opportunities**

Effort is relative to the existing project and includes data/export work where needed. It is not a delivery estimate or release sequence. The examples below are hypothetical questions, not current forecasts.

**P1. Multi-match season sandbox — medium to large; existing providers.**

Let visitors choose results for several upcoming fixtures and inspect the resulting table, title race, European-place bands and relegation picture. Questions include “What if we win our next three?”, “What if both contenders draw this weekend?” and “Could we still finish fourth after losing the derby?” Preserve selections in a shareable scenario URL and distinguish the scenario from the published forecast.

Single-fixture stakes are an existing foundation in `src/standing_prediction/stakes.py`. Multiple selections require joint simulation paths or fresh conditioned runs. Filtering a finite archive becomes unreliable for rare combinations; expose the supporting sample or rerun instead. Do not multiply separately exported conditional percentages. Under [ADR 0001](adr/0001-site-model-boundary.md), filtering Python-generated outputs can fit the static site; arbitrary fresh simulations would need a separately chosen execution surface, without duplicating the forecasting model in browser code.

**P2. Explain why a forecast changed — medium; existing providers.**

Extend the current before/after views with a breakdown of points secured by the club, results elsewhere, revised team strengths and changes to European league levels. This would answer “We won, so why did our title chance fall?” or “Did our rating fall because of our match or the league's European results?”

Use controlled reruns with common seeds and an explicit allocation convention. Interacting results and model updates do not have one uniquely correct decomposition. A difference between two daily refreshes is not automatically the effect of one match; describe the allocation without claiming a causal explanation of football performance.

**P3. Champions League path explorer — medium; mostly existing inputs.**

Show likely opponents by round and the chance of winning the trophy conditional on particular pairings. Let visitors inspect how different league-phase positions change their route, the value of bypassing the playoffs and the effect of a favorable or difficult draw. This adds exploration to the existing illustrative bracket.

Reuse the tournament engine's permitted slots, observed pairings and inherited home priority. Before a draw, average over legal draws; after it, condition on the official pairing at its availability time. Label a selected path as hypothetical rather than the model's single predicted bracket. Sparse conditional paths need the same sample-size care as P1.

**P4. Points targets and clinching dates — medium; additional simulation outputs.**

Show how a club's chances differ across finishing totals, alongside distributions for the title-winning total, fourth-place threshold and survival threshold. Later, show distributions of dates when a title, place or safety is secured. Questions include “What does 70 points buy us?” and “How soon could we secure safety?”

Use joint simulations when conditioning on a club's own points; an independently sampled league threshold is not equivalent. Distinguish a simulated chance from a mathematical guarantee, and preserve league tie-breakers. Clinching dates require intermediate tables and fixture dates, beyond the current final-position summaries. Qualification and playoff outcomes depend on P7 and additional competition coverage.

**P5. European matchup laboratory — small to medium; existing providers.**

Choose two rated clubs and a home, away or neutral venue, then inspect win/draw/loss probabilities, expected goals and a score distribution. “Barcelona against Brighton on a neutral pitch” is a concrete use of the European strength model. Today's rating comparison would remain useful context around the hypothetical match.

Generate probabilities with the connected model, rather than converting the difference between displayed ratings into odds. A hypothetical fixture must not acquire a real kickoff or published pre-match receipt. Precomputed Python matchup outputs could serve an initial static-site version; show the underlying run date and sparse-country coverage limits.

**P6. My Floodlight — small for browser preferences; existing providers.**

Save a favorite club and open on its next match, meaningful races, recent changes and other fixtures that affect its prospects. A “Who should I support tonight?” view could personalize the existing third-party stakes. Add an optional fixture-calendar export and a concise club digest assembled from supported changes.

Preferences can initially stay in the browser without accounts. Distinguish a since-last-visit comparison from the existing Monday baseline, and retain the comparison dates. Freshness must follow the selected competition. Email, push delivery and account synchronization would be separate capabilities; a digest view does not require sending messages.

**P7. Actual European qualification paths — large; additional competitions and rules.**

Forecast entry to the Champions League, Europa League and Conference League rather than equating fixed league-position bands with qualification. Domestic cups, European titleholders, access-list rules and European Performance Spots can change the available places. [UEFA's explanation](https://www.uefa.com/uefachampionsleague/news/02a2-1fdbe9a25733-8d37ff5f9226-1000--2026-27-uefa-cham/) confirms that performance places depend on associations' collective European results.

A full version would connect domestic leagues and cups with all three European tournaments, using the relevant season's regulations. The current EL/ECL result and odds archives are useful inputs, not complete tournament or qualification simulators. Keep present finish-band labels until this broader calculation is implemented. The same distinction applies to actual relegation where a playoff separates league position from survival.

**P8. Season time machine — medium; existing dated foundation.**

Choose a date and inspect the whole football picture as it stood then: ratings, projected tables, match expectations and competition chances. Connect the existing `--as-of` behavior and dated histories into one browsing experience, with links back to the present and comparisons between origins.

Saved publications and reconstructed views retain separate labels. Retrospective runs cannot reconstruct unavailable publication times, historical postponement announcements or undated sanctions exactly. Preserve immutable published forecasts rather than replacing them with a newer reconstruction. Start with covered seasons and show gaps explicitly; a date selector does not establish a complete historical archive.

**P9. Tactical matchup reports — small to medium for shots; larger for detailed tactics.**

Compare how upcoming opponents create and concede chances: set pieces, headers, shot locations, shot volume and shot quality. Show the relevant attacking and defensive profiles together. The current club characteristics and shot archive support a useful descriptive version.

Do not turn a descriptive mismatch into a probability adjustment without evaluation. Current profiles are not opponent-adjusted, and their sources have different coverage. Claims about pressing, buildup, passing routes or defensive lines need event or tracking data with appropriate definitions; shots and aggregate possession cannot establish those behaviors by themselves.

**P10. Live race centre — large; in-play model, timely feed and publishing work.**

During simultaneous games, update match probabilities, projected standings and season chances after goals and red cards. Preserve a post-match replay of the moments that changed the race most. This could make Floodlight useful while watching football as well as before and after games.

[Opta's methodology](https://theanalyst.com/articles/live-win-probability) illustrates the relevance of current score, time remaining, red cards, in-game performance and added time. Daily pre-match probabilities and retrospective shot-based chances are different quantities. This addition needs an evaluated in-play model, event timing/correction handling, quotas and a more frequent publishing mechanism. It cannot be delivered by relabeling the current daily forecast as live.

**P11. Probability prediction challenge — medium for a public competition.**

Let supporters submit home/draw/away probabilities and compare their record with Floodlight and defined baselines, using log loss or Brier scores rather than only picked winners. A weekly challenge could make probabilistic forecasting easier to understand and supply a new reason to return.

A public competition needs reliable pre-kickoff submissions, server-side deadlines, persistence and a stated scoring rule. Browser-local entries can support a personal exercise but cannot prove a public record. Any later crowd model needs its own prospective evaluation; collecting predictions does not establish that averaging them beats the current model. No wagering or prizes are required for this idea.

**P12. Embeddable club and race widgets — small to medium for static embeds.**

Offer a compact club outlook, race table or match preview that a writer or supporter site can embed, with a link to the full analysis. Existing download cards remain useful; embeds would add dated, refreshable views for other publications.

Use the same checked exports and definitions as the site, include source/run attribution and preserve retained-data timestamps. Review display and redistribution terms before distributing third-party-derived content externally. A public API, usage guarantees or a paid product would require additional decisions; an embed does not require promising those services.

**3. Model and evaluation opportunities**

These are candidate experiments. They do not authorize changing `calibrated_weights.json`, model defaults or published forecasts. The existing [calibration protocol](../packages/forecast-calibration/README.md), [numerical protection](numerical-protection.md) and experiment history remain applicable.

**M1. Context-adjusted xG — strongest new experimental candidate.**

Whole-match attacking production reflects score and manpower as well as team strength. A side defending a lead behaves differently from one chasing a game. [Skripnikov, Cemek and Gillman (June 2026)](https://journals.sagepub.com/doi/10.1177/22150218261454824) model these contextual effects with minute-level data from the five major leagues. Test whether context-adjusted historical production improves forecasts relative to the current whole-match xG fit.

Audit historical score, red-card timing and exposure coverage first, and fit adjustments on earlier data only. The paper motivates the experiment; it does not demonstrate a gain against Floodlight. This uses the full match with context adjustments and is distinct from the rejected before-first-goal truncation in the [miss report](eleven-season-miss-report.md). Standardization is not a causal reconstruction of the game without a goal or dismissal.

**M2. Consistent xG across more European leagues and cups.**

The connected model currently has domestic xG for the five major leagues while many other clubs depend on goals. A broader feed could improve European match reports and permit a matched forecasting comparison. Sportmonks documents [coverage](https://docs.sportmonks.com/v3/tutorials-and-guides/tutorials/expected/coverage) for all three European competitions and several relevant domestic leagues; its [product page](https://www.sportmonks.com/football-api/xg-data/) dates xG history from 2024 onward.

Inspect representative historical and current payloads before selecting it. Compare on identical clubs, fixtures and origins, recording exclusions and provider differences. Values from different xG models are not interchangeable; test a consistent-provider contender instead of silently appending new values to Understat history. Public coverage claims do not establish that every desired season or fixture is complete.

**M3. Separate chance volume and chance quality.**

Similar xG totals can come from different shot counts and quality distributions. Test whether modeling these components separately adds stable information beyond the existing strengths. [Wheatcroft and Sienkiewicz (2021)](https://arxiv.org/abs/2101.02104) combine shot-count forecasts with team-specific shot success. Existing Understat shots provide a possible modest experiment after checking archive coverage.

The [xG+ preprint, revised January 2026](https://arxiv.org/abs/2512.00203), goes further by modeling whether a shot occurs and its potential quality at possession level. Its proprietary data and richer requirements make it a research reference, not a drop-in improvement. Avoid unstable club/player finishing claims from small shot samples, and compare any contender against today's model on common fixtures.

**M4. A restrained match-context adjustment.**

Candidates include rest differences, minutes across all competitions, recent extra time and travel. Start with a small adjustment around the existing model to test whether those features add information. Use only schedule, minutes and news available at the origin; cover domestic cups and Europe before interpreting a club's apparent rest period.

The [systematic review of congestion and performance](https://pmc.ncbi.nlm.nih.gov/articles/7846542/) reports mixed effects, so a fixed penalty after a midweek European match is not established. A reliable availability feed could improve display without justifying a probability adjustment. More complex learning methods should follow evidence that the features help, rather than being treated as improvements by themselves.

**M5. Provider-aware xG stability checks.**

The [eleven-season miss report](eleven-season-miss-report.md) finds a widening recent gap against Understat xG without a comparable actual-goal deficit, and records differences between fetched xG vintages. Check historical stability and provider vintages before treating that gap as a goal-level error. StatsBomb's [xG explanation](https://statsbomb.com/articles/soccer/upgrading-expected-goals/) also emphasizes that xG depends on the model producing it.

Separate descriptive monitoring from a forecast adjustment. If an adjustment is proposed, estimate it from earlier data and evaluate it on later fixtures; do not choose a goal uplift from the current season's gap. A source or definition change can require a data decision rather than a more complicated football model.

**Evaluation and existing negative findings.** Use identical fixtures and origins, chronological choices, fixed seeds for simulation comparisons, coverage/exclusion reports and paired uncertainty. Judge match forecasts with log loss, Brier scores and calibration; use the relevant position/stage metrics for season changes. Report lead-time differences and retain the distinction between standalone and market-informed forecasts. Seasons that informed global weights or later design choices are not independent overall-model holdouts. The prospective receipt archive becomes more valuable as new matches accumulate.

Keep the [expected-XI](expected-xi-forecast-adjustment.md) and [EA-prior](expected-xi-ea-prior-comparison.md) findings in view: the tested offsets, including confirmed-starter variants, do not establish a deployable forecast gain. [PLAN.md](../PLAN.md) records rejected strength noise, head-to-head and other searches; the [npxG experiment](npxg-penalty-rate.md) found only a small uncertain gain. New information may justify a different experiment, but these results should not be presented as untried opportunities. Dynamic strengths and promoted-team priors are already parked in the [roadmap](../ROADMAP.md), rather than new discoveries here.

**4. Data-source options**

| Source | Potential use | Cost and material limits |
| --- | --- | --- |
| [API-Football](https://www.api-football.com/) | Injuries, confirmed lineups, transfers, match events and more competitions. | Free: 100 requests/day. Pro advertises US$19/month and 7,500/day. All endpoints does not mean complete fixture coverage; inspect [season and fixture availability](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide). |
| [Sportmonks](https://www.sportmonks.com/football-api/plans-pricing/) | Availability data and broader European xG. | Starter begins at EUR29/month for five leagues. Extra leagues and xG add-ons increase the total; six current competitions already exceed five. Confirm a complete quote and representative payloads. |
| [Official FPL public endpoint](https://fantasy.premierleague.com/api/bootstrap-static/) | A low-cost Premier League availability pilot. | The research directly verified `news`, `news_added`, `status` and chance-of-playing fields. PL only; gameweek availability is not a full injury-history service or a guaranteed supported integration. Archive observations if evaluating news retrospectively. |
| [StatsBomb Open Data](https://github.com/hudl/open-data) | Passing, possession-value and selected 360 prototypes. | Selected historical competitions and matches, not a complete ongoing feed. Follow the repository's attribution and usage terms. |
| [Public Wyscout event dataset](https://www.nature.com/articles/s41597-019-0247-7) | A historical laboratory for passing, actions and tactical metrics. | Covers the five major leagues in 2017/18, plus international tournaments. Released under CC BY 4.0; not a current production feed. |
| [SkillCorner Open Data](https://github.com/SkillCorner/opendata) | Tracking visualizations and off-ball movement experiments. | Small A-League match sample and related aggregates, not European production coverage. Tracking includes detection/extrapolation limitations. |
| [The Odds API](https://the-odds-api.com/liveapi/guides/v4/), already integrated | More market benchmarks and dated price histories. | More markets and collection times consume quota; historical access has separate constraints. Preserve observation times and expiry rules. Do not assume desired competition outrights are available. |
| [Commercial Hudl StatsBomb](https://www.hudl.com/en_gb/products/statsbomb) | Detailed event analysis and richer player evaluation. | Contact the provider for scope, history and price. No verified public price was available to recommend here. |

The strongest paid-data investigation is broader European xG: it addresses a current reporting gap and enables M2. Availability data is another useful product investment, with its forecasting value evaluated separately. A trial should check fixture identity, missingness, timing, source definitions, retention and display rights before any integration choice.

**Payload distinctions matter.** Events, xG and shot coordinates are different capabilities. Sportmonks' [event-data article](https://www.sportmonks.com/blogs/modeling-expected-goals-xg-from-match-event-data/) says standard shot events lack per-shot coordinates, even though it offers other xG and positional products. Verify the actual endpoint and sample payload for the intended feature; marketing descriptions do not establish a complete shot or passing feed.

**Existing-source constraints.** The [football-data.co.uk notice](https://football-data.co.uk/data.php) states restrictions on commercial and automated data-training uses, and warns that its Pinnacle odds became unreliable after 23 July 2025. Clarify intended usage before expanding or commercializing that dependency; this is a recorded provider notice, not a legal determination. The warning concerns that source's Pinnacle columns and should not be generalized to separately archived Odds API observations. [Sports Reference's January 2026 announcement](https://www.sports-reference.com/blog/category/expire21d/) records the removal of its provider-supplied advanced football data. FBref's former advanced dataset is not a dependable source for these proposals.

**5. Analysis unlocked by richer events**

Passing networks, progression maps, possession chains and player contribution beyond goals and assists are plausible extensions once event coverage exists. [Expected Threat (xT)](https://socceraction.readthedocs.io/en/stable/documentation/valuing_actions/xT.html) values locations and successful ball progression; [VAEP](https://socceraction.readthedocs.io/en/latest/documentation/valuing_actions/vaep.html) values actions through changes in scoring and conceding probabilities. They offer established starting points rather than requiring a new proprietary metric immediately.

Prototype on suitable open data, stating its historical/sample scope. These action-value measures are not automatically player effects on match-winning chances. Continuous movement, defensive-line height and off-ball behavior require appropriate positional coverage; selected 360 snapshots and continuous tracking are different observations. Keep descriptive analysis separate from changes to the match model until its forecast value is evaluated.

**6. UI opportunities within the scoreboard identity**

Preserve the dark scoreboard treatment, typography, bulbs and compact ruled presentation in [DESIGN.md](../DESIGN.md). The live Tables and Arsenal views suggest improving discovery and interpretation rather than replacing the visual system.

| Opportunity | Concrete scope and dependency |
| --- | --- |
| Global search | Find clubs, players and fixtures from one keyboard-accessible control. Use existing exports; define which historical fixtures and player identities are searchable. |
| Compact returning-user view | Prioritize the selected club's next match and meaningful race, with the full data still accessible. Pair with P6's browser preferences. |
| Race selection near the top | Let visitors foreground Europe or survival when the title is nearly settled. Preserve the current definitions of finish bands until P7 exists. |
| Since-last-visit explanation | Link meaningful changes to supporting matches and forecast origins. Distinguish the visitor's baseline from Monday movement and use P2 for attributed explanations. |
| Linked charts | Selecting a match highlights it across rating history, rolling performance and race chances. Respect different snapshot frequencies and missing data. |
| Shareable scenario URLs | Preserve selected outcomes and the baseline forecast reference for P1/P3. Warn when an old scenario uses an unavailable baseline rather than silently applying today's data. |
| Strength versus event chance | Make a club-strength score and its title probability visibly distinct; they measure different quantities even when both appear near a percent sign. |
| Freshness and coverage in context | Show the date and source coverage beside the affected competition or analysis, including retained forecasts after a failed refresh. |

Browser preferences, search, comparison controls and additional Python-generated views can retain the current static architecture. Arbitrary simulations, live updates, public submissions and delivery notifications need separate execution or persistence decisions. This catalogue does not supersede the accepted [site/model boundary](adr/0001-site-model-boundary.md) or [browser-check decision](adr/0002-site-browser-checks.md).

**7. Strongest opportunities by purpose**

| Purpose | Most promising opportunity | Main dependency |
| --- | --- | --- |
| Give Floodlight a memorable signature | P1: multi-match season scenarios | Joint paths or conditioned simulations with sample support |
| Make it useful every day | P6: My Floodlight and results elsewhere that matter | Browser preferences and existing stakes |
| Explain the forecasts | P2: why probabilities changed | Controlled reruns and a stated attribution convention |
| Pursue a substantive model experiment | M1: context-adjusted xG | Historical event timing and exposure coverage |
| Investigate a paid source | M2: consistent, broader European xG | Verified payloads, coverage, history and price |
| Build a larger football product | P7/P10: qualification paths and a live race centre | More competition rules, timely data and execution support |

These are choices to evaluate, not an ordered backlog. P1 is the clearest candidate for a signature feature because it lets supporters explore the questions that brought them to Floodlight; M1 is the clearest new modeling study. Neither requires assuming that every additional statistic or a more complex model will improve forecasts.
