# Backtest data and engine contract

Tasks 3–5 of the [Backtest plan](backtest-plan-2026-10-24.md). Version 1 covers domestic 90-minute 1X2 bets. Historical-price publication was authorized on 26 October 2026; [ADR 0004](adr/0004-backtest-deployment-switch.md) replaces the original D1 safeguards.

## Season files

One `<season>.json` per season start year. The envelope contains `version: 1`, `season`, `generated_at`, `calibration_version`, `columns`, `coverage`, `provenance` and `parity`. `columns` is an object of equal-length arrays, one value per forecast row:

| Column | Value |
| --- | --- |
| `id` | football-data.org fixture ID or null; only known IDs may link to match pages |
| `comp` | `PL`, `PD`, `BL1`, `SA` or `FL1` |
| `kickoff` | ISO UTC date/time; provenance states historical noon anchors |
| `home`, `away` | Display names |
| `home_key`, `away_key` | The model's normalized team identities, also used for deterministic sorting |
| `home_id`, `away_id` | football-data.org club IDs or null |
| `matchday` | Known provider matchday or null; never infer an official round from CSV row order |
| `forecast` | `replayed` or `published` |
| `at` | Forecast origin, strictly before kickoff |
| `score` | Home/away 90-minute goals |
| `xg` | Observed home/away Understat xG or null; descriptive, never a selection condition |
| `p` | Standalone forecast home/draw/away triple; normalize receipt-rounding drift when calculating |
| `elo` | Standalone Elo home/draw/away triple or null |
| `exp` | Pre-match home/away expected goals from the blended score distribution, or null |
| `stakes` | Whether pre-match evidence carries the site's Stakes tag, or null if unavailable |
| `rating_gap` | Pre-match home-minus-away European strength rating, or null |
| `prices` | Book-keyed objects, each with `pre` and `close`: a complete raw decimal H/D/A triple or null |

Book keys include `avg`, `max`, `bet365`, `pinnacle`, `betfair`, `betfair_exchange`, `betfred`, `betvictor`, `bwin`, `paddypower`, `skybet`, `williamhill`, `ladbrokes`, `interwetten`, `1xbet` and `betmgm` where covered. Labels follow the [provider's column definitions](https://www.football-data.co.uk/notes.txt): `BFD` is Betfred and `BW` is Bet&Win/bwin, rather than the Betfair/Betway labels in the initial plan. Average/maximum are aggregate benchmarks. No bookmaker or timing falls back to another. Missing fields stay null. Published rows permit closing-price execution only; receipts without a source-price join remain present with null prices. Neither observed xG nor closing prices may enter a pre-closing rule.

Provider IDs and names are retrospective display/link enrichment, not inputs to forecasts. A row is unique by competition, season, home/away fixture and forecast kind. Historical unavailable Stakes/rating/round evidence remains unknown, with coverage stated; conditions requiring it exclude unknowns.

## Engine interface

`site/assets/backtest-engine.js` exports `decodeSeason(file)`, `normalizeStrategy(strategy)`, `runBacktest(filesOrRows, strategy, options)`, `encodeStrategy(strategy)` and `decodeStrategy(hash)`. It has no DOM or network access. `runBacktest` accepts season envelopes or decoded rows. Options default to `{bootstrap: 2000, seed: 7}`.

The strategy follows the plan's v1 JSON shape. `execution.book` defaults to `bet365`, timing to `pre`; `avg` and `max` are canonical keys (`average`/`best` accepted as aliases). `rule.pick` accepts `model_favourite`, `market_favourite`, `edge`, `disagreement` and `home`/`draw`/`away`; aliases `model` and `market` are accepted. All conditions use the selected outcome and execute with AND. Operators are `>=`, `>`, `<=`, `<`, `==`, `!=` and `between` (inclusive). Unsupported fields/operators reject the strategy; unknown evidence fails a condition. `gap` is model minus proportionally de-margined selected-book probability on the 0–1 scale. `xg_diff` is selection-side minus opponent expected goals (draw uses the absolute home/away difference); `xg_total` is their sum. `rating_gap` reverses for away and uses absolute difference for draw. `elo_agrees` compares the selection with Elo's argmax.

Universe filters cover competitions, season start years, team include/exclude IDs, venue of the included team, optional betting-on-that-team restriction (`team_side: true`), matchday range, months (1–12), weekdays (UTC, Monday=0), and `forecast` (default `replayed`). Missing IDs cannot satisfy a requested ID filter. An absent matchday range or the full `[1,38]` range imposes no round restriction; narrower ranges require known round evidence. `weekday: "midweek"` means Tuesday–Thursday; weekday arrays are also accepted. Unrestricted team/season/competition lists are empty arrays.

Staking methods are `flat`, `fraction`, `probability`, `edge`, `kelly` and `to_win`. `stake.unit` defaults to 1, `stake.fraction` to 0.25 for Kelly (0.01 for fixed fraction), `stake.cap` to 0.03 for bankroll-relative methods, `stake.daily_cap` to 1 and `stake.trust` to 1. Probability stakes are `unit*p/0.5` or explicit `{min,max,stake}` probability bands; edge stakes are `unit*max(edge,0)/0.05`; to-win stakes are `unit/(price-1)`. Flat/probability/edge/to-win are unit-return references, without a finite-bankroll constraint; fraction/Kelly use a bankroll reset to `strategy.bankroll` (default 100) per season. Kelly rejects nonpositive edges after an optional trust blend with the contemporaneous de-margined market. Commission defaults to 2% for Betfair Exchange and zero for sportsbooks, applies only to positive net returns, and reduces the effective price used for edge/Kelly.

Pre-closing stakes share the starting bankroll of their forecast-origin date; closing stakes share that of their UTC match day. Bankroll-relative batches scale proportionally when exposure exceeds the available balance or daily cap. Previously unsettled bets may not finance new ones. Same-batch outcomes never resize stakes. Keep commission-adjusted expected return for selection and sizing; CLV compares raw entry and closing prices.

The result has `strategy`, `coverage`, `summary`, `bets`, `bankroll` and `breakdowns`. Summary keys match the Python reference: `bets`, `staked`, `profit`, `roi`, `roi_low`, `roi_high`, `clusters`, `strike_rate`, `implied_strike_rate`, `average_price`, `mean_edge`, `clv_bets`, `clv`, `max_drawdown_units`, `longest_losing_run`. No-bet rates/losses are null, counts and totals zero. Coverage distinguishes input rows, universe matches, fully priced matches, selection exclusions, condition exclusions, zero stakes and missing-price voids. Breakdowns group by season, competition, team, decimal price band and UTC month, with the same bootstrap settings; fewer than two match dates yield an unavailable interval. `options.breakdowns: false` skips subgroup calculations for parity-only checks.

ROI intervals resample UTC match dates with all competitions together, conditional on realized stakes. Use the reference's Mulberry32 sequence, row-major draws and linearly interpolated 2.5/97.5 percentiles. Ties resolve H/D/A; fixture sequence is kickoff, competition (mapped to Python league code), then normalized home name. Daily drawdown and losing runs reset per season. Closing runs have no CLV. Pre CLV is the unweighted mean entry/close minus one on covered selections.

`parity` contains `{strategy, options, summary}` entries computed by Python for the six fixed selectors under flat and quarter-Kelly stakes at average pre-closing prices. The browser check compares every summary key (nulls/counts exactly, floats within `1e-8`). Committed parity fixtures are synthetic and contain no third-party historical prices. Optional locally built season files can be checked explicitly without publishing them.

URL state is `#backtest/<encodeURIComponent(JSON.stringify(normalizedStrategy))>`. Decode validates the version, values and supported fields; malformed or unsupported state throws an error. Task 5 restores this state in the Backtest view.

## Availability and page

`backtest/index.json` is `{ "version": 1, "seasons": [] }`, with unique integer season start years when files are available. After successful builds, the exporter atomically writes the manifest from the season files in its destination, preserving unchanged bytes and timestamps. The validator checks listed files exist and their seasons match; the page fetches only listed files, caches availability once per page load, and shows an unavailable state on failure without substituting partial results. The optional manifest remains compatible with older datasets.

`ENABLE_BACKTEST=1` is the only deployment switch. Deployment writes `site/assets/features.js` before asset stamping and browser checks; the committed module defaults off. Disabled Backtest links return to Tables, its navigation link stays hidden, and its code, data and worker are not loaded. Scheduled refresh runs the current-season exporter only when enabled, using `--dest` to write into the staged site. Local exports default to `out/backtest/`; initial historical publication uses `--dest site/data/backtest`. Enabling the feature does not require a separate price-publication flag.

The page calls the engine in a module worker (whose URL inherits the stamped entry-module version). It uses 2,000 bootstrap draws and seed 7 for results and the labelled flat-stake market-favourite reference. Probability and gap controls convert display percentages/points to engine fractions; bankroll fractions remain explicitly 0–1. Daily chart values and ledger balances come from the engine's season-reset bankroll paths.
