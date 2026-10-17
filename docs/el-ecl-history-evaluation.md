# Europa and Conference League history replay

17 October 2026. [Task A](model-plan-2026-10-16.md); [machine-readable results](el-ecl-history-evaluation.json).

**Decision: keep ESPN behind `--european-history both`; openfootball remains the default.**

The full variant leaves 2024/25 unchanged but raises 2025/26 Champions League log loss by **0.000560** (clustered SE **0.003522**), while lowering covered EL/ECL log loss by **0.006061** (SE **0.010266**). Both changes are within noise, and the strict no-worse-in-both-seasons point-estimate gate fails. The published/default forecast therefore stays unchanged.

## Protocol

The same nine origins per season as `football-ucl --evaluate`: after MD2, MD4, MD6 and MD8, then before each knockout round. Seed 7; 2,000 simulations per origin. Match scores use each origin until the next, with the final interval ending after the Champions League final. Every variant has identical scored fixtures and origins, checked by one-to-one fixture joins. EL/ECL scoring always uses the full target set, regardless of the training variant; both clubs must have domestic history available at that origin. Two legs count separately.

`none` removes all EL/ECL fitting rows; `openfootball` is the existing 2024/25 supplement; `both` retains that supplement and adds ESPN for 2025/26 onward. The existing openfootball European-only club fallbacks are unchanged, preserving today's comparator. New ESPN rows require covered domestic histories. ESPN and openfootball are partitioned by season, so no fixture can enter from both sources.

The fixed global calibration, offset ridge 1, club ridge 16, decay and xG settings are unchanged. No settings were tuned for this comparison. These seasons influenced the existing calibration and Plan D choices; the integration gate is applied retrospectively after seeing these results. This is not an independent or prospective holdout.

Historical replays have no eligible archived Champions League market quotes. Today's comparison retains all 18 eligible CL quotes at weight 10 and shift ridge 5, with no direct fixture-odds blend. EL/ECL prices remain unused for the 10 December recheck.

## Match scores and position RPS

Lower is better. Position RPS averages MD2, MD4 and MD6, when league positions remain uncertain.

| Season | History | CL matches | CL log loss | EL/ECL matches | EL/ECL log loss | Position RPS |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2024/25 | none | 153 | 0.908125 | 123 | 1.046213 | 0.082887 |
| 2024/25 | openfootball | 153 | 0.901217 | 123 | 1.029769 | 0.082754 |
| 2024/25 | both | 153 | 0.901217 | 123 | 1.029769 | 0.082754 |
| 2025/26 | none | 153 | 0.931536 | 137 | 0.961058 | 0.089409 |
| 2025/26 | openfootball | 153 | 0.916019 | 137 | 0.941233 | 0.084557 |
| 2025/26 | both | 153 | 0.916578 | 137 | 0.935172 | 0.083413 |

EL and ECL separately (log loss):

| Season | Cup | Matches | None | Openfootball | Both |
| --- | --- | ---: | ---: | ---: | ---: |
| 2024 | EL | 101 | 1.082381 | 1.046290 | 1.046290 |
| 2024 | ECL | 22 | 0.880170 | 0.953923 | 0.953923 |
| 2025 | EL | 100 | 1.006187 | 0.992113 | 0.988215 |
| 2025 | ECL | 37 | 0.839091 | 0.803719 | 0.791813 |

The covered-club totals above include same-country European fixtures. Restricting to different domestic leagues gives 122 matches in 2024/25 and 134 in 2025/26; the latter improves from 0.940415 to 0.934312 with ESPN. The integration decision is unchanged.

## Stage Brier

Means over all nine existing origins per season, including already-resolved stages (whose errors are zero). These are comparisons at equal horizons; do not interpret the diluted averages as prospective stage calibration.

| Season | History | Playoffs | Round of 16 | Quarterfinal | Semifinal | Final | Winner |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024 | none | 0.056533 | 0.086924 | 0.075319 | 0.054218 | 0.046710 | 0.025969 |
| 2024 | openfootball | 0.055271 | 0.085697 | 0.075195 | 0.054197 | 0.047171 | 0.026690 |
| 2024 | both | 0.055271 | 0.085697 | 0.075195 | 0.054197 | 0.047171 | 0.026690 |
| 2025 | none | 0.079839 | 0.066473 | 0.055209 | 0.039258 | 0.021734 | 0.023108 |
| 2025 | openfootball | 0.079243 | 0.067372 | 0.056564 | 0.039636 | 0.022224 | 0.023930 |
| 2025 | both | 0.078052 | 0.066103 | 0.055207 | 0.039965 | 0.023187 | 0.024410 |

## Paired uncertainty

Differences are variant minus openfootball. Standard errors cluster the paired fixture-loss differences by season and replay origin, because fixtures in an interval share one fit. Only origins with scored fixtures enter the standard error: eight per season (16 pooled) for CL, and seven/eight (15 pooled) for EL/ECL. These standard errors are descriptive, with substantial uncertainty.

| Target | Variant | Season | Difference | Clustered SE | Matches | Clusters |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| matches | none | 2024 | +0.006908 | 0.004967 | 153 | 8 |
| matches | none | 2025 | +0.015517 | 0.011626 | 153 | 8 |
| matches | none | pooled | +0.011213 | 0.006444 | 306 | 16 |
| matches | both | 2024 | +0.000000 | 0.000000 | 153 | 8 |
| matches | both | 2025 | +0.000560 | 0.003522 | 153 | 8 |
| matches | both | pooled | +0.000280 | 0.001699 | 306 | 16 |
| cross_matches | none | 2024 | +0.016444 | 0.014469 | 123 | 7 |
| cross_matches | none | 2025 | +0.019825 | 0.009669 | 137 | 8 |
| cross_matches | none | pooled | +0.018226 | 0.008230 | 260 | 15 |
| cross_matches | both | 2024 | +0.000000 | 0.000000 | 123 | 7 |
| cross_matches | both | 2025 | -0.006061 | 0.010266 | 137 | 8 |
| cross_matches | both | pooled | -0.003194 | 0.005456 | 260 | 15 |

## League offsets at the latest replay origins

Offsets are log goal-rate contrasts relative to the Premier League, whose value is subtracted from every league for comparability. All fitted leagues are retained in the JSON, including European-only fallbacks. Latest origins are 2025-05-31T00:00:00+00:00 and 2026-05-30T00:00:00+00:00.

| League | 2024 none | 2024 openfootball | 2024 both | 2025 none | 2025 openfootball | 2025 both |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AM1 | — | -0.9088 | -0.9088 | — | -0.6702 | -0.7053 |
| AUT | -0.8279 | -0.8799 | -0.8799 | -0.7184 | -0.7533 | -0.7881 |
| AZ1 | -0.4955 | -1.1364 | -1.1364 | -0.8553 | -0.9287 | -0.9673 |
| B1 | -0.5344 | -0.6165 | -0.6165 | -0.5706 | -0.5399 | -0.5344 |
| BA1 | — | -0.6758 | -0.6758 | — | -0.6065 | -0.6471 |
| BL1 | -0.2471 | -0.3348 | -0.3348 | -0.2958 | -0.3037 | -0.2988 |
| BUL | — | -0.5919 | -0.5919 | — | -0.5994 | -0.6390 |
| BY1 | — | -0.9317 | -0.9317 | — | -0.6583 | -0.6981 |
| CH1 | -0.6982 | -0.7660 | -0.7660 | -0.6295 | -0.6871 | -0.7241 |
| CY1 | — | -0.5125 | -0.5125 | -0.3196 | -0.4152 | -0.4556 |
| CZ1 | -0.7200 | -0.7752 | -0.7752 | -0.8687 | -0.8007 | -0.8122 |
| DK1 | -0.3992 | -0.4716 | -0.4716 | -0.4428 | -0.4595 | -0.4885 |
| FI1 | — | -0.7847 | -0.7847 | — | -0.6266 | -0.6643 |
| FL1 | -0.1570 | -0.3090 | -0.3090 | -0.1551 | -0.1842 | -0.2871 |
| G1 | -0.4955 | -0.6938 | -0.6938 | -0.6648 | -0.6786 | -0.7087 |
| HR1 | -0.3665 | -0.4831 | -0.4831 | -0.4867 | -0.5308 | -0.5702 |
| HU1 | — | -0.4884 | -0.4884 | — | -0.5524 | -0.5868 |
| IE1 | — | -0.4750 | -0.4750 | — | -0.5369 | -0.5741 |
| IS1 | — | -0.6817 | -0.6817 | — | -0.6004 | -0.6394 |
| ISR | — | -0.7194 | -0.7194 | — | -0.6075 | -0.6389 |
| KZ1 | — | -0.6763 | -0.6763 | -0.5764 | -0.5971 | -0.6309 |
| LV1 | — | -0.7200 | -0.7200 | — | -0.6276 | -0.6655 |
| MD1 | — | -0.8688 | -0.8688 | — | -0.6419 | -0.6813 |
| N1 | -0.5182 | -0.5625 | -0.5625 | -0.5555 | -0.5079 | -0.6123 |
| NI1 | — | -0.9694 | -0.9694 | — | -0.6693 | -0.7040 |
| NOR | -0.4955 | -0.7082 | -0.7082 | -0.3824 | -0.5318 | -0.5991 |
| P1 | -0.4560 | -0.5971 | -0.5971 | -0.4929 | -0.5241 | -0.5010 |
| PD | -0.1088 | -0.2503 | -0.2503 | -0.2102 | -0.2341 | -0.2659 |
| PL | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0000 |
| PO1 | — | -0.2986 | -0.2986 | — | -0.3319 | -0.3647 |
| RO1 | — | -0.4464 | -0.4464 | — | -0.4830 | -0.5375 |
| RS1 | -0.4309 | -0.7002 | -0.7002 | -0.5107 | -0.6253 | -0.6651 |
| SA | -0.1946 | -0.2903 | -0.2903 | -0.3331 | -0.3185 | -0.3507 |
| SC0 | -0.7342 | -0.7392 | -0.7392 | -0.5621 | -0.6024 | -0.8373 |
| SE1 | — | -0.5039 | -0.5039 | — | -0.4916 | -0.5380 |
| SI1 | — | -0.5361 | -0.5361 | — | -0.5065 | -0.5395 |
| SK1 | -0.8556 | -0.9709 | -0.9709 | -0.6687 | -0.7123 | -0.7928 |
| T1 | -0.5280 | -0.7355 | -0.7355 | -0.5705 | -0.6555 | -0.6322 |
| UA1 | -0.5886 | -0.9288 | -0.9288 | -0.6025 | -0.7597 | -0.8188 |
| WA1 | — | -0.6965 | -0.6965 | — | -0.6205 | -0.6573 |

## Today's forecast and offsets

Fixed origin **17 October 2026, 20:30 UTC (16:30 Toronto)**; seed 7, 10,000 simulations. Identical fixtures and standings were verified byte for byte across variants. These are fresh local comparisons in `out/task-a/`, not changes to published data.

| League | No EL/ECL offset | Openfootball offset | Both offset | Both − openfootball | Old mean rating | New mean rating |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| PL | +0.0000 | +0.0000 | +0.0000 | +0.0000 | 73.20 | 73.29 |
| PD | -0.1524 | -0.1608 | -0.1609 | -0.0000 | 64.36 | 64.69 |
| BL1 | -0.1612 | -0.1650 | -0.1907 | -0.0257 | 63.60 | 62.58 |
| SA | -0.2614 | -0.2402 | -0.2322 | +0.0079 | 58.72 | 59.67 |
| FL1 | -0.2930 | -0.3034 | -0.3640 | -0.0605 | 56.87 | 54.05 |
| P1 | -0.4716 | -0.4849 | -0.4724 | +0.0126 | 45.42 | 47.03 |
| N1 | -0.6343 | -0.6058 | -0.6480 | -0.0422 | 39.43 | 38.21 |
| SC0 | -0.5400 | -0.5664 | -0.8251 | -0.2588 | 40.65 | 28.47 |

Serie A’s latest replay offset falls from −0.3185 to −0.3507 relative to the Premier League. At today’s origin with CL prices enabled, it rises slightly from −0.2402 to −0.2322, and its mean rating rises from 58.72 to 59.67. The Premier League lead over La Liga is essentially unchanged (0.1608 to 0.1609), while its lead over the Bundesliga widens from 0.1650 to 0.1907 and over Ligue 1 from 0.3034 to 0.3640. ESPN therefore does not resolve the original Serie A/English-lead concern.

Plan E adds a current market shift even to the reference league. Subtracting the Premier League offset above avoids mistaking a common reference shift for a change in league gaps. Raw shifted and results-only offsets remain in the local forecast metadata.

| Club | Openfootball title % | Both title % | Change (percentage points) |
| --- | ---: | ---: | ---: |
| FC Bayern München | 23.81 | 21.45 | -2.36 |
| Arsenal FC | 21.89 | 20.88 | -1.01 |
| FC Barcelona | 18.24 | 19.24 | +1.00 |
| Paris Saint-Germain FC | 12.43 | 11.82 | -0.61 |
| Real Madrid CF | 10.25 | 11.67 | +1.42 |
| Manchester City FC | 2.19 | 2.44 | +0.25 |
| Liverpool FC | 2.73 | 2.40 | -0.33 |
| Club Atlético de Madrid | 1.73 | 2.05 | +0.32 |
| Aston Villa FC | 1.00 | 1.97 | +0.97 |
| FC Internazionale Milano | 1.49 | 1.83 | +0.34 |
| Manchester United FC | 1.01 | 1.30 | +0.29 |
| Borussia Dortmund | 0.85 | 0.77 | -0.08 |

## ESPN coverage and exclusions

Counts at today's fixed origin, after canonical aliases. Reasons are mutually exclusive in this order: extra time/penalties, unsupported status or invalid input, known unmodelled league, no domestic history, unavailable result, duplicate. `no_domestic_history` includes clubs absent from the domestic adapters whose league cannot be recovered from existing identities; names are listed in the JSON rather than assigned an invented league.

| Season | Cup | Archived | Included | Unmodelled league | No domestic history | Extra time | Penalties |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | ECL | 153 | 37 | 30 | 84 | 2 | 0 |
| 2026 | ECL | 18 | 1 | 3 | 14 | 0 | 0 |
| 2025 | EL | 189 | 109 | 56 | 19 | 3 | 2 |
| 2026 | EL | 36 | 19 | 8 | 9 | 0 | 0 |

All remaining exclusion counts (invalid data, unknown statuses, duplicates and unavailable results) are zero at this origin. Per-origin ESPN audits retain the availability exclusions and CSV SHA-256 hashes. Full-season fitting coverage exceeds the scored subset: games before the first UCL replay origin are not evaluated.

Only `full time` ESPN scores are used. `after extra time` and `penalties` rows are excluded entirely because ESPN does not expose a reliable 90-minute score in this archive. Finals and the already verified relocated Ukrainian home fixtures use neutral rates. Historical ESPN availability is **approximated as kickoff plus three hours, strictly before the origin**. `fetched_at` is retained for provenance and never used as a historical publication time.

## Identity evidence

Added explicit aliases use ESPN's club names and the existing domestic source spellings:

- [Racing Genk (ESPN ID 938)](https://www.espn.com/soccer/team/results?id=938&league=UEFA.EUROPA&season=2025) → `genk`, matching the [Belgian domestic CSV](https://www.football-data.co.uk/mmz4281/2526/B1.csv).
- [Rapid Vienna (ESPN ID 519)](https://www.espn.com.au/football/team/results/_/id/519/aut.rapid_vienna) → `rapid wien`, matching the [Austrian domestic CSV](https://www.football-data.co.uk/new/AUT.csv).
- [Sint-Truidense (ESPN ID 936)](https://www.espn.com/soccer/team/_/id/936/sint-truidense) → `st truiden`, matching the [Belgian domestic CSV](https://www.football-data.co.uk/mmz4281/2627/B1.csv).

Existing aliases already cover AZ Alkmaar, Feyenoord Rotterdam, SK Brann, RB Salzburg, SK Sturm Graz, Sparta Prague, NEC Nijmegen and Olympiacos. Names from uncovered leagues are not fuzzy-matched to a rated club.

## Reproduction and checks

Using Python 3.12 and the pinned requirements from the repository root:

```bash
for history in none openfootball both; do
  PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    football-ucl --evaluate --european-history "$history" --n-sim 2000 --seed 7 \
    --out-dir "out/task-a/$history"
done
```

The current-forecast comparison uses the same loop with `--season 2026 --as-of 2026-10-17T20:30:00Z --n-sim 10000 --seed 7 --no-match-forecasts --no-sensitivity`, without `--evaluate`, and output directories `out/task-a/today-<history>`.

The local runs called the same `champions_league.cli.main` entry point through the existing virtual environment with this worktree on `PYTHONPATH`. The JSON records the calibration hash, effective variants, per-season metrics, all league offsets, paired standard errors, archive hashes and current title comparison.

The provider gaps are shared by all variants: inaccessible pre-2023 football-data.org European history/baseline seasons, missing Czech 2022/23 and 2025/26 results, missing Azerbaijani 2022/23–2023/24 results, and the official coefficient feed returning 403. They remain in per-origin metadata; none is filled with future results. Replay positions/draws retain the existing availability approximations. Two tournaments and small numbers of origin clusters limit the evidence.

Validation: the existing offline suite passed **124 tests**; `validate_site_data.py --data site/data` validated **484 files**. Direct loader checks covered the strict three-hour boundary, exclusion of both extended-time statuses, aliases, missing domestic history and duplicate exclusion. No tests or docstrings were added, no calibration artifact or archived odds/results were modified, and published forecasts were left unchanged.
