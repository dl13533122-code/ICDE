"""Typeset verified public plans; physical cells remain missing."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DRAFT = ROOT / 'manuscript/revision_joint_ablation_20261013_v1'
data = json.loads((ROOT / 'evidence/joint_ablation_20261013_v1/planning_matrix.json').read_text())
rows = data['rows']
assert len(rows) == 6 and data['physical_cases_admitted'] == 0

tex = r'''\begin{table*}[t]\centering\footnotesize
\caption{Strict anchored ablation: public planning only, with the same configured-rational objective and 4096-byte conservative host grid. Ideal error sums all frozen query-coordinate pairs (55 for E370; $100\times2=200$ for I54). App bytes are modeled endpoint TX+RX including $\ell_0$. No new physical epoch is available for any row.}\label{tab:strict}
\begin{tabular}{llrrrrrrr}\hline
Data & Arm & Grid feasible & Ideal total error & Max node app & Max host app & Plan wall(s) & Plan CPU(s) & Partitions\\\hline
'''
names = dict(FIXED_GRAPH='Fixed graph', FIXED_PARTITION='Fixed partition', JOINT='Joint')
for r in rows:
    error = f"{r['configured_total_ideal_error']:.6g}" if r['feasible'] else '--'
    node = f"{r['max_logical_node_app_bytes']:,}" if r['feasible'] else '--'
    host = f"{r['max_physical_host_app_bytes']:,}" if r['feasible'] else '--'
    count = r['compatible_partition_count'] if r['arm'] != 'JOINT' else 'full family'
    arm = names[r['arm']] + (' (degenerate)' if r['degeneracy'] == 'DEGENERATE' else '')
    tex += f"{'E370' if r['dataset']=='electricity_full' else 'I54'} & {arm} & {'yes' if r['feasible'] else 'no'} & {error} & {node} & {host} & {r['planning_wall_seconds']:.3f} & {r['planning_cpu_seconds']:.3f} & {count}\\\\\n"
tex += r'''\hline\end{tabular}
\par\scriptsize Caps per host: E370 $0.85(4{,}350{,}208)=3{,}697{,}676.8$ bytes; I54 $0.90(1{,}000{,}832)=900{,}748.8$ bytes. Public build (shared across arms): E370 E_BUILD_WALLs wall/E_BUILD_CPUs CPU, I54 I_BUILD_WALLs wall/I_BUILD_CPUs CPU. Plan times are one observed local planning run per arm, with no timing CI; they exclude public construction, certificate checking and serialization. Infeasible rows have no returned mechanism or fabricated error/load measurement. Setup, provisioning, release, query, whole-process CPU/wall, TLS, SSH, empirical error CI and p99 are missing for the strict grid.
\end{table*}
'''
for ds, prefix in [('electricity_full', 'E'), ('intel', 'I')]:
    r = next(r for r in rows if r['dataset'] == ds)
    tex = tex.replace(prefix + '_BUILD_WALL', f"{r['candidate_build_wall_seconds']:.3f}")
    tex = tex.replace(prefix + '_BUILD_CPU', f"{r['candidate_build_cpu_seconds']:.3f}")
(DRAFT / 'sections/joint_ablation_table_20261013_v1.tex').write_text(tex)

p = DRAFT / 'sections/joint_ablation_20261013_v1.tex'
s = p.read_text()
s = s.replace('% The mechanically verified comparison is inserted after the planning matrix is complete.', r'''The strict fixed-partition and joint arms select identical complete mechanisms and routes on both fixtures: ideal total error is 703,506.70 on E370 and 4,363,642.91 on I54, with maximum modeled host loads 3,615,232 and 885,376 bytes. Thus these caps show no accuracy or load advantage from partition optimization. Fixing the complete graph fails the grid caps on both fixtures. I54 has only the original compatible partition and is degenerate; E370 has two, differing only in whether its final two no-edge nodes are split. B5's original leader choice and B6's uncapped minimum-load alternate are distinct designs. The retained cap configurations match the selected mechanism and routes, but are historical observations, not new strict-arm trials.

The original local host identity matches, but the read-only check of the original remote \texttt{fy1} host failed before identity verification. Consequently the strict $3\times2$ physical grid is missing; no wall-time, CPU, TLS, SSH, error-CI or p99 comparison is inferred from a replacement host. The retained R6 table is historical two-host evidence with its own identities and accounting scopes. This revision is public planning only and remains incomplete pending matched physical evidence and current web review.''')
p.write_text(s)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'pdf.fonttype': 42})
fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.35), constrained_layout=True)
for ax, ds, label in zip(axes, ['electricity_full', 'intel'], ['Electricity-370: 55 pairs', 'Intel-54: 200 pairs']):
    rr = [r for r in rows if r['dataset'] == ds]
    values = [r['configured_total_ideal_error'] for r in rr[1:]]
    bars = ax.bar([0, 1], values, color=['#426B93', '#48A099'], width=.55)
    ax.set_xticks([0, 1], ['Fixed partition', 'Joint'])
    ax.set_ylabel('Planned total ideal Gaussian error')
    ax.set_title(label, fontsize=10)
    ax.set_ylim(0, max(values) * 1.8)
    ax.ticklabel_format(axis='y', style='sci', scilimits=(0, 0))
    ax.grid(axis='y', alpha=.18)
    for b, v in zip(bars, values):
        ax.text(b.get_x()+b.get_width()/2, v*1.035, f'{v:.5g}', ha='center', fontsize=8)
    ax.text(.5, .93, 'Fixed graph: grid infeasible' + ('; degenerate' if ds=='intel' else ''),
            transform=ax.transAxes, ha='center', va='top', fontsize=8)
    ax.text(.5, .79, 'Identical selected mechanism and routes', transform=ax.transAxes,
            ha='center', va='top', fontsize=8)
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
fig.savefig(DRAFT / 'figures/joint_ablation_20261013_v1.pdf')
fig.savefig(DRAFT / 'figures/joint_ablation_20261013_v1.png', dpi=180)
plt.close(fig)
with (ROOT / 'evidence/joint_ablation_20261013_v1/typesetting.json').open('w') as f:
    json.dump(dict(script=str(pathlib.Path(__file__).relative_to(ROOT)), source='planning_matrix.json',
                   table='manuscript/revision_joint_ablation_20261013_v1/sections/joint_ablation_table_20261013_v1.tex',
                   figure='manuscript/revision_joint_ablation_20261013_v1/figures/joint_ablation_20261013_v1.pdf',
                   figure_scope='public planning, ideal total loss only; no empirical physical values'), f, indent=2)
print('public table and planning figure rendered')
