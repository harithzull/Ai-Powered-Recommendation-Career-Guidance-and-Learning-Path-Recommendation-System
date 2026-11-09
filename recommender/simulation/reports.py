"""CSV exports and descriptive diagnostics, never an accuracy estimate."""
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import statistics

from recommender.engine.config import configuration
from recommender.simulation.profiles import GENERATOR_VERSION

REPORT_NAMES = ('synthetic_profiles_100.csv', 'assessment_results_100.csv', 'recommendation_results_100.csv',
                'evaluation_summary.json', 'evaluation_summary.md')


def validate_output_paths(directory, source):
    directory, source = Path(directory).resolve(), Path(source).resolve(strict=True)
    if directory.exists() and not directory.is_dir():
        raise ValueError('Report destination must be a directory')
    for name in REPORT_NAMES:
        target = directory/name
        if target.is_symlink() or target.resolve() == source or (target.exists() and target.samefile(source)):
            raise ValueError('Report output must not alias the source database or use symbolic-link files')


def distribution(values):
    return {'count': len(values), 'min': min(values), 'max': max(values), 'mean': statistics.mean(values),
            'median': statistics.median(values), 'population_stddev': statistics.pstdev(values)} if values else {'count': 0}


def summarize(profiles, runs, checks, metadata):
    records = [r for run in runs for r in run['recommendations']]
    by_profile = defaultdict(dict)
    titles = {r['career_id']: r['career'].title for r in records}
    top_one, top_five = Counter(), Counter()
    for run in runs:
        by_profile[run['profile_id']][run['mode']] = run
        ids = tuple(r['career_id'] for r in run['recommendations'])
        if ids:
            top_one[ids[0]] += 1
            top_five.update(ids)
    pairs = []
    unexplained = []
    for profile_id, modes in by_profile.items():
        if set(modes) != {'quick', 'detailed'}:
            continue
        quick, detailed = modes['quick'], modes['detailed']
        qids, dids = [r['career_id'] for r in quick['recommendations']], [r['career_id'] for r in detailed['recommendations']]
        intersection = len(set(qids) & set(dids))
        differences = {t: round(detailed['assessment']['scores'][t]-quick['assessment']['scores'][t], 2) for t in 'RIASEC'}
        pairs.append({'profile_id': profile_id, 'overlap_count': intersection,
            'overlap_fraction': intersection/max(1, min(len(qids), len(dids))),
            'jaccard': intersection/max(1, len(set(qids) | set(dids))), 'identical_order': qids == dids,
            'holland_code_equal': quick['assessment']['holland_code'] == detailed['assessment']['holland_code'],
            'score_differences_detailed_minus_quick': differences})
        if all(v == 0 for v in differences.values()) and qids != dids:
            unexplained.append(profile_id)
    def frequencies(counter):
        return [{'career_id': career, 'title': titles[career], 'count': n} for career, n in
                sorted(counter.items(), key=lambda item: (-item[1], titles[item[0]].casefold(), item[0]))]
    def percent(predicate, rows):
        return round(100*sum(bool(predicate(r)) for r in rows)/len(rows), 4) if rows else 0
    evidence = {
        'runs_with_any_industry_fallback_pct': percent(lambda run: any(r['riasec']['method'] == 'industry_fallback' for r in run['recommendations']), runs),
        'recommendations_using_industry_fallback_pct': percent(lambda r: r['riasec']['method'] == 'industry_fallback', records),
        'runs_with_any_confirmed_skill_match_pct': percent(lambda run: any(r['matched_skills'] for r in run['recommendations']), runs),
        'recommendations_with_confirmed_skill_match_pct': percent(lambda r: bool(r['matched_skills']), records),
        'runs_with_unavailable_scoring_component_pct': percent(lambda run: any(not c['available'] for r in run['recommendations'] for c in r['components'].values()), runs),
        'recommendations_with_unavailable_scoring_component_pct': percent(lambda r: any(not c['available'] for c in r['components'].values()), records),
        'runs_with_any_unavailable_evidence_pct': percent(lambda run: any(r['explanation']['unavailable_evidence'] for r in run['recommendations']), runs),
        'explanation_structures_complete_pct': percent(lambda r: all(k in r['explanation'] for k in ('summary', 'supporting_evidence', 'uncertain_suggestions', 'unavailable_evidence', 'score_meaning')), records),
    }
    # Cross-mode equality is expected for many profiles. Report concentration
    # separately within each mode across distinct students.
    identical = {}
    for mode in sorted({run['mode'] for run in runs}):
        groups = defaultdict(list)
        for run in runs:
            if run['mode'] == mode:
                groups[tuple(r['career_id'] for r in run['recommendations'])].append(run['profile_id'])
        identical[mode] = {'distinct_top_five_sequences': len(groups),
            'profiles_in_shared_top_five_groups': sum(len(ids) for ids in groups.values() if len(ids) > 1),
            'groups': [{'career_ids': list(sequence), 'profile_ids': ids} for sequence, ids in groups.items() if len(ids) > 1]}
    warnings = []
    tied_runs = all_tied_runs = high_scores_without_skills = 0
    for run in runs:
        scores = [sum(c['contribution_points'] for c in row['components'].values()) for row in run['recommendations']]
        tied_runs += any(math.isclose(scores[a], scores[b], abs_tol=1e-9) for a in range(len(scores)) for b in range(a))
        all_tied_runs += bool(scores) and all(math.isclose(scores[0], value, abs_tol=1e-9) for value in scores)
        high_scores_without_skills += sum(row['final_score'] == 100 and not row['components']['skill']['available'] for row in run['recommendations'])
    if runs and max(top_one.values(), default=0)/len(runs) > .25:
        warnings.append('One career receives over 25% of top-one positions; inspect evidence and industry mappings before drawing conclusions.')
    if len(top_five) < min(10, metadata.get('catalog_counts', {}).get('recommender.career', len(titles))):
        warnings.append('Limited unique top-five careers; inspect catalog coverage and scoring concentration.')
    if any(v['profiles_in_shared_top_five_groups'] > len(profiles)/2 for v in identical.values()):
        warnings.append('Over half the profiles share a top-five sequence with another profile in at least one mode.')
    if unexplained:
        warnings.append('Identical six-dimensional scores produced different ordered top-five IDs for: '+', '.join(unexplained))
    if runs and tied_runs/len(runs) > .5:
        warnings.append(f'{tied_runs}/{len(runs)} runs contain tied unrounded top-five scores; deterministic title ordering can shape career frequencies.')
    if high_scores_without_skills:
        warnings.append(f'{high_scores_without_skills} recommendation rows reach 100 points without available skill evidence because missing components are renormalized; this is not verified suitability.')
    if evidence['recommendations_using_industry_fallback_pct'] > 0:
        warnings.append('Industry proxies are being used; occupation-level RIASEC evidence is unavailable or unusable.')
    if not warnings:
        warnings.append('No configured concentration/uniformity heuristic triggered; this does not establish career accuracy.')
    return {'synthetic_only': True, 'generator_version': GENERATOR_VERSION, **metadata,
        'configuration': configuration().as_dict(), 'profile_count': len(profiles), 'assessment_run_count': len(runs),
        'recommendation_run_count': len(runs), 'recommendation_row_count': len(records),
        'scenario_counts': dict(Counter(p['scenario'] for p in profiles)), 'mode_counts': dict(Counter(r['mode'] for r in runs)),
        'checks': checks, 'holland_code_frequency': dict(sorted(Counter(r['assessment']['holland_code'] for r in runs).items())),
        'holland_code_frequency_by_mode': {mode: dict(sorted(Counter(r['assessment']['holland_code'] for r in runs if r['mode'] == mode).items())) for mode in sorted({r['mode'] for r in runs})},
        'top_one_career_frequency': frequencies(top_one), 'top_five_career_frequency': frequencies(top_five),
        'unique_careers_recommended': len(top_five), 'ranking_points': distribution([r['final_score'] for r in records]),
        'ranking_points_by_mode': {mode: distribution([r['final_score'] for run in runs if run['mode'] == mode for r in run['recommendations']]) for mode in sorted({r['mode'] for r in runs})},
        'evidence': evidence, 'identical_top_five': identical,
        'tie_diagnostics': {'runs_with_any_unrounded_top_five_tie': tied_runs,
                            'runs_with_all_five_unrounded_scores_tied': all_tied_runs,
                            'hundred_point_rows_without_skill_evidence': high_scores_without_skills},
        'quick_vs_detailed': {'pair_count': len(pairs), 'identical_order_count': sum(p['identical_order'] for p in pairs),
            'same_holland_code_count': sum(p['holland_code_equal'] for p in pairs),
            'overlap_fraction': distribution([p['overlap_fraction'] for p in pairs]),
            'absolute_dimension_difference_points': distribution([abs(v) for p in pairs for v in p['score_differences_detailed_minus_quick'].values()]),
            'unexplained_ranking_difference_profile_ids': unexplained, 'profiles': pairs},
        'timing_seconds': {stage: distribution([run[stage+'_seconds'] for run in runs]) for stage in ('assessment', 'recommendation')},
        'warnings': warnings, 'warning_thresholds': {'top_one_share': .25, 'shared_sequence_profile_share': .5, 'runs_with_any_score_tie_share': .5, 'low_unique_careers': 10},
        'limitations': ['No psychometric validity, fairness, employability or real-world accuracy is established.',
            'Profiles and response patterns are designed scenarios, not a representative Malaysian student sample.',
            'Quick and Detailed share per-item ratings; additional Detailed items may change dimension means and ties.',
            'Semantics are disabled, so this evaluation does not validate embedding thresholds.',
            'Timings are local warm-process observations; repeated ranking time is excluded from first-call timings.',
            'An input signature identifies a persisted session; different modes legitimately have different signatures.',
            'Concentration thresholds are diagnostic heuristics and are not pass/fail accuracy criteria.']}


def write_csv(path, rows):
    rows = list(rows)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['profile_id', 'mode'])
        writer.writeheader()
        for row in rows:
            encoded = {k: json.dumps(v, ensure_ascii=False, sort_keys=True, allow_nan=False) if isinstance(v, (dict, list)) else v for k, v in row.items()}
            # Protect plain-text spreadsheet cells; structured JSON retains
            # original catalog labels without interpreting them as formulas.
            writer.writerow({k: "'"+v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for k, v in encoded.items()})


def markdown(summary):
    s = summary
    lines = ['# Synthetic student evaluation', '',
        f"Test date (UTC): {s['test_date']}. Seed: {s['seed']}. Generator: {s['generator_version']}.", '',
        f"**{s['profile_count']} synthetic profiles; {s['assessment_run_count']} assessment runs; {s['recommendation_run_count']} recommendation runs.**", '',
        'Software correctness observations only; no psychometric validity or career accuracy claim.', '',
        f"Engine: `{s['configuration']['version']}`. Catalog fingerprint: `{s['fingerprints']['catalog']}`.",
        f"Bank: `{s['checks']['bank_version']}`; fingerprint: `{s['fingerprints']['assessment_bank']}`.", '',
        f"Scenarios: {json.dumps(s['scenario_counts'], sort_keys=True)}.",
        f"Modes: {json.dumps(s['mode_counts'], sort_keys=True)}.",
        f"Checks: {json.dumps(s['checks'], sort_keys=True)}.", '',
        '## Holland Code frequency', '', '| Code | Runs |', '| --- | ---: |']
    lines += [f'| {code} | {n} |' for code, n in s['holland_code_frequency'].items()]
    lines += ['', '## Ten most frequent careers in top-five lists', '', '| Career | Top-five appearances |', '| --- | ---: |']
    lines += [f"| {r['title'].replace('|', '/')} | {r['count']} |" for r in s['top_five_career_frequency'][:10]]
    lines += ['', f"Unique careers in top-five lists: {s['unique_careers_recommended']}.",
        f"Ranking points distribution: {json.dumps(s['ranking_points'], sort_keys=True)}.", '', '## Quick versus Detailed', '',
        f"Pairs: {s['quick_vs_detailed']['pair_count']}; identical ordered top-five: {s['quick_vs_detailed']['identical_order_count']}; same Holland Code: {s['quick_vs_detailed']['same_holland_code_count']}.",
        f"Overlap: {json.dumps(s['quick_vs_detailed']['overlap_fraction'], sort_keys=True)}.",
        f"Absolute score differences: {json.dumps(s['quick_vs_detailed']['absolute_dimension_difference_points'], sort_keys=True)}.", '',
        '## Evidence coverage and timing', '', json.dumps(s['evidence'], indent=2), '',
        json.dumps(s['timing_seconds'], indent=2), '', '## Warnings', '']
    lines += ['- '+w for w in s['warnings']]
    lines += ['', '## Limitations and further evaluation', '']+['- '+w for w in s['limitations']]
    lines += ['', 'Collect consented student feedback and independent career-center expert relevance judgments. Review occupation profiles and aliases before tuning weights; evaluate held-out cohorts and subgroup coverage.', '']
    return '\n'.join(lines)


def export_reports(directory, profiles, runs, checks, metadata):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    summary = summarize(profiles, runs, checks, metadata)
    write_csv(directory/'synthetic_profiles_100.csv', profiles)
    write_csv(directory/'assessment_results_100.csv', ({'profile_id': run['profile_id'], 'scenario': run['scenario'],
        'mode': run['mode'], 'seed': metadata['seed'], 'scoring_version': run['assessment']['scoring_version'],
        'bank_version': checks['bank_version'], 'scores': run['assessment']['scores'], 'holland_code': run['assessment']['holland_code'],
        'counts': run['assessment']['counts'], 'ties': run['assessment']['ties'], 'responses': run['responses'],
        'assessment_seconds': run['assessment_seconds']} for run in runs))
    write_csv(directory/'recommendation_results_100.csv', ({'profile_id': run['profile_id'], 'mode': run['mode'], 'rank': rank,
        'career_id': row['career_id'], 'career_title': row['career'].title, 'final_ranking_points': row['final_score'],
        'algorithm_version': row['algorithm_version'], 'input_signature': row['input_signature'],
        'catalog_fingerprint': metadata['fingerprints']['catalog'], 'components': row['components'],
        'interest_method': row['riasec']['method'], 'riasec': row['riasec'], 'matched_skills': row['matched_skills'],
        'opportunities': row['opportunities'], 'skill_alignment': row['skill_alignment'], 'explanation': row['explanation'],
        'recommendation_seconds': run['recommendation_seconds']} for run in runs for rank, row in enumerate(run['recommendations'], 1)))
    (directory/'evaluation_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    (directory/'evaluation_summary.md').write_text(markdown(summary), encoding='utf-8')
    return summary
