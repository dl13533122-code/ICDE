#!/usr/bin/env python3
"""Supplementary execution details, using the same design as the main figures."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import matplotlib.pyplot as plt
from render_figures import ROOT, CW, C, AUDIT, axes, clean, title, handle, save


def render(out):
    comparison_path = ROOT / 'data/supplement_execution/paired_comparisons.json'
    reuse_path = ROOT / 'data/fig6_physical_execution/reuse_pairs.json'
    comparisons = json.loads(comparison_path.read_text())['comparisons']
    reuse = json.loads(reuse_path.read_text())['metrics']
    assert len(comparisons) == 8
    fig = plt.figure(figsize=(CW, 3.05))
    ax = axes(fig, [.76, 1.56, 2.55, 1.08])
    title(ax, 'a', 'Accuracy and execution')
    styles = [('MSE', C['H'], 'o', -.21),
              ('App. bytes', C['U'], 's', 0),
              ('Online time', C['FULL'], '^', .21)]
    fig.legend(handles=[handle(n, col, mark, 'None', n != 'MSE')
                        for n, col, mark, _ in styles],
               loc='upper left', bbox_to_anchor=(.185, 1.005),
               ncol=3, fontsize=7.1, columnspacing=.9)
    rows = []
    for i, r in enumerate(comparisons):
        entries = [[r['ideal_error_ratio']], r['ratios']['max_application_kib'],
                   r['ratios']['online_seconds']]
        for (name, col, mark, offset), values in zip(styles, entries):
            vals = np.asarray(values, dtype=float)
            assert len(vals) == (1 if name == 'MSE' else 10)
            med = float(np.median(vals))
            ax.errorbar(med, i + offset,
                        xerr=[[med - min(vals)], [max(vals) - med]],
                        fmt=mark, color=col, markerfacecolor=col if name == 'MSE' else 'white',
                        ms=3.1, markeredgewidth=.65, capsize=1.4, elinewidth=.65, zorder=4)
        price = '0' if r['lambda_exact'] == '0' else '0.1'
        fam = 'Cat.' if r['family'] == 'class' else 'Range'
        place = 'B' if r['placement'] == 'balanced' else 'S'
        rows.append(f'{fam} {place} {price}')
    ax.axvspan(.15, 1, color=C['H'], alpha=.035, lw=0)
    ax.axvline(1, color=C['muted'], lw=.75, ls=(0, (3, 2)))
    ax.axhline(3.5, color=C['grid'], lw=.8)
    ax.set(xlim=(.15, 1.82), ylim=(7.6, -.65), yticks=range(8), yticklabels=rows,
           xticks=[.25, .5, 1, 1.5])
    ax.set_xlabel('Adaptive / fixed U (lower is better)', labelpad=3)
    clean(ax, 'x')

    ax = axes(fig, [.76, .37, 2.55, .66])
    title(ax, 'b', 'Reuse savings (10 pairs)')
    gains = {}
    for i, key in enumerate(['max_application_kib', 'max_tls_kib', 'online_seconds']):
        ratios = np.asarray(reuse[key], dtype=float)
        assert len(ratios) == 10
        savings = 100 * (1 - 1 / ratios)
        median = float(np.median(savings))
        # Deterministic vertical displacement separates coincident observations;
        # each horizontal position remains the exact paired measurement.
        offsets = np.linspace(-.15, .15, len(savings))
        ax.plot([min(savings), max(savings)], [i, i], color=C['H'], lw=.8, zorder=2)
        ax.scatter(savings, i + offsets, s=15, color=C['H'], alpha=.65,
                   edgecolors='white', linewidths=.3, zorder=3)
        ax.plot([median, median], [i - .23, i + .23], color=C['ink'], lw=1.25, zorder=5)
        ax.text(max(savings) + 1.4, i, f'{median:.2f}%',
                ha='left', va='center', fontsize=7.6, color=C['H'], weight='bold')
        gains[key] = {'n': 10, 'median_percent': median,
                      'min_percent': float(min(savings)), 'max_percent': float(max(savings)),
                      'paired_savings_percent': list(savings)}
    ax.set(xlim=(0, 54), ylim=(2.65, -.75), yticks=range(3),
           yticklabels=['App. bytes', 'TLS bytes', 'Time'], xticks=[0, 10, 20, 30, 40, 50])
    ax.set_xlabel('Saved vs. no reuse (%)', labelpad=3)
    clean(ax, 'x')
    AUDIT['input_files'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in [comparison_path, reuse_path]}
    AUDIT['annotations']['reuse'] = gains
    AUDIT['data_definition'] = {
        'comparisons': 8, 'modeled_mse_ratios': 8, 'execution_paired_ratios': 160,
        'reuse_paired_ratios': 30,
        'intervals': 'Full range of ten paired repetitions, not confidence intervals',
        'savings_formula': '100 * (1 - 1 / (no_reuse_i / reuse_i)); transform before median',
        'vertical_offsets': 'Display separation only; all x values are unchanged'}
    save(fig, 'supplement_execution', out)
    assert not AUDIT['artist_boundary_warnings'], AUDIT['artist_boundary_warnings']
    (out / 'supplement_plot_validation.json').write_text(json.dumps(AUDIT, indent=2) + '\n')
    print(json.dumps({'figure': 'supplement_execution', 'comparisons': 8,
                      'reuse_pairs_per_metric': 10, 'range_checks': AUDIT['data_range_checks'],
                      'boundary_warnings': AUDIT['artist_boundary_warnings']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=ROOT / 'output')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    render(args.out)
