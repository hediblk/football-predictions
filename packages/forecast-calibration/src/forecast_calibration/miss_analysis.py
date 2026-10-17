import hashlib
import json
import platform
from pathlib import Path
import subprocess
from importlib.metadata import version

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, poisson, spearmanr

from forecast_calibration.dataset import dc_prefix
from forecast_calibration.miss_report import ARTIFACT, KEYS, KINDS, ROOT, VERDICTS, blend, digest
from standing_prediction.utils import normalize_team


class Estimates:
    def __init__(self, frame):
        self.rows = []
        self.groups = [('all', frame)]
        self.groups += [(f'league:{key}', group) for key, group in frame.groupby('league')]
        self.groups += [(f'season:{key}', group) for key, group in frame.groupby('season')]
        self.groups += [('cohort:2015-2023', frame[frame.season < 2024]), ('cohort:2024-2025', frame[frame.season >= 2024])]
        self.groups += [(f'{league}:{season}', group) for (league, season), group in frame.groupby(['league', 'season'])]

    def add(self, scope, group, metric, values, total=False):
        values = pd.Series(np.asarray(values, float), index=group.index).dropna()
        used = group.loc[values.index]
        cluster = used.league + ':' + used.season.astype(str)
        unit = 'league-season'
        if cluster.nunique() == 1:
            cluster = used.forecast_at
            unit = 'forecast-origin'
        mean = values.mean() if len(values) else None
        residuals = (values - mean).groupby(cluster).sum() if len(values) else pd.Series(dtype=float)
        g = len(residuals)
        se = np.sqrt(g / (g - 1) * (residuals**2).sum()) / len(values) if g > 1 else None
        multiplier = len(values) if total else 1
        row = {'scope': scope, 'metric': metric, 'estimate': None if mean is None else float(values.sum()) if total else float(mean),
               'se': None if se is None else float(se * multiplier), 'n': len(values), 'clusters': g, 'cluster_unit': unit}
        self.rows.append(row)
        return row['estimate']

    def table(self):
        return pd.DataFrame(self.rows)


def chances(home, away):
    k = np.arange(65)
    ph, pa = poisson.pmf(k, home[:, None]), poisson.pmf(k, away[:, None])
    if (poisson.sf(64, np.r_[home, away]) > 1e-14).any():
        raise ValueError('Insufficient Poisson support')
    p = np.column_stack(((ph * poisson.cdf(k - 1, away[:, None])).sum(axis=1),
                         (ph * pa).sum(axis=1), (pa * poisson.cdf(k - 1, home[:, None])).sum(axis=1)))
    return p / p.sum(axis=1, keepdims=True)


def shots(row, cache):
    result = {'shot_reason': '', 'shot_home': np.nan, 'shot_away': np.nan,
              'pre_home': np.nan, 'pre_away': np.nan, 'first_goal': np.nan, 'early': False}
    if pd.isna(row.understat_id):
        return {**result, 'shot_reason': 'no validated league xG join'}
    path = cache / 'understat/matches' / f'{int(row.understat_id)}.json'
    try:
        raw = path.read_bytes()
        result['shot_hash'] = hashlib.sha256(raw).hexdigest()
        wrapped = json.loads(raw)
        if wrapped.get('error') or wrapped.get('failed'):
            raise ValueError('cached fetch failure')
        payload = json.loads(wrapped['content']) if 'content' in wrapped else wrapped['payload']
        events, ids = [], set()
        for side in ('h', 'a'):
            for shot in payload['shots'][side]:
                if int(shot['id']) in ids:
                    raise ValueError('duplicate shot ID')
                ids.add(int(shot['id']))
                if (int(shot['match_id']) != int(row.understat_id) or shot['h_a'] != side
                        or normalize_team(shot['h_team']) != row.homeTeam or normalize_team(shot['a_team']) != row.awayTeam
                        or abs(pd.Timestamp(shot['date'], tz='UTC') - pd.Timestamp(row.utcDate)) > pd.Timedelta(days=2)
                        or (int(shot['h_goals']), int(shot['a_goals'])) != (row.homeGoals, row.awayGoals)):
                    raise ValueError('shot fixture identity/score mismatch')
                xg, minute = float(shot['xG']), int(shot['minute'])
                if not np.isfinite(xg) or not 0 <= xg <= 1 or not 0 <= minute <= 130:
                    raise ValueError('invalid shot xG/minute')
                events.append((side, minute, xg, shot['result']))
        goals = [m for _, m, _, r in events if r in ('Goal', 'OwnGoal')]
        if len(goals) != row.homeGoals + row.awayGoals:
            raise ValueError('incomplete goal event coverage')
        first = min(goals) if goals else np.inf
        for side, name in [('h', 'home'), ('a', 'away')]:
            result[f'shot_{name}'] = sum(x for s, m, x, r in events if s == side and r != 'OwnGoal')
            result[f'pre_{name}'] = sum(x for s, m, x, r in events if s == side and m < first and r != 'OwnGoal')
        result.update(first_goal=first, early=first < 10)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['shot_reason'] = str(exc)
    return result


def verdict(margin, threshold):
    return np.where(~np.isfinite(margin), 'unknown', np.where(margin > threshold, 'won', np.where(margin < -threshold, 'lost', 'level')))


def contract(est):
    contracts = {}
    for scope, group in est.groups:
        add = lambda key, values, total=False: est.add(scope, group, key, values, total)
        xg = group.home_xg.notna() & group.away_xg.notna()
        confusion = [[add(f'confusion.{i}.{j}', (group.call == i) & (group.y == j), True) for j in range(3)] for i in range(3)]
        outcomes = {key: [add(f'outcomes.{key}.{i}', group[f'p_{c}'] if key == 'expected' else group.y == i, True)
                          for i, c in enumerate('hda')] for key in ('expected', 'actual')}
        for i, c in enumerate('hda'):
            add(f'outcomes.actual_minus_expected.{i}', (group.y == i) - group[f'p_{c}'], True)
        kinds = {kind: {lens: {v: add(f'kinds.{kind}.{lens}.{v}', (group.kind == kind) & (group[lens] == v), True)
                              for v in VERDICTS} for lens in ('xg', 'xg_pre')} for kind in KINDS}
        goals = {'team_games': int(2 * xg.sum())}
        for name, values in [('predicted', (group.pred_home + group.pred_away) / 2),
                             ('goals', (group.homeGoals + group.awayGoals) / 2),
                             ('xg', (group.home_xg + group.away_xg) / 2),
                             ('mae_goals', (abs(group.pred_home - group.homeGoals) + abs(group.pred_away - group.awayGoals)) / 2),
                             ('mae_xg', (abs(group.pred_home - group.home_xg) + abs(group.pred_away - group.away_xg)) / 2)]:
            goals[name] = add(f'goals.{name}', values.where(xg))
        add('goals.bias_goals', ((group.pred_home + group.pred_away - group.homeGoals - group.awayGoals) / 2).where(xg))
        add('goals.actual_minus_xg', ((group.homeGoals + group.awayGoals - group.home_xg - group.away_xg) / 2).where(xg))
        add('goals.bias_xg', ((group.pred_home + group.pred_away - group.home_xg - group.away_xg) / 2).where(xg))
        scored = {'n': int(xg.sum())}
        for candidate in ('model', 'elo', 'frequency'):
            scored[candidate] = add(f'xg_scored.{candidate}', group[f'xll_{candidate}'])
            add(f'real_scored.{candidate}', group[f'll_{candidate}'].where(xg))
            add(f'real_scored_all.{candidate}', group[f'll_{candidate}'])
        add('accuracy', group.call == group.y)
        add('draw_call_share', group.call == 1)
        contracts[scope] = {'n': len(group), 'misses': {'confusion': confusion, 'outcomes': outcomes, 'kinds': kinds,
                                                     'goals': goals, 'xg_scored': scored}}
        assert sum(map(sum, confusion)) == len(group)
        assert sum(sum(k['xg'].values()) for k in kinds.values()) == len(group)
        assert sum(sum(k['xg_pre'].values()) for k in kinds.values()) == len(group)
        assert np.isclose(sum(outcomes['expected']), len(group))
    return contracts


def diagnostics(est, candidates):
    for scope, group in est.groups:
        add = lambda key, frame, values: est.add(scope, frame, key, values)
        for name, series in [('probability', pd.cut(group.p_d, [0, .1, .15, .2, .25, .3, .35, .4, 1], right=False)),
                             ('closeness', pd.cut(abs(group.p_h - group.p_a), [0, .1, .2, .3, .5, 1.01], right=False))]:
            for label, subset in group.groupby(series, observed=True):
                key = f'draw.{name}.{label}'
                add(f'{key}.predicted', subset, subset.p_d)
                add(f'{key}.actual', subset, subset.y == 1)
                add(f'{key}.gap', subset, (subset.y == 1) - subset.p_d)
        for factor in (.75, 1, 1.1, 1.25, 1.5, 1.75, 2):
            p = group[['p_h', 'p_d', 'p_a']].to_numpy().copy()
            p[:, 1] *= factor
            call = p.argmax(axis=1)
            boosted = p / p.sum(axis=1, keepdims=True)
            label = f'draw_boost.{factor:g}'
            add(f'{label}.accuracy', group, call == group.y)
            add(f'{label}.accuracy_delta', group, (call == group.y).astype(float) - (group.call == group.y))
            add(f'{label}.call_share', group, call == 1)
            ll = -np.log(boosted[np.arange(len(group)), group.y.to_numpy(int)])
            add(f'{label}.log_loss_delta', group, ll - group.ll_model)
            switched = group[(call == 1) & (group.call != 1)]
            add(f'{label}.switched_accuracy_delta', switched,
                (switched.y == 1).astype(float) - (switched.y == switched.call))
        for threshold in (.3, .5, .7):
            v = verdict(group.xg_margin, threshold)
            for kind in ('all', *KINDS):
                subset = group if kind == 'all' else group[group.kind == kind]
                labels = pd.Series(v, index=group.index).loc[subset.index]
                subset = subset[labels != 'unknown']
                for value in VERDICTS[:3]:
                    add(f'margin.{threshold:g}.{kind}.{value}', subset, labels.loc[subset.index] == value)
        for low, high in ((.3, .5), (.5, .7)):
            subset = group[group.home_xg.notna() & group.away_xg.notna()]
            add(f'margin.changed.{low:g}_to_{high:g}', subset, (abs(subset.xg_margin) > low) & (abs(subset.xg_margin) <= high))
        paired = group[group.shot_reason.eq('') & group.home_xg.notna()]
        for lens in ('xg', 'shot_verdict'):
            add(f'pre.{lens}.disagree', paired, paired[lens] != paired.xg_pre)
            for whole in VERDICTS[:3]:
                for pre in VERDICTS[:3]:
                    add(f'pre.{lens}.{whole}.{pre}', paired, (paired[lens] == whole) & (paired.xg_pre == pre))
        add('pre.early_share', paired, paired.early)
        add('pre.pre_level', paired, paired.xg_pre == 'level')
        add('pre.whole_level', paired, paired.shot_verdict == 'level')
        add('pre.direction_flip', paired, ((paired.shot_verdict == 'won') & (paired.xg_pre == 'lost')) | ((paired.shot_verdict == 'lost') & (paired.xg_pre == 'won')))
        add('pre.to_level', paired, (paired.shot_verdict != 'level') & (paired.xg_pre == 'level'))
        add('pre.from_level', paired, (paired.shot_verdict == 'level') & (paired.xg_pre != 'level'))
        for label, subset in [('late', paired[~paired.early]), ('early', paired[paired.early]),
                              ('goalless', paired[np.isinf(paired.first_goal)])]:
            add(f'pre.{label}.disagree', subset, subset.shot_verdict != subset.xg_pre)
        add('vintage.verdict_disagree', paired, paired.xg != paired.shot_verdict)
        add('vintage.xg_mae', paired, (abs(paired.shot_home - paired.home_xg) + abs(paired.shot_away - paired.away_xg)) / 2)
        for name in candidates:
            paired = group[group.home_xg.notna() & group.away_xg.notna()]
            add(f'candidate.{name}.real', paired, paired[f'll_{name}'])
            add(f'candidate.{name}.xg', paired, paired[f'xll_{name}'])
            add(f'candidate.{name}.delta_real', paired, paired[f'll_{name}'] - paired.ll_model)
            add(f'candidate.{name}.delta_xg', paired, paired[f'xll_{name}'] - paired.xll_model)


def rankings(frame, candidates, output):
    rng = np.random.default_rng(7)
    results, noise = [], []
    for label, subset in [('all', frame), ('2015-2023', frame[frame.season < 2024]), ('2024-2025', frame[frame.season >= 2024])]:
        subset = subset[subset.home_xg.notna() & subset.away_xg.notna()]
        real = subset[[f'll_{name}' for name in candidates]].to_numpy()
        xg = subset[[f'xll_{name}' for name in candidates]].to_numpy()
        clusters = subset.league + ':' + subset.season.astype(str)
        codes, _ = pd.factorize(clusters)
        n = np.bincount(codes)
        a = np.array([real[codes == i].sum(axis=0) for i in range(len(n))])
        b = np.array([xg[codes == i].sum(axis=0) for i in range(len(n))])
        picks = rng.integers(0, len(n), size=(2000, len(n)))
        boot_a = a[picks].sum(axis=1) / n[picks].sum(axis=1)[:, None]
        boot_b = b[picks].sum(axis=1) / n[picks].sum(axis=1)[:, None]
        correlations = np.array([spearmanr(x, y).statistic for x, y in zip(boot_a, boot_b)])
        ma, mb = real.mean(axis=0), xg.mean(axis=0)
        results.append({'cohort': label, 'n': len(subset), 'clusters': len(n),
                        'spearman': spearmanr(ma, mb).statistic, 'spearman_ci': np.quantile(correlations, [.025, .975]).tolist(),
                        'kendall': kendalltau(ma, mb).statistic,
                        'controlled_spearman': spearmanr(np.delete(ma, [candidates.index('elo'), candidates.index('frequency')]),
                                                         np.delete(mb, [candidates.index('elo'), candidates.index('frequency')])).statistic,
                        'real_order': [candidates[i] for i in np.argsort(ma)], 'xg_order': [candidates[i] for i in np.argsort(mb)]})
        base = candidates.index('model')
        # Paired cluster bootstrap ratios measure precision of selection contrasts, not score levels.
        for i, name in enumerate(candidates):
            if i == base:
                continue
            da, db = a[:, i] - a[:, base], b[:, i] - b[:, base]
            mean_a, mean_b = (ma[i] - ma[base]), (mb[i] - mb[base])
            se_a = np.sqrt(len(n) / (len(n) - 1) * np.square(da - n * mean_a).sum()) / n.sum()
            se_b = np.sqrt(len(n) / (len(n) - 1) * np.square(db - n * mean_b).sum()) / n.sum()
            # Recenter each resampled cluster on that replicate's ratio estimate.
            dra, drb, ns = da[picks], db[picks], n[picks]
            ba, bb = dra.sum(axis=1) / ns.sum(axis=1), drb.sum(axis=1) / ns.sum(axis=1)
            sa = np.sqrt(np.square(dra - ns * ba[:, None]).sum(axis=1)) / ns.sum(axis=1)
            sb = np.sqrt(np.square(drb - ns * bb[:, None]).sum(axis=1)) / ns.sum(axis=1)
            ratio = sb / sa
            noise.append({'cohort': label, 'candidate': name, 'real_delta': mean_a, 'xg_delta': mean_b,
                          'real_se': se_a, 'xg_se': se_b, 'se_ratio': se_b / se_a,
                          'se_ratio_ci_low': np.quantile(ratio, .025), 'se_ratio_ci_high': np.quantile(ratio, .975),
                          'variance_reduction': 1 - (se_b / se_a)**2})
    (output / 'rankings.json').write_text(json.dumps(results, indent=2) + '\n')
    pd.DataFrame(noise).to_csv(output / 'noise.csv', index=False)


def write_tables(est, contracts, output):
    table = est.table().set_index(['scope', 'metric'])
    lines = ['# Eleven-season miss report: complete contract tables', '',
             'Generated by `forecast_calibration.miss_report`. See [the report](eleven-season-miss-report.md) for definitions, sources and limitations.', '',
             'Every number is estimate ± one clustered SE; counts are at the observed sample size. H/D/A means home/draw/away. Verdict columns are won/level/lost/unknown, relative to the pre-match favourite. The pre-goal rows use the draft early-as-level convention for audit only. No pre-goal field is recommended for the site.', '',
             'Aggregate scopes cluster by league-season; a single league-season clusters by forecast origin. Sample and coverage counts are exact denominators. Zero empirical SEs for unobserved cells are not evidence of zero population risk.', '']
    for scope, record in contracts.items():
        def cell(metric, digits=1):
            row = table.loc[(scope, metric)]
            if pd.isna(row.estimate):
                return '—'
            se = '—' if pd.isna(row.se) else f'{row.se:.{digits}f}'
            return f'{row.estimate:.{digits}f} ± {se}'
        info = record['misses']
        clusters = table.loc[(scope, 'accuracy')]
        lines += [f'## {scope}', '',
                  f"{record['n']:,} matches; {info['xg_scored']['n']:,} with xG; {info['goals']['team_games']:,} team-games. {int(clusters.clusters)} {clusters.cluster_unit} clusters.", '',
                  '| Call / result | H | D | A |', '| --- | ---: | ---: | ---: |']
        for i, label in enumerate(('Home', 'Draw', 'Away')):
            lines.append('| ' + label + ' | ' + ' | '.join(cell(f'confusion.{i}.{j}') for j in range(3)) + ' |')
        lines += ['', '| Outcomes | H | D | A |', '| --- | ---: | ---: | ---: |']
        for name in ('expected', 'actual', 'actual_minus_expected'):
            lines.append('| ' + name + ' | ' + ' | '.join(cell(f'outcomes.{name}.{j}') for j in range(3)) + ' |')
        lines += ['', '| Kind / lens | Won | Level | Lost | Unknown |', '| --- | ---: | ---: | ---: | ---: |']
        for kind in KINDS:
            for lens in ('xg', 'xg_pre'):
                lines.append(f'| {kind} / {lens} | ' + ' | '.join(cell(f'kinds.{kind}.{lens}.{v}') for v in VERDICTS) + ' |')
        lines += ['', '| Goal measure, per team-game | Estimate ± SE |', '| --- | ---: |']
        for name in ('predicted', 'goals', 'xg', 'mae_goals', 'mae_xg', 'bias_goals', 'bias_xg'):
            lines.append(f'| {name} | {cell(f"goals.{name}", 4)} |')
        lines += ['', '| Score (all matches for real_scored_all; xG coverage otherwise) | Model | Elo | Frequency |', '| --- | ---: | ---: | ---: |']
        for name in ('real_scored_all', 'real_scored', 'xg_scored'):
            lines.append(f'| {name} | ' + ' | '.join(cell(f'{name}.{c}', 5) for c in ('model', 'elo', 'frequency')) + ' |')
        lines += ['']
    (output / 'contract-tables.md').write_text('\n'.join(lines))


def analyze(args, data, artifact):
    output = args.out_dir
    parts = [pd.read_csv(output / 'replay' / f'{league}_{season}.csv') for league, season in data.groupby(['league', 'season']).groups]
    frame = data.merge(pd.concat(parts), on=KEYS, validate='one_to_one')
    if len(frame) != 19763 or frame[KEYS].duplicated().any():
        raise ValueError('Incomplete/duplicate replay')
    prefix = dc_prefix(artifact['xg_weight'], artifact['xg_scale'])
    p_dc = frame[[f'{prefix}_{c}' for c in 'hda']].to_numpy()
    elo = frame[[f'elo_{c}' for c in 'hda']].to_numpy()
    probabilities = {'model': blend(p_dc, elo, artifact['no_odds_weights']['main']), 'elo': elo,
                     'frequency': frame[[f'frequency_{c}' for c in 'hda']].to_numpy()}
    # Controlled alternatives: the same fixed main/Elo ratio, no fitting or model selection.
    for weight, scale in [(0, 1), (.25, 1), (.5, 1), (.75, 1), (1, 1), (.5, 1.3), (1, 1.3), (.75, 1.5)]:
        prefix = dc_prefix(weight, scale)
        probabilities[f'w{weight:g}s{scale:g}'] = blend(frame[[f'{prefix}_{c}' for c in 'hda']].to_numpy(), elo,
                                                       artifact['no_odds_weights']['main'])
    frame = frame.copy()
    p = probabilities['model']
    frame[['p_h', 'p_d', 'p_a']] = p
    frame['call'] = p.argmax(axis=1)
    frame['favourite'] = np.where(p[:, 0] >= p[:, 2], 0, 2)
    frame['kind'] = np.where(frame.call == frame.y, 'called', np.where(frame.call == 1, 'missed_draw_call',
                             np.where(frame.y == 1, 'draw', 'upset')))
    frame['xg_margin'] = (frame.home_xg - frame.away_xg) * np.where(frame.favourite == 0, 1, -1)
    frame['xg'] = verdict(frame.xg_margin, .5)
    shot_rows = [shots(row, args.cache_dir) for row in frame.itertuples(index=False)]
    frame = pd.concat([frame, pd.DataFrame(shot_rows)], axis=1)
    orient = np.where(frame.favourite == 0, 1, -1)
    frame['xg_pre'] = verdict((frame.pre_home - frame.pre_away) * orient, .5)
    frame.loc[frame.early, 'xg_pre'] = 'level'  # Draft definition, retained for the research comparison.
    frame['shot_verdict'] = verdict((frame.shot_home - frame.shot_away) * orient, .5)
    valid = frame.home_xg.notna() & frame.away_xg.notna()
    if valid.sum() != 19759:
        raise ValueError('Expected 19,759 validated observed-xG joins')
    q = np.full((len(frame), 3), np.nan)
    q[valid] = chances(frame.loc[valid, 'home_xg'].to_numpy(), frame.loc[valid, 'away_xg'].to_numpy())
    frame[['xg_p_h', 'xg_p_d', 'xg_p_a']] = q
    for name, prob in probabilities.items():
        if not np.isfinite(prob).all() or (prob <= 0).any() or not np.allclose(prob.sum(axis=1), 1):
            raise ValueError(f'Invalid {name} probabilities')
        frame[f'll_{name}'] = -np.log(prob[np.arange(len(frame)), frame.y.to_numpy(int)])
        frame[f'xll_{name}'] = -(q * np.log(prob)).sum(axis=1)
    balanced_loss = frame.groupby(['league', 'season']).ll_model.mean().mean()
    if not np.isclose(balanced_loss, artifact['metrics']['no_odds_log_loss'], atol=1e-10, rtol=0):
        raise ValueError('Saved calibration loss does not reproduce')
    est = Estimates(frame)
    contracts = contract(est)
    diagnostics(est, list(probabilities))
    est.table().to_csv(output / 'estimates.csv', index=False)
    (output / 'contract.json').write_text(json.dumps(contracts, indent=2, allow_nan=False) + '\n')
    rankings(frame, list(probabilities), output)
    write_tables(est, contracts, output)
    frame.to_csv(output / 'matches.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    frame[frame.shot_reason.ne('')][KEYS + ['understat_id', 'shot_reason']].to_csv(output / 'shot_exclusions.csv', index=False)
    coverage = frame.groupby(['league', 'season']).agg(n=('y', 'size'), xg=('home_xg', 'count'),
               shots=('shot_home', 'count'), early=('early', 'sum'), replay_max_drift=('replay_max_drift', 'max'))
    coverage.to_csv(output / 'coverage.csv')
    manifests = {path.stem: json.loads(path.read_text()) for path in sorted((output / 'replay').glob('*.json'))}
    manifest = {'dataset_sha256': digest(args.dataset), 'artifact_sha256': digest(ARTIFACT),
                'calibration_version': artifact['version'], 'calibration_balanced_loss': balanced_loss, 'replay_inputs': manifests,
                'analysis_code_sha256': digest(__file__), 'shot_hashes': dict(zip(frame.understat_id.dropna().astype(int).astype(str),
                    frame.loc[frame.understat_id.notna(), 'shot_hash'].fillna('excluded'))),
                'seed': 7, 'bootstrap_replicates': 2000, 'python': platform.python_version(),
                'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'dependencies': {name: version(name) for name in ('numpy', 'pandas', 'scipy')},
                'outputs': {p.name: digest(p) for p in sorted(output.glob('*')) if p.is_file() and p.name != 'manifest.json' and not p.name.endswith('.log')}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(coverage.to_string(), flush=True)
    print(est.table().query("scope == 'all' and (metric.str.startswith('goals.') or metric.str.startswith('pre.') or metric.str.startswith('vintage.'))").to_string(index=False), flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, default=Path('out/miss-report'))
    args = parser.parse_args()
    analyze(args, pd.read_csv(args.dataset), json.loads(ARTIFACT.read_text()))
