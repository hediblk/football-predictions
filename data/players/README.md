# Squad observations and references

`rosters/<UTC date>/<code>.json` archives football-data.org's `/v4/competitions/<code>/teams` response with its actual `fetched_at` and URL. A snapshot is an observation of the provider's squad, not proof of registration or availability. Never replace a dated file. The first Champions League snapshot was recovered from the existing HTTP cache with its original observation time; the La Liga pilot snapshot was copied unchanged. The other four leagues were observed on 16 October UTC (15 October in Toronto).

`ea.sha256` pins the bytes of the [commit-pinned EA CSV](https://raw.githubusercontent.com/LakshmiKanth11/EA_FC_ANALYSIS/c0b2542d9fcae72d2c538a472a30ee57c4e7c75e/EA_FC_PLAYERS_DATASET_AND_%20DASHBOARD/data/players.csv). The raw CSV stays in `.cache/`. It contains one publisher-labelled FC 27 snapshot, 12 September 2026; the mirror's provenance is a publisher claim. Changes to that pin require reviewing a new source/vintage explicitly.

`identity_overrides.json` contains reviewed provider/EA links, each with its expected names/dates, EA ID, evidence URL, observation date and reason. These IDs belong to separate providers. Do not extrapolate an override to another player or numeric ID namespace.

`baselines/<season>/<slug>/<content ID>.json` freezes each published club reference. Its `generated_at` is first creation, not roster observation or EA release. New content creates a new immutable file. An identical rerun reuses its timestamp. These references cannot reconstruct a pre-match squad before their creation.

The initial 111-club export has the following coverage. Champions League overlaps the domestic cohorts; do not sum the rows.

| Competition | Clubs | Matched / listed players | Coverage | Filled ideal XIs |
| --- | ---: | ---: | ---: | ---: |
| Premier League | 20 | 497 / 545 | 91.2% | 20 / 20 |
| La Liga | 20 | 470 / 520 | 90.4% | 20 / 20 |
| Bundesliga | 18 | 478 / 523 | 91.4% | 18 / 18 |
| Serie A | 20 | 503 / 585 | 86.0% | 20 / 20 |
| Ligue 1 | 18 | 412 / 475 | 86.7% | 17 / 18 |
| Champions League | 36 | 838 / 989 | 84.7% | 34 / 36 |

All 111 files are present under `site/data/squads/2026/`. Slovan Bratislava's provider squad is empty and has an explicit `unavailable` file (not a fabricated roster); it contributes no players to the denominator. Sabah has too few matched positions to fill an XI; Toulouse lacks an eligible rated left-back. These slots remain unfilled. Every partially rated squad remains provisional even when it fills an XI.

Yann Gboho (Coventry/Toulouse), Daniel Elfadli (Hamburg/LASK) and Mikkel Hansen (PSV/Bodø/Glimt) each occur at two clubs in the selected raw observations. All six rows remain ambiguous, unrated and excluded from XI selection. The exporter chooses the newer dated roster for clubs present in both domestic and European responses, without rewriting either archive.

On 16 October, source-backed spelling overrides linked Angers' Ousman Camara to Ousmane Camara and Lilian Rao-Lisoa to Lilian Raolisoa. A new Angers baseline rates 20/22 listed players; its previous baseline remains archived. Season usage separately adds repeated match-sheet players missing from listed squads as `observed`, without changing baseline coverage or ideal XIs. Possible aliases remain unresolved pending evidence instead of becoming duplicate observed players; see the [Task 4b contract](../../docs/site-data-contract.md#squad-references).

See the [publication contract](../../docs/site-data-contract.md#squad-references) and [local commands](../../docs/squad-matching.md#published-export-all-competitions). Squad refreshes are optional, reuse rosters for seven days, and keep old site files and timestamps on failure. No participation ledger or forecast adjustment is part of this export.
