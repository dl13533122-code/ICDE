#!/usr/bin/env python3
"""Reconstruct the numeric rows that the six ICDE02 manuscript figures are drawn from.

Reads the frozen, archived analysis products only:
  * analysis_v3/summary.json   (schema icde02-summary-v1)
  * physical_analysis/physical_summary.json (schema icde02-physical-summary-v1)

Nothing is re-measured, re-solved or re-simulated here: every emitted row is a
selection/aggregation of fields that already exist in the archived summary.
The selection and aggregation rules reproduce the archived plotting scripts
(plot_results_v3.py, publish_results_v3.py worker, physical_plot.py) so that the
CSV values can be compared with the caption-level numbers in the manuscript.

Standard library only. Usage:
  python3 extract_plotted_values.py --summary SUMMARY.json \
      --physical PHYSICAL_SUMMARY.json --out OUTDIR
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import pathlib
import statistics

FAMILIES = ('class', 'range', 'mixed', 'iid')
FAMILY_LABELS = {'class': 'Categories', 'range': 'Ranges', 'mixed': 'Mixed', 'iid': 'IID selections',
                 'local-class': 'Local categories', 'point-heavy': 'Point-heavy', 'identical': 'Identical',
                 'sum': 'SUM', 'groupby': 'GROUP BY'}


def num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def good(row):
    return row.get('usable') is True and row.get('standalone') is True


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(header)
        for row in rows:
            writer.writerow(['' if value is None else value for value in row])
    return len(rows)


def median(values):
    return float(statistics.median(values)) if values else None


def fig1_activation(data, out):
    """Figure 1 (label fig:activation): two 6x9 help-count heatmaps + U/H scatter."""
    phase = data.get('phase', [])
    methods = data.get('case_methods', [])
    settings = [(n, f) for n in (8, 16) for f in (0, 1, 2)]
    written = collections.Counter()
    for field, name, label in (('activation_status', 'panel_a_heatmap_general_activation.csv', 'general activation'),
                               ('uniform_help_predicted', 'panel_b_heatmap_uniform_activation.csv', 'uniform activation')):
        rows = []
        for n, f in settings:
            for j in range(9):
                theta = j / 8
                bucket = [r for r in phase
                          if r.get('n') == n and r.get('f') == f and num(r.get('theta'))
                          and abs(r['theta'] - theta) < 1e-12]
                if field == 'activation_status':
                    known = [r for r in bucket if r.get(field) in ('help', 'no-help', 'positive', 'nonpositive')]
                    help_count = sum(r[field] in ('help', 'positive') for r in known)
                else:
                    known = [r for r in bucket if isinstance(r.get(field), bool)]
                    help_count = sum(bool(r[field]) for r in known)
                intensity = (help_count / 4) if len(known) == 4 else None
                rows.append([n, f, format(theta, '.6g'), theta, len(known), help_count,
                             '' if intensity is None else round(intensity, 6),
                             'ORDER_COUNT_INCOMPLETE' if intensity is None else 'OK'])
        written[name] = write_csv(
            out / name,
            ['n_owners', 'f_colluders', 'theta_label', 'theta_value', 'orders_seen_of_4',
             'orders_with_strict_gain', 'heatmap_intensity', 'row_status'], rows)
    scatter = []
    by_case = collections.defaultdict(dict)
    for r in methods:
        if r.get('suite') == 'A' and r.get('method') in ('U', 'H') and good(r):
            by_case[r['case_id']][r['method']] = r
    phase_by_case = {r['case_id']: r for r in phase}
    matched = 0
    special = 0
    for case_id, pair in sorted(by_case.items()):
        if set(pair) != {'U', 'H'}:
            continue
        x = pair['U'].get('error_normalized')
        y = pair['H'].get('error_normalized')
        if not (num(x) and num(y)):
            continue
        p = phase_by_case.get(case_id, {})
        nonuniform = (p.get('activation_status') in ('help', 'positive')
                      and p.get('uniform_help_predicted') is False)
        scatter.append([case_id, p.get('n'), p.get('f'), p.get('theta'),
                        round(x, 12), round(y, 12),
                        round(100 * (1 - y / x), 8) if x else None,
                        p.get('activation_status'),
                        int(bool(p.get('uniform_help_predicted'))),
                        int(bool(nonuniform)), 'general_only' if nonuniform else 'uniform_or_no_help'])
        matched += 1
        special += int(bool(nonuniform))
    written['panel_c_scatter_U_vs_H.csv'] = write_csv(
        out / 'panel_c_scatter_U_vs_H.csv',
        ['case_id', 'n_owners', 'f_colluders', 'theta', 'uniform_loss_over_E0', 'harmonic_loss_over_E0',
         'harmonic_gain_percent', 'activation_status', 'uniform_help_predicted', 'general_only_highlight',
         'point_class'], scatter)
    return {'matched_pairs': matched, 'general_only_pairs': special, 'rows': dict(written)}


def fig2_local_gap(data, out):
    """Figure 2 (label fig:local): triangle brackets + H candidate excess over FULL."""
    tri = [r for r in data.get('triangle', []) if r.get('verified') and r.get('width_targets_met')]
    tri = sorted(tri, key=lambda r: r['tau'])
    rows = [[r['tau_exact'], r['tau'], r.get('normalized_gap_lower'), r.get('normalized_gap_upper'),
             (float(r['normalized_gap_lower']) + float(r['normalized_gap_upper'])) / 2,
             float(r['normalized_gap_upper']) - float(r['normalized_gap_lower']),
             1.0 / 32.0, r.get('target_width'), r.get('harmonic_width'), r.get('full_width'),
             r.get('normalized_cubic_upper'), r.get('verified'), r.get('width_targets_met')] for r in tri]
    write_csv(out / 'panel_a_triangle_brackets.csv',
              ['tau_exact', 'tau', 'normalized_gap_lower', 'normalized_gap_upper', 'normalized_gap_mid',
               'normalized_gap_width', 'asymptotic_limit_1_over_32', 'target_width', 'harmonic_bracket_width',
               'full_bracket_width', 'normalized_cubic_upper', 'verified', 'width_targets_met'], rows)

    gaps = data.get('local_gaps', [])
    palette = ('local-class', 'range', 'point-heavy', 'identical')
    summary_rows = []
    point_rows = []
    admitted = 0
    for family in palette:
        for tau in sorted({r['tau'] for r in gaps if r.get('family') == family and num(r.get('tau'))}):
            bucket = [r for r in gaps if r.get('family') == family and r.get('tau') == tau
                      and r.get('usable') and num(r.get('candidate_excess_upper_normalized'))]
            if not bucket:
                continue
            by_condition = collections.defaultdict(list)
            for r in bucket:
                by_condition[r['condition_id']].append(r)
            lo = [statistics.fmean(float(r['candidate_excess_lower_normalized']) for r in g)
                  for g in by_condition.values()]
            hi = [statistics.fmean(float(r['candidate_excess_upper_normalized']) for r in g)
                  for g in by_condition.values()]
            mid = (statistics.fmean(lo) + statistics.fmean(hi)) / 2
            summary_rows.append([family, FAMILY_LABELS.get(family, family), format(tau, '.6g'), tau,
                                 len(bucket), len(by_condition), len(lo),
                                 round(statistics.fmean(lo), 12), round(statistics.fmean(hi), 12),
                                 round(100 * mid, 8), round(100 * min(lo), 8), round(100 * max(hi), 8)])
            admitted += len(bucket)
        for r in gaps:
            if r.get('family') != family:
                continue
            point_rows.append([r['case_id'], r['condition_id'], family, format(r['tau'], '.6g'), r['tau'],
                               r.get('n'), r.get('f'), int(bool(r.get('usable'))),
                               int(bool(r.get('H_standalone'))), int(bool(r.get('H_fallback'))),
                               r.get('H_candidate'), r.get('FULL_lower'), r.get('FULL_upper'),
                               r.get('candidate_excess_lower'), r.get('candidate_excess_upper'),
                               r.get('candidate_excess_lower_normalized'),
                               r.get('candidate_excess_upper_normalized'), r.get('gap_scope')])
    write_csv(out / 'panel_b_candidate_excess_summary.csv',
              ['family', 'family_label', 'tau_label', 'tau', 'admitted_rows', 'distinct_conditions',
               'band_min_x', 'mean_excess_lower_normalized', 'mean_excess_upper_normalized',
               'plotted_center_percent', 'band_low_percent', 'band_high_percent'], summary_rows)
    write_csv(out / 'panel_b_candidate_excess_points.csv',
              ['case_id', 'condition_id', 'family', 'tau_label', 'tau', 'n_owners', 'f_colluders', 'usable',
               'H_standalone', 'H_fallback', 'H_candidate', 'FULL_lower', 'FULL_upper',
               'candidate_excess_lower', 'candidate_excess_upper',
               'candidate_excess_lower_normalized', 'candidate_excess_upper_normalized', 'gap_scope'], point_rows)
    conditions = len({r.get('condition_id') for r in gaps if r.get('usable')})
    return {'triangle_brackets': len(tri), 'planned_triangle': 5, 'local_admitted': admitted,
            'local_planned': len(gaps), 'distinct_local_conditions': conditions,
            'rows': {'panel_a': len(rows), 'panel_b_summary': len(summary_rows), 'panel_b_points': len(point_rows)}}


def fig3_scale(data, out):
    """Figure 3 (label fig:scale): planning-time medians/ranges and 1,024-owner loss."""
    methods = data.get('case_methods', [])
    written = {}
    for suite, name, wanted in (('C', 'panel_a_sparse_planning_times.csv', ('U', 'H', 'LP')),
                                ('Cfull', 'panel_b_full_comparison_times.csv', ('U', 'H', 'FULL'))):
        rows = []
        for method in wanted:
            subset = [r for r in methods if r.get('suite') == suite and r.get('method') == method]
            for n in sorted({r['n'] for r in subset}):
                bucket = [r for r in subset if r['n'] == n and good(r) and num(r.get('seconds')) and r['seconds'] > 0]
                if bucket:
                    values = [float(r['seconds']) for r in bucket]
                    rows.append([suite, method, n, len(bucket), round(median(values), 6),
                                 round(min(values), 6), round(max(values), 6), len(subset), 0])
                for r in subset:
                    if r['n'] == n and 'timeout' in str(r.get('execution_status', '')).lower() and num(r.get('seconds')):
                        rows.append([suite, method, n, 0, '', '', round(float(r['seconds']), 6), len(subset), 1])
        written[name] = write_csv(
            out / name,
            ['suite', 'method', 'n_owners', 'standalone_timed', 'median_seconds', 'min_seconds',
             'max_seconds', 'planned_rows_for_method', 'is_timeout_cross'], rows)
    bars = []
    for method in ('U', 'H'):
        for family in FAMILIES:
            bucket = [r for r in methods if r.get('suite') == 'C' and r.get('n') == 1024
                      and r.get('family') == family and r.get('method') == method]
            if len(bucket) != 1 or bucket[0].get('usable') is not True or not num(bucket[0].get('error_normalized')):
                continue
            r = bucket[0]
            kind = 'standalone' if good(r) else (
                'independence_fallback' if method == 'U' and r.get('fallback') is True
                and r.get('independent_returned') is True else 'not_plotted')
            bars.append(['U' if method == 'U' else 'H', family, FAMILY_LABELS.get(family, family),
                         round(float(r['error_normalized']), 12), kind,
                         round(float(r['seconds']), 6) if num(r.get('seconds')) else '',
                         r['case_id'], int(bool(r.get('fallback'))), int(bool(good(r)))])
    written['panel_c_loss_at_1024.csv'] = write_csv(
        out / 'panel_c_loss_at_1024.csv',
        ['method', 'family', 'family_label', 'loss_over_E0', 'bar_type', 'recorded_total_seconds',
         'case_id', 'fallback', 'standalone'], bars)
    return {'rows': dict(written),
            'fallback_case_ids': [b[6] for b in bars if b[4] == 'independence_fallback'],
            'bars_plotted': len([b for b in bars if b[4] != 'not_plotted'])}


def fig4_grouping(data, out):
    """Figure 4 (label fig:group): max-host KiB vs loss frontier panels + paired reductions."""
    plans = data.get('group_plans', [])
    fronts = data.get('group_frontiers', [])
    written = {}
    for family, name in (('class', 'panel_a_categories_frontier.csv'), ('range', 'panel_b_ranges_frontier.csv')):
        selected = [r for r in plans if r.get('case_id') == f'D-n128-{family}-s1401'
                    and r.get('placement') == 'balanced']
        rows = []
        for partition, cand, label, style in (('fixed8', 'U', 'Fixed U', 'dashed'),
                                              ('adaptive', 'U', 'Adaptive U', 'solid'),
                                              ('adaptive', 'H', 'Adaptive H', 'solid'),
                                              ('adaptive', 'PORTFOLIO', 'Portfolio', 'solid')):
            points = [r for r in selected if r.get('partition') == partition
                      and r.get('candidate_family') == cand and r.get('verified') and r.get('complete')]
            for r in sorted(points, key=lambda r: r['price']):
                rows.append([label, style, r['price'], r['price_exact'], r['max_host_kib'],
                             r.get('error_normalized'), r.get('objective'), r['case_id'],
                             int(bool(r.get('method_family_complete'))), r.get('candidate_family'),
                             r.get('partition'), r.get('total_endpoint_kib'),
                             json.dumps(r.get('host_endpoint_kib')), r.get('fixed_collection_kib')
                             and json.dumps(r.get('fixed_collection_kib'))])
        frontier = next((r for r in fronts if r.get('case_id') == f'D-n128-{family}-s1401'
                         and r.get('placement') == 'balanced' and r.get('complete')
                         and r.get('method_family_complete') and r.get('coordinate_check_passed')), None)
        if frontier and frontier.get('points'):
            for p in sorted(frontier['points'], key=lambda r: r['max_host_kib']):
                rows.append(['Candidate frontier', 'dotted', '', '', p['max_host_kib'],
                             p.get('error_normalized'), p.get('objective'), frontier['case_id'],
                             '', 'frontier', '', '', '', ''])
        written[name] = write_csv(
            out / name,
            ['series', 'linestyle', 'price', 'price_exact', 'max_host_kib', 'loss_over_E0', 'priced_objective',
             'case_id', 'method_family_complete', 'candidate_family', 'partition', 'total_endpoint_kib',
             'host_endpoint_kib_json', 'fixed_collection_kib_json'], rows)
    pair_rows = []
    matched = {}
    for family in FAMILIES:
        candidates = [r for r in plans if r.get('family') == family and r.get('n') == 128
                      and not r.get('interleaved') and num(r.get('price')) and abs(r['price'] - 0.1) < 1e-12]
        pairs = collections.defaultdict(dict)
        for r in candidates:
            if not (r.get('verified') and r.get('complete')):
                continue
            if (r.get('partition'), r.get('candidate_family')) == ('fixed8', 'U'):
                pairs[(r['case_id'], r['placement'])]['base'] = r
            if (r.get('partition'), r.get('candidate_family')) == ('adaptive', 'PORTFOLIO'):
                pairs[(r['case_id'], r['placement'])]['plan'] = r
        count = 0
        for key, pair in sorted(pairs.items()):
            if set(pair) != {'base', 'plan'}:
                continue
            base, plan = pair['base'], pair['plan']
            if not all(num(r.get(k)) for r in (base, plan) for k in ('max_host_kib', 'error_normalized')):
                continue
            if base['max_host_kib'] <= 0 or base['error_normalized'] <= 0:
                continue
            mse = 100 * (1 - plan['error_normalized'] / base['error_normalized'])
            host = 100 * (1 - plan['max_host_kib'] / base['max_host_kib'])
            complete_family = bool(plan.get('method_family_complete') and base.get('method_family_complete'))
            pair_rows.append([family, FAMILY_LABELS.get(family, family), key[0], key[1],
                              round(float(base['max_host_kib']), 6), round(float(plan['max_host_kib']), 6),
                              round(float(base['error_normalized']), 12), round(float(plan['error_normalized']), 12),
                              round(mse, 8), round(host, 8), int(complete_family)])
            count += 1
        matched[family] = count
    write_csv(out / 'panel_c_paired_plan_changes.csv',
              ['family', 'family_label', 'case_id', 'placement', 'base_max_host_kib', 'plan_max_host_kib',
               'base_loss_over_E0', 'plan_loss_over_E0', 'mse_reduction_percent',
               'max_host_byte_reduction_percent', 'candidate_family_complete'], pair_rows)
    coverage = data.get('coverage', {}).get('D', {})
    return {'matched_pairs_by_family': matched,
            'verified_scalar_plans': coverage.get('verified_scalar_plans'),
            'planned_scalar_plans': coverage.get('planned_scalar_plans', 1344),
            'rows': dict(written)}


def fig5_finite(data, out):
    """Figure 5 (label fig:finite): per-dataset method means with t intervals; H-U paired panel."""
    rows = data.get('finite', [])
    families = ('sum', 'range', 'groupby', 'mixed')
    written = {}
    for dataset, name, label in (('intel', 'panel_a_intel_utility.csv', 'Intel'),
                                 ('electricity', 'panel_b_electricity_utility.csv', 'Electricity')):
        selected = {r.get('family'): r for r in rows if r.get('dataset') == dataset}
        emitted = []
        for r_index, family in enumerate(families):
            r = selected.get(family, {})
            for m_index, method in enumerate(('I', 'U', 'H')):
                m = r.get('methods', {}).get(method, {})
                if not (r.get('eligible_for_primary') and num(m.get('mean'))
                        and num(m.get('ci_low')) and num(m.get('ci_high'))):
                    continue
                emitted.append([label, family, FAMILY_LABELS.get(family, family), method,
                                r_index + (m_index - 1) * 0.21,
                                round(float(m['mean']), 12), round(float(m['ci_low']), 12),
                                round(float(m['ci_high']), 12),
                                round(float(m['mean']) - float(m['ci_low']), 12),
                                round(float(m['ci_high']) - float(m['mean']), 12),
                                m.get('ideal_normalized_error'), r.get('dimension'), m.get('batch_n'),
                                r.get('case_id')])
        written[name] = write_csv(
            out / name,
            ['dataset_label', 'family', 'family_label', 'method', 'x_position', 'weighted_mse_mean',
             'ci_low', 'ci_high', 'err_low', 'err_high', 'ideal_normalized_error', 'dimension',
             'paired_batches', 'case_id'], emitted)
    diffs = []
    for d_index, dataset in enumerate(('intel', 'electricity')):
        for f_index, family in enumerate(families):
            r = next((r for r in rows if r.get('dataset') == dataset and r.get('family') == family), {})
            pair = r.get('paired_comparisons', {}).get('H-U', {})
            ok = (r.get('eligible_for_primary') and all(num(pair.get(k)) for k in ('mean', 'ci_low', 'ci_high')))
            diffs.append([dataset, family, 4 * d_index + f_index,
                          round(float(pair['mean']), 12) if num(pair.get('mean')) else '',
                          round(100 * float(pair['mean']), 8) if num(pair.get('mean')) else '',
                          round(100 * float(pair['ci_low']), 8) if num(pair.get('ci_low')) else '',
                          round(100 * float(pair['ci_high']), 8) if num(pair.get('ci_high')) else '',
                          pair.get('batch_n'), int(bool(ok)), r.get('case_id')])
    written['panel_c_paired_H_minus_U.csv'] = write_csv(
        out / 'panel_c_paired_H_minus_U.csv',
        ['dataset', 'family', 'y_row', 'difference_over_E_ind', 'difference_percent_points',
         'ci_low_percent_points', 'ci_high_percent_points', 'paired_batches', 'plotted', 'case_id'], diffs)
    primary = sum(r.get('eligible_for_primary') is True for r in rows)
    observed = sum(r.get('observed_rows', 0) for r in rows)
    planned = sum(r.get('planned_rows', 0) for r in rows)
    return {'primary_workloads': primary, 'planned_workloads': len(rows),
            'observed_attempt_rows': observed, 'planned_attempt_rows': planned,
            'rows': dict(written)}


def fig6_physical(physical, out):
    """Figure 6 (label fig:physical): matched traffic/time panels and the partial-reuse ablation."""
    comparisons = physical.get('comparisons', [])
    written = {}
    traffic = []
    online = []
    for index, row in enumerate(comparisons):
        label = (('Cat.' if row['family'] == 'class' else 'Range')
                 + ' ' + ('B' if row['placement'] == 'balanced' else 'S')
                 + ' ' + ('0' if row['lambda_exact'] == '0' else '.1'))
        metric = row['metrics']['max_application_kib']
        n = metric['ratio']['n']
        base, alt = metric['base'], metric['alternative']
        traffic.append([index, label, row['condition_id'], row['family'], row['placement'], row['lambda_exact'],
                        n, base['median'], base['minimum'], base['maximum'],
                        alt['median'], alt['minimum'], alt['maximum'],
                        metric['ratio']['median'], metric['ratio']['minimum'], metric['ratio']['maximum'],
                        metric['reduction_percent']['median'] if metric.get('reduction_percent') else '',
                        int(bool(row.get('alternative_family_complete')))])
        ratio = row['metrics']['online_seconds']['ratio']
        online.append([index, label, row['condition_id'], ratio['n'], ratio['median'],
                       ratio['minimum'], ratio['maximum'], ratio['mean'],
                       int(bool(row.get('alternative_family_complete')))])
    traffic_n = write_csv(out / 'panel_a_matched_host_traffic.csv',
              ['row_index', 'row_label', 'condition_id', 'family', 'placement', 'lambda_exact', 'pairs_n',
               'fixed_u_median_kib', 'fixed_u_min_kib', 'fixed_u_max_kib',
               'adaptive_median_kib', 'adaptive_min_kib', 'adaptive_max_kib',
               'ratio_median', 'ratio_min', 'ratio_max', 'reduction_percent_median',
               'alternative_family_complete'], traffic)
    online_n = write_csv(out / 'panel_b_matched_online_time.csv',
              ['row_index', 'row_label', 'condition_id', 'pairs_n', 'ratio_median', 'ratio_min',
               'ratio_max', 'ratio_mean', 'alternative_family_complete'], online)
    ablation = physical.get('no_sharing', {})
    rows = []
    for metric, label, unit in (('max_application_kib', 'App. bytes', 'KiB'),
                                ('max_tls_kib', 'TLS records', 'KiB'),
                                ('online_seconds', 'Online time', 's')):
        values = ablation.get('metrics', {}).get(metric, {}).get('ratio', {})
        rows.append([label, unit, values.get('n', 0), values.get('median'), values.get('minimum'),
                     values.get('maximum'), values.get('mean'),
                     int(bool(ablation.get('same_allocation_and_routes')))])
    ablation_n = write_csv(out / 'panel_c_partial_reuse.csv',
              ['metric_label', 'unit', 'pairs_n', 'ratio_median', 'ratio_min', 'ratio_max', 'ratio_mean',
               'same_allocation_and_routes'], rows)
    written['panel_a_matched_host_traffic.csv'] = traffic_n
    written['panel_b_matched_online_time.csv'] = online_n
    written['panel_c_partial_reuse.csv'] = ablation_n
    coverage = physical.get('coverage', {})
    scopes = coverage.get('scopes', {})
    return {'paired_main_conditions': len(comparisons),
            'paired_no_sharing_conditions': 1,
            'observed_attempts': coverage.get('observed_attempts'),
            'planned_attempts': coverage.get('planned_attempts'),
            'observed_cases': coverage.get('observed_cases'),
            'main_ordinary_validated': scopes.get('main_ordinary', {}).get('validated_successes'),
            'no_sharing_validated': scopes.get('no_sharing_ordinary', {}).get('validated_successes'),
            'forced_abort_observed': scopes.get('forced_abort', {}).get('observed'),
            'fresh_retry_validated': scopes.get('fresh_retry', {}).get('validated_successes'),
            'rows': dict(written)}


def table1_design(data, out):
    """Table I (label tab:design): configurations and distinct weighted workloads."""
    cov = data.get('coverage', {})
    layout = collections.Counter()
    for r in data.get('case_methods', []):
        layout[(r.get('suite'), r.get('method'))] += 1
    specs = [('Activation', 'A', None, '216'),
             ('Budgeted approximation', 'B', None, '32'),
             ('Sparse scaling', 'C', '40x3+4', '124'),
             ('Matched FULL comparison', 'Cfull', None, '28'),
             ('Grouping and placement', 'D', None, '28'),
             ('Finite reports', 'E', None, '8')]
    rows = []
    for display, suite, config_exact, config_ascii in specs:
        entry = cov.get(suite, {})
        rows.append([display, suite, config_exact or str(entry.get('planned_cases')), config_ascii,
                     entry.get('planned_cases'), entry.get('workloads'), entry.get('conditions'),
                     entry.get('observed_cases'), entry.get('terminal_cases'),
                     'VERIFIED' if entry.get('planned_cases') is not None else 'BLOCKED'])
    write_csv(out / 'values.csv',
              ['row_label', 'suite_id', 'configurations_display', 'configurations_ascii', 'planned_cases',
               'weighted_workloads', 'privacy_workload_conditions', 'observed_cases', 'terminal_cases',
               'status'], rows)
    return {'rows': len(rows), 'cells': len(rows) * 3}


def table2_data(data, out):
    """Table II (label tab:data): full-release preprocessing and coverage."""
    cov = {r['dataset']: r for r in data.get('dataset_coverage', [])}
    elec, intel = cov.get('electricity', {}), cov.get('intel', {})
    lines = [('Raw measurement rows', 'raw_rows', 'rows'),
             ('Public owners', 'owner_count', 'owners'),
             ('Complete/qualified dates', 'valid_days', 'dates'),
             ('Evaluation dates', 'evaluation_days', 'dates'),
             ('Available evaluation owner-days', 'evaluation_available_owner_days', 'owner-days'),
             ('Evaluation roster owner-days', 'evaluation_roster_owner_days', 'owner-days')]
    rows = []
    for label, key, unit in lines:
        rows.append([label, unit, elec.get(key), intel.get(key), elec.get('dataset'), intel.get('dataset'),
                     'VERIFIED' if elec.get(key) is not None and intel.get(key) is not None else 'BLOCKED'])
    write_csv(out / 'values.csv',
              ['row_label', 'unit', 'electricity_value', 'intel_value', 'electricity_dataset',
               'intel_dataset', 'status'], rows)
    extras = [['calendar_days', elec.get('calendar_days'), intel.get('calendar_days')],
              ['qualified_rows', elec.get('qualified_rows'), intel.get('qualified_rows')],
              ['clipped_rows_or_cells', elec.get('clipped_rows_or_cells'), intel.get('clipped_rows_or_cells')],
              ['source_file', elec.get('source_file'), intel.get('source_file')],
              ['qualification_rule', elec.get('qualification_rule'), intel.get('qualification_rule')],
              ['normalization', elec.get('normalization'), intel.get('normalization')]]
    write_csv(out / 'supporting_fields.csv', ['field', 'electricity', 'intel'], extras)
    return {'rows': len(rows), 'cells': len(rows) * 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=pathlib.Path, required=True)
    parser.add_argument('--physical', type=pathlib.Path, required=True)
    parser.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()

    raw = args.summary.read_bytes()
    data = json.loads(raw)
    if data.get('schema') != 'icde02-summary-v1':
        raise SystemExit(f'unexpected summary schema: {data.get("schema")!r}')
    praw = args.physical.read_bytes()
    physical = json.loads(praw)
    if physical.get('schema') != 'icde02-physical-summary-v1':
        raise SystemExit(f'unexpected physical schema: {physical.get("schema")!r}')

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    report = {
        'schema': 'icde02-plotted-values-v1',
        'generated_by': 'extract_plotted_values.py',
        'source_summary_sha256': hashlib.sha256(raw).hexdigest(),
        'source_summary_bytes': len(raw),
        'source_physical_summary_sha256': hashlib.sha256(praw).hexdigest(),
        'source_physical_summary_bytes': len(praw),
        'method': ('Rows are selections/aggregations of archived summary fields only; no measurement, '
                   'solver or simulation is executed. Aggregation rules mirror plot_results_v3.py, the '
                   'publish_results_v3.py worker and physical_plot.py.'),
        'figures': {},
    }
    report['figures']['fig1_activation'] = fig1_activation(data, out / 'fig1_activation')
    report['figures']['fig2_local_gap'] = fig2_local_gap(data, out / 'fig2_local_gap')
    report['figures']['fig3_scale'] = fig3_scale(data, out / 'fig3_scale')
    report['figures']['fig4_grouping'] = fig4_grouping(data, out / 'fig4_grouping')
    report['figures']['fig5_finite_utility'] = fig5_finite(data, out / 'fig5_finite_utility')
    report['figures']['fig6_physical_execution'] = fig6_physical(physical, out / 'fig6_physical_execution')
    report['tables'] = {'table1_design': table1_design(data, out / 'table1_design'),
                        'table2_data': table2_data(data, out / 'table2_data')}
    (out / 'EXTRACTION_REPORT.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('method',)}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
