import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.special import logsumexp

from forecast_calibration.dataset import dc_prefix, feature_code_hash, load_season
from standing_prediction.match_forecasts import describe_match
from standing_prediction.odds import _football_data_csv, _uk_dates
from standing_prediction.predict_positions import fit_model_components
from standing_prediction.scorecard import frequency_baseline
from standing_prediction.xg import blend_xg_strengths

ROOT = Path(__file__).resolve().parents[4]
ARTIFACT = ROOT / 'src/standing_prediction/calibrated_weights.json'
KEYS = ['league', 'season', 'utcDate', 'homeTeam', 'awayTeam']
VERDICTS = ('won', 'level', 'lost', 'unknown')
KINDS = ('called', 'draw', 'upset', 'missed_draw_call')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cached_content(cache, url, **kwargs):
    folder = 'understat' if 'understat.com/' in url else 'football-data-uk'
    key = hashlib.sha256(json.dumps([url, kwargs.get('params') or {}], sort_keys=True).encode()).hexdigest()
    return json.loads((cache / folder / f'{key}.json').read_text())['content']


def blend(dc, elo, share):
    logits = share * np.log(np.clip(dc, 1e-12, 1)) + (1 - share) * np.log(np.clip(elo, 1e-12, 1))
    return np.exp(logits - logsumexp(logits, axis=-1, keepdims=True))


def replay(league, season, dataset, cache, output):
    artifact = json.loads(ARTIFACT.read_text())
    features = pd.read_csv(dataset)
    features = features[(features.league == league) & (features.season == season)]
    metadata = json.loads(dataset.with_suffix('.json').read_text())
    signature = {'dataset': digest(dataset), 'artifact': digest(ARTIFACT), 'code': digest(__file__),
                 'model_code': feature_code_hash(),
                 'match_forecasts_code': digest(ROOT / 'src/standing_prediction/match_forecasts.py'), 'inputs': {}}
    # Hash every required cache, including the frequency baseline's earlier seasons.
    urls = [f'https://www.football-data.co.uk/mmz4281/{y % 100:02d}{(y + 1) % 100:02d}/{league}.csv'
            for y in range(season - 5, season + 1)]
    from forecast_calibration.dataset import XG_COMPETITIONS
    from standing_prediction.xg import COMPETITION_TO_UNDERSTAT_LEAGUE
    us_league = COMPETITION_TO_UNDERSTAT_LEAGUE[XG_COMPETITIONS[league]]
    urls += [f'https://understat.com/getLeagueData/{us_league}/{y}'
             for y in range(max(2014, season - metadata['prior_seasons']), season + 1)]
    for url in urls:
        signature['inputs'][url] = hashlib.sha256(cached_content(cache, url).encode()).hexdigest()
    path = output / 'replay' / f'{league}_{season}.csv'
    stamp = path.with_suffix('.json')
    if path.exists() and stamp.exists() and json.loads(stamp.read_text()) == signature:
        return str(path)
    read = partial(cached_content, cache)
    with patch('standing_prediction.odds.cached_get', read), patch('standing_prediction.xg.cached_get', read):
        history = {y: load_season(league, y) for y in range(max(2014, season - metadata['prior_seasons']), season + 1)}
        frequency_history = {}
        for year in range(season - 5, season):
            raw = _football_data_csv(league, year, 30, None, True)
            dates = _uk_dates(raw)
            frequency_history[year] = pd.DataFrame({'utcDate': dates, 'homeGoals': raw.FTHG, 'awayGoals': raw.FTAG,
                                                   'available_at': dates.dt.normalize() + pd.Timedelta(days=1)})
    frequency = frequency_baseline(frequency_history, season)
    if frequency['p'] is None:
        raise ValueError(f'Incomplete frequency history: {league}/{season}')
    matches = history[season]
    source = features.merge(matches, on=KEYS[:2] + ['homeTeam', 'awayTeam'], suffixes=('', '_source'), validate='one_to_one')
    if len(source) != len(features) or not (pd.to_datetime(source.utcDate, utc=True) == source.utcDate_source).all():
        raise ValueError('Result identities or dates differ from saved features')
    truth = np.where(source.homeGoals > source.awayGoals, 0, np.where(source.homeGoals == source.awayGoals, 1, 2))
    if not np.array_equal(truth, source.y):
        raise ValueError('Result differs from calibration target')
    teams = sorted(set(matches.homeTeam) | set(matches.awayTeam))
    prior = pd.concat(list(history.values()), ignore_index=True)
    rows = []
    for origin, group in source.groupby('forecast_at', sort=True):
        cutoff = pd.Timestamp(origin)
        train = prior[(prior.available_at <= cutoff) & (prior.utcDate < cutoff)]
        if not (pd.to_datetime(group.utcDate, utc=True) > cutoff).all():
            raise ValueError('Forecast at/after kickoff')
        if not group.training_matches.eq(len(train)).all() or not pd.to_datetime(group.training_last_available_at, utc=True).eq(train.available_at.max()).all():
            raise ValueError('Training provenance differs from saved features')
        dc, elo, xg, _ = fit_model_components(train, teams=teams, reference_date=cutoff,
                                              xi=metadata['xi'], lambda_reg=metadata['lambda_reg'], xg=True)
        model = blend_xg_strengths(dc, xg, artifact['xg_weight'], artifact['xg_scale'])
        prefix = dc_prefix(artifact['xg_weight'], artifact['xg_scale'])
        for row in group.itertuples(index=False):
            p_dc = np.array(model.match_outcome_probs(row.homeTeam, row.awayTeam))
            p_elo = np.array(elo.predict_probs(row.homeTeam, row.awayTeam))
            stored = np.array([getattr(row, f'elo_{c}') for c in 'hda'])
            original = features[(features.homeTeam == row.homeTeam) & (features.awayTeam == row.awayTeam)].iloc[0]
            drift = max(np.max(np.abs(p_dc - original[[f'{prefix}_{c}' for c in 'hda']].to_numpy(float))),
                        np.max(np.abs(p_elo - stored)))
            if drift > 1e-6:
                raise ValueError(f'Replay probability drift {league}/{season}: {drift}')
            p = blend(original[[f'{prefix}_{c}' for c in 'hda']].to_numpy(float), stored, artifact['no_odds_weights']['main'])
            _, matrix = model.score_matrix(row.homeTeam, row.awayTeam)
            forecast = describe_match(matrix, p)
            rows.append({**{key: getattr(row, key) for key in KEYS}, 'homeGoals': row.homeGoals, 'awayGoals': row.awayGoals,
                         'home_xg': row.home_xg, 'away_xg': row.away_xg, 'understat_id': row.understat_id,
                         'pred_home': forecast['exp_home_goals'], 'pred_away': forecast['exp_away_goals'],
                         'replay_max_drift': drift, 'frequency_training_matches': frequency['n'], **{f'frequency_{c}': v for c, v in zip('hda', frequency['p'])}})
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    stamp.write_text(json.dumps(signature, indent=2) + '\n')
    return str(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, default=Path('out/miss-report'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--replay-only', action='store_true')
    args = parser.parse_args()
    args.dataset = args.dataset.resolve()
    args.cache_dir = args.cache_dir.resolve()
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(args.dataset)
    artifact = json.loads(ARTIFACT.read_text())
    if len(data) != 19763 or digest(args.dataset) != artifact['dataset']['sha256']:
        raise ValueError('Expected the saved 19,763-match calibration dataset')
    jobs = list(data.groupby(['league', 'season']).groups)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(replay, league, int(season), args.dataset, args.cache_dir, args.out_dir) for league, season in jobs]
        for job in as_completed(futures):
            print(f'Replayed {Path(job.result()).stem}', flush=True)
    if not args.replay_only:
        from forecast_calibration.miss_analysis import analyze
        analyze(args, data, artifact)


if __name__ == '__main__':
    main()
