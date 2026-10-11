import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from standing_prediction.defaults import CALIBRATION_VERSION, DEFAULT_WEIGHTS
from standing_prediction.ensemble import blend_probabilities

from champions_league.data import load_inputs
from champions_league.coefficients import fetch_coefficients
from champions_league.strengths import fit_strengths
from champions_league.tournament import simulate_tournament


def _teams(matches):
    return set(matches.homeTeam) | set(matches.awayTeam)


def _origins(fixtures):
    league = fixtures[fixtures.stage.eq("LEAGUE_STAGE")]
    origins = []
    for md in (2, 4, 6, 8):
        last = league.loc[league.matchday.le(md), "utcDate"].max()
        origins.append((f"MD{md}", last.normalize() + pd.Timedelta(days=1, seconds=1)))
    for stage in ("PLAYOFFS", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL"):
        rows = fixtures[fixtures.stage.eq(stage)]
        if not rows.empty:
            origins.append((f"before_{stage}", rows.utcDate.min().normalize()))
    return sorted(origins, key=lambda item: item[1])


def evaluate(*, seasons=(2024, 2025), n_sim=2000, seed=7, out_dir="out", cache=True):
    if n_sim < 1:
        raise ValueError("n_sim must be positive.")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshots, matches = [], []
    for season in seasons:
        targets = load_inputs(season=season, as_of=pd.Timestamp.now(tz="UTC"), cache=cache)
        coefficients, coefficient_metadata = fetch_coefficients(season, targets.standings.team, cache=cache)
        coefficients = coefficients if coefficient_metadata["complete"] else None
        final_positions = targets.standings.set_index("team").position.to_dict()
        future = targets.fixtures[targets.fixtures.status.eq("FINISHED")].copy()
        if len(future[future.stage.eq("LEAGUE_STAGE")]) != 144:
            raise ValueError(f"Season {season} is not complete; cannot evaluate final positions.")
        stages = {"playoffs_pct": "PLAYOFFS", "round16_pct": "LAST_16", "quarterfinal_pct": "QUARTER_FINALS",
                  "semifinal_pct": "SEMI_FINALS", "final_pct": "FINAL"}
        reach = {event: _teams(future[future.stage.eq(stage)]) for event, stage in stages.items()}
        final = future[future.stage.eq("FINAL")].iloc[0]
        winner = final.get("winner")
        if winner in ("HOME_TEAM", "AWAY_TEAM"):
            winner = final.homeTeam if winner == "HOME_TEAM" else final.awayTeam
        if winner not in (final.homeTeam, final.awayTeam):
            raise ValueError(f"Season {season} final winner is missing.")
        reach["title_pct"] = {winner}
        origins = _origins(future)
        for origin_index, (label, origin) in enumerate(origins):
            logging.info("Historical Champions League %s %s (%s).", season, label, origin)
            data = load_inputs(season=season, as_of=origin, cache=cache)
            teams = data.standings.team.tolist()
            model = fit_strengths(data.history, teams=teams, team_leagues=data.team_leagues, as_of=origin)
            result = simulate_tournament(data.fixtures, data.standings, model, season=season, n_sim=n_sim,
                                         seed=seed, as_of=origin, coefficients=coefficients)
            p = result.probabilities.loc[teams].to_numpy() / 100
            truth = np.array([final_positions[team] for team in teams])
            target_cdf = np.arange(1, 37)[None, :] >= truth[:, None]
            row = {"season": season, "snapshot": label, "as_of": origin.isoformat(), "history_matches": len(data.history),
                   "position_rps": float(np.square(p.cumsum(axis=1)[:, :-1] - target_cdf[:, :-1]).mean()),
                   "conservation": result.metadata.get("conservation"), "data": data.metadata,
                   "coefficients": coefficient_metadata}
            for event, reached in reach.items():
                if event in result.summary:
                    target = np.array([float(team in reached) for team in teams])
                    predicted = result.summary.loc[teams, event].to_numpy() / 100
                    row[event.replace("_pct", "_brier")] = float(np.square(predicted - target).mean())
            xg_teams = set(data.history.loc[data.history.get("home_xg", pd.Series(np.nan, index=data.history.index)).notna(), "homeTeam"])
            for covered in (True, False):
                mask = np.array([(team in xg_teams) == covered for team in teams])
                if mask.any():
                    row[f"position_rps_xg_{covered}"] = float(np.square(p.cumsum(axis=1)[mask, :-1] - target_cdf[mask, :-1]).mean())
                    for event, reached in reach.items():
                        target = np.isin(np.array(teams)[mask], list(reached))
                        predicted = result.summary.loc[teams, event].to_numpy()[mask] / 100
                        row[f"{event.replace('_pct', '_brier')}_xg_{covered}"] = float(np.square(predicted - target).mean())
            snapshots.append(row)
            end = origins[origin_index + 1][1] if origin_index + 1 < len(origins) else future.utcDate.max() + pd.Timedelta(days=1)
            heldout = future[future.utcDate.ge(origin) & future.utcDate.lt(end)]
            no_offsets = fit_strengths(data.history, teams=teams, team_leagues=data.team_leagues, as_of=origin, league_offsets=False)
            goals_only = fit_strengths(data.history, teams=teams, team_leagues=data.team_leagues, as_of=origin, xg_weight=0)
            for match in heldout.itertuples():
                neutral = bool(getattr(match, "neutral", False))
                outcome = 0 if match.homeGoals > match.awayGoals else 1 if match.homeGoals == match.awayGoals else 2
                losses = {}
                for name, fitted in (("joint", model), ("without_offsets", no_offsets), ("goals_only", goals_only)):
                    prob = blend_probabilities(fitted.match_outcome_probs(match.homeTeam, match.awayTeam, neutral=neutral),
                                               p_elo=fitted.elo_probs(match.homeTeam, match.awayTeam, neutral=neutral), weights=DEFAULT_WEIGHTS)
                    losses[name] = float(-np.log(max(prob[outcome], 1e-12)))
                losses["elo"] = float(-np.log(max(model.elo_probs(match.homeTeam, match.awayTeam, neutral=neutral)[outcome], 1e-12)))
                matches.append({"season": season, "snapshot": label, "id": match.id, "home": match.homeTeam, "away": match.awayTeam,
                                "xg_covered": match.homeTeam in xg_teams and match.awayTeam in xg_teams, **losses})
            (out_dir / "cl_evaluation_snapshots.json").write_text(json.dumps(snapshots, indent=2, default=str) + "\n")
    match_frame = pd.DataFrame(matches)
    match_frame.to_csv(out_dir / "cl_evaluation_matches.csv", index=False)
    metrics = ["joint", "without_offsets", "goals_only", "elo"]
    active_positions = [row["position_rps"] for row in snapshots if row["snapshot"] in {"MD2", "MD4", "MD6"}]
    report = {"seasons": list(seasons), "n_sim": n_sim, "seed": seed, "weight_calibration_version": CALIBRATION_VERSION,
              "snapshots": len(snapshots), "matches": len(matches), "match_log_loss": match_frame[metrics].mean().to_dict(),
              "match_log_loss_by_xg": {str(key): group[metrics].mean().to_dict() for key, group in match_frame.groupby("xg_covered")},
              "tournament_metrics": pd.DataFrame(snapshots).select_dtypes(include="number").drop(columns=["season", "history_matches"]).mean().to_dict(),
              "position_rps_after_MD2_MD4_MD6": float(np.mean(active_positions)),
              "tournament_averaging": "All replay origins, including completed league phases with known positions and already-resolved knockout stages; see per-snapshot metrics for comparisons at equal horizons.",
              "limitations": "Retrospective replay with the fixed globally calibrated artifact, which includes these domestic seasons. Publication times and historical draw availability are approximated. Two tournament seasons do not establish calibrated title probabilities."}
    (out_dir / "cl_evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
