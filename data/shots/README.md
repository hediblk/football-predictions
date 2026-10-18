# Understat shot archive

Every shot in the five domestic leagues for seasons the site's match files don't cover, from [Understat](https://understat.com/). One gzip CSV per league and season start year: `<league>/<season>.csv.gz`, with Understat's league names (`EPL`, `La_liga`, `Bundesliga`, `Serie_A`, `Ligue_1`). `scripts/build_club_profiles.py` reads the season before the current one to fill each club's 38-game window.

Each row is one shot: `match_id`, `date` (provider kickoff, UTC), `home`, `away` (Understat team names), `side` (`h`/`a`, the shooter's side), `minute` (zero-based elapsed, including stoppage time), `x`, `y` (0–1, `x` toward the attacking goal), `xg`, `result`, `situation`, `body`, `last_action` (the event just before the shot), `player` and `assister` (empty for none). Provider values are copied unchanged. `OwnGoal` rows sit on the side of the player who scored, so they count for the other side.

`scripts/archive_understat_shots.py` derives the files offline from the match payloads cached by `scripts/fetch_understat_rosters.py` (see the [Understat match sheets](../players/understat/README.md)), using its `team_games.csv.gz` as the match list, so matches excluded there are missing here too. Output is deterministic gzip.

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/archive_understat_shots.py --seasons 2025 \
  --cache /Users/hedibelkahia/codes/football/.cache/understat/matches
```

2025/26, archived on 18 October 2026: EPL 380 matches, La Liga 379, Bundesliga 306, Serie A 380, Ligue 1 305 (one La Liga and one Ligue 1 match are excluded in the match-sheet archive). At the start of each new season, archive the season just finished before the first refresh, or profiles fall back to the new season's games only.
