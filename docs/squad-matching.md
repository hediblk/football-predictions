# Ideal XI and match usage pilot

The La Liga pilot uses a fixed EA FC 27 rating snapshot, current football-data.org squads, and collected Understat appearances. It produces local review reports in `out/squads/`. It does not alter forecast probabilities or publish player data.

## Inputs and setup

The selected [EA FC dataset](https://github.com/LakshmiKanth11/EA_FC_ANALYSIS) is a CSV mirror of a publisher-labelled 12 September 2026 snapshot. The pinned revision below contains 17,849 men's players with full/common names, birth dates, overall ratings, primary positions and alternative positions. Its date fields use day-month-year despite the README describing ISO dates; the loader normalizes both explicit formats. The publisher's original scraper link is unavailable, so its EA provenance remains a publisher claim. Raw EA data stays in the ignored cache; public redistribution has not been authorized by downloading the file.

```bash
mkdir -p .cache/players/ea
curl -fL 'https://raw.githubusercontent.com/LakshmiKanth11/EA_FC_ANALYSIS/c0b2542d9fcae72d2c538a472a30ee57c4e7c75e/EA_FC_PLAYERS_DATASET_AND_%20DASHBOARD/data/players.csv' -o .cache/players/ea/fc27-2026-09-12.csv
PYTHONDONTWRITEBYTECODE=1 python scripts/build_squads.py --competition PD
```

Use the existing Python environment and package dependencies. No new dependency is needed. `FOOTBALL_DATA_API_KEY` comes from the environment or repository `.env`. One request per competition fetches `/v4/competitions/<code>/teams`; its payload and actual observation time are saved at `.cache/players/rosters/<UTC date>/<code>.json`. Same-day reruns reuse that observation. The script checks the season, competition and all supported club IDs against committed site data, and rejects empty squads, conflicting snapshots and repeated provider player IDs.

Other supported codes are `PL PD BL1 SA FL1 CL`, accepted together after `--competition`. A club present in both domestic and European responses is matched once. La Liga is the tested pilot. API squads are provider observations rather than independently verified registrations or availability.

Replay the saved squad input without network access:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/build_squads.py --competition PD --roster-date 2026-10-15 --offline
```

Older roster dates require `--offline`: current membership cannot reconstruct past squads. `--players` accepts another CSV with the same EA schema; supply its provenance with `--source-url`. One file must contain only one edition and snapshot.

## Identities and XI selection

Matching requires an identical birth date and a unique normalized full/common name, a multi-token subset of that name, or an explicit given-name variant such as Dani/Daniel. A single-token provider name can match EA's explicit common name with that birth date, but is not matched to an arbitrary surname. Duplicate EA IDs are quarantined; if two squad players resolve to the same EA identity, both become ambiguous. Suggestions stay separate from accepted identities.

[data/players/identity_overrides.json](../data/players/identity_overrides.json) records source-backed exceptions. Each pins the expected provider name and original birth date, verified birth date, EA ID, source URL and observation date. It covers two erroneous provider birth dates (Pablo Barrios and Junior Firpo), three verified name differences (Boyomo, Isi Palazón and Vlachodimos), and Abde Ezzalzouli's match-sheet alias for Abdessamad Ezzalzouli. It accepts a provider's later correction to the verified date, but fails if the source identity changes unexpectedly. Original provider values remain in the output.

Current membership comes from the API, while positions and ratings come from EA. The default `4-3-3` has GK, LB, two CBs, RB, CDM, two CMs, LW, ST and RW. `--formation 4-2-3-1` or `4-4-2` uses explicit roles for those shapes. Primary and alternative positions are eligible; LW/LM and RW/RM are compatible wide roles. The assignment maximizes filled roles first, then summed overall rating. Ties prefer primary positions, with a stable provider-ID ordering. Each player fills at most one slot. Ratings must be integers on 1–99.

This is an ideal reference with everyone assumed available. It does not predict the coach's lineup, infer injuries, assess tactical chemistry or estimate goals lost to an absence. Unmatched squad players can still change a provisional XI. Missing roles stay unfilled and have no mean rating. Only a fully rated squad gets `complete` status.

## Frozen baselines

`PD.json` and `PD.md` hold the latest baseline and readable lineup report. An immutable copy lives at `snapshots/PD/<baseline_id>.json`. The baseline ID hashes its inputs and output, including the EA file hash, roster hash, identity overrides, formation and assignments. An identical rerun reuses the original `created_at`; changed inputs create a new baseline and leave prior snapshots intact. Formation changes are explicit new baselines.

The baseline becomes available when created, even though its EA ratings are older. It is eligible only for matches kicking off strictly after `created_at`. Today's identity joins and squads never become historical forecast features.

On the 15 October 2026 squad snapshot, **470 of 520** players match. All 20 clubs can fill position-constrained 4-3-3s, including Barcelona's Pedri, Raphinha and Lamine Yamal. Remaining identities are listed per club; only two clubs currently have full squad coverage.

## Compare each finished game

After match data refreshes, rerun:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/compare_lineup_usage.py
# Pin a specific version instead of the latest PD.json:
# python scripts/compare_lineup_usage.py --baseline out/squads/snapshots/PD/<baseline_id>.json
```

This reads the existing `site/data/matches/la-liga.json` and `site/data/match/<season>/la-liga/<fixture id>.json` without new provider requests. `PD-usage.json` retains every eligible club-game and each ideal player's participation; `PD-usage.md` summarizes games and shows each club's latest comparison. This is a local command, not a scheduled or deployed feature.

Understat's match sheet supplies actual minutes and starter/substitute flags (`position == Sub` means a substitute appearance). Names map uniquely within the baseline club, using provider names and accepted EA full/common names. Ambiguous assignments and duplicate player mappings remain unresolved. A sheet must have eleven starters, unique source player IDs and feasible minutes. Missing or invalid sheets are labelled rather than counted as absences.

Each ideal player is `started`, `substitute`, `did_not_play` or `unknown`. An observed player keeps their reported minutes even when another identity is unresolved. An unobserved player gets `did_not_play` and zero minutes only if every appearance on that side maps; otherwise participation stays unknown. Understat does not list unused substitutes, so the pilot cannot distinguish unused bench from omission, injury, suspension or rest. It does not infer an entry minute from `90 - minutes`, or combine ESPN clocks with potentially inconsistent Understat minutes.

When all eleven ideal players' participation is known, ideal minutes share is `sum(min(minutes, 90)) / (11 * 90)`, displayed as a percentage. Missing roles or unknown participation suppress the metric. This is unweighted usage, not a calibrated strength adjustment; EA overall differences are not assumed to measure lost goals.

The initial baseline has no completed prospective fixtures yet. To inspect earlier games as explicitly retrospective diagnostics:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/compare_lineup_usage.py --retrospective
```

These write separate `PD-usage-diagnostic.json` and `.md` files. Every row indicates whether its kickoff preceded baseline creation. On the current 78 finished La Liga fixtures there are 156 club-game rows; one match lacks Understat player data. These current-XI comparisons are examples of the plumbing, not pre-match observations or independent backtests. The baseline and match-detail hashes preserve provenance for both modes.

## Cross-check the heatmap player names

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/check_squad_identities.py
```

This checks the current season's Champions League heatmap files against the pilot's supported clubs, without provider requests. `PD-identities.json` records mapped UEFA/squad IDs, names, baseline and match-detail hashes, counts and any identity conflicts. Unmatched names, duplicate assignments, conflicting UEFA bindings and incomplete starter sets produce a failing exit status. This is a name audit against today's roster, not a historical forecast input.

On 15 October 2026, all **159 participating-player records, 129 heatmap-player records and 110 starter records** match across ten club-games for Barcelona, Real Madrid, Atlético Madrid, Betis and Villarreal. The remaining 26 heatmap fixtures have no La Liga pilot club and are outside this audit. A source-backed Abde/Abdessamad alias resolves the only initial gap.

UEFA `positions` identifies starters from its lineup `field`; `physical.players` supplies positive playing times, including stoppage time. These accompanying records support XI history and minutes. Player heatmap grids require at least 30 minutes and include long substitute appearances (19 in this sample), so they cannot identify starters alone. Domestic sheets supply starts/minutes through Understat, without activity heatmaps. The [squads and players plan](xi-ui-plan-2026-10-15.md) extends this to every competition, the club Squad subtab, past lineups, a pooled player-impact model and lineup-adjusted forecasts.
