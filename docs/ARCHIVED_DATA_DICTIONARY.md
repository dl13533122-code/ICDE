# Archived figure and table data dictionary

This English dictionary describes the supplied figure archive. Historical
figure labels 1-6 correspond to experimental Figures 2-7 in the current paper.
Panel inputs are in `plotting/data/`, analysis outputs in `results/`, and
archived analysis scripts in `scripts/archived_analysis/`.

CSV files use UTF-8, comma separators, LF line endings, and a header row.
Numeric data retain the generating script's original representation without
added rounding. Empty cells mean that the archive did not provide a value;
no missing measurements have been interpolated. JSON files retain their
original formatting unless a distribution change is recorded in provenance.

## Units

- `*_kib`: KiB, where 1 KiB = 1024 bytes, for application or host endpoint load.
- `*_seconds` and `*_s`: seconds, including the repair, certificate, process
  startup, and serialization costs described in the paper unless stated otherwise.
- `*_over_E0`, `loss_over_E0`, `error_normalized`: dimensionless loss normalized
  by the independent baseline E0.
- `*_percent`, `percent_points`: percentages or percentage points according to
  the specific metric definition.
- `theta`, `tau`, `lambda`: correlation or budget parameters. An `*_exact`
  field is an exact rational string; `*_label` is a display label.

## Activation: `fig1_activation/`

The two heatmap CSVs each contain 54 rows. `n_owners` is 8 or 16;
`f_colluders` is 0, 1, or 2; `theta_label` and `theta_value` describe nine
values from 0 to 1 in steps of 1/8. `orders_seen_of_4` counts observed public
orders. `orders_with_strict_gain` counts improving orders using
`activation_status` for the general panel and `uniform_help_predicted` for
the uniform panel. `heatmap_intensity` is that count divided by four.
`row_status` records validity.

The U-versus-H scatter CSV contains 216 rows. Configuration identifiers and
parameters accompany `uniform_loss_over_E0`, `harmonic_loss_over_E0`, and
`harmonic_gain_percent`. `activation_status`, `uniform_help_predicted`,
`general_only_highlight`, and `point_class` preserve the original classifications.
The eight general-only cases have `general_only_highlight` equal to one.

## Local approximation: `fig2_local_gap/`

`panel_a_triangle_brackets.csv` contains five rows. `tau_exact` and `tau` give
exact and numeric budgets. The normalized gap lower/upper/mid/width fields
describe `[L_H-U_P, U_H-L_P]/E0`. The analytical limit is 1/32; the target
width is tau^3/3200. Harmonic/full bracket widths, the normalized cubic upper
bound, verification status, and target-width checks are retained.

`panel_b_candidate_excess_points.csv` contains 32 supplemental records with
case/condition identifiers, family, tau, owner count, coalition budget, and
usability. `H_standalone`, `H_fallback`, and `H_candidate` identify the standalone
solution, fallback bound, and better candidate. `FULL_lower` and `FULL_upper`
bound the full pairwise objective. Candidate-excess fields and their normalized
versions compare the returned candidate with the full pairwise optimum.
`gap_scope` explicitly distinguishes this from the difference between the
optimal H objective and the global optimum.

`panel_b_candidate_excess_summary.csv` contains 16 rows with family/tau labels,
admitted row and distinct-condition counts, band position, mean normalized
excess bounds, plotted center, and percentage band endpoints.

## Scale: `fig3_scale/`

The sparse-planning and full-comparison time CSVs contain 17 and 12 rows.
Fields record suite (`C` or `Cfull`), method (`U`, `H`, `I`, `LP`, `FULL`),
owner count, number of standalone timed completions, median/minimum/maximum
seconds, planned method rows, and timeout-cross indicators.

The 1,024-owner loss CSV contains eight rows with method, family/display label,
normalized loss, bar type, recorded total time, case identifier, and
standalone/fallback indicators.

## Grouping: `fig4_grouping/`

The category and range frontier CSVs each contain 16 rows.

| Fields | Meaning |
|---|---|
| `series`, `linestyle` | Legend series and line style |
| `price`, `price_exact` | Numeric and exact price parameter |
| `max_host_kib`, `total_endpoint_kib` | Maximum host load and total endpoint load |
| `loss_over_E0` | Normalized loss |
| `priced_objective` | Loss plus price times bytes, as defined by the archived plotting script |
| `case_id`, `partition`, `candidate_family` | Case, partition, and candidate-family identifiers |
| `method_family_complete` | Candidate-family completeness |
| `host_endpoint_kib_json`, `fixed_collection_kib_json` | Per-host and fixed-collection loads as JSON arrays |

The paired-plan CSV contains 24 rows with family, case, balanced/skewed
placement, baseline/planned maximum-host load and normalized loss, MSE
reduction, host-byte reduction, and candidate-family completeness. A negative
host-byte reduction means increased load.

## Finite-report utility: `fig5_finite_utility/`

The Intel and Electricity utility CSVs each contain 12 rows.

| Fields | Meaning |
|---|---|
| `dataset_label`, `family`, `family_label` | Dataset and query-family names |
| `method`, `x_position` | Method (`I`, `H`, `U`) and grouped plot coordinate |
| `weighted_mse_mean` | Mean of 16 paired batch means for unclipped loss |
| `ci_low`, `ci_high` | Pointwise 95% t interval |
| `err_low`, `err_high` | Lower and upper deviations from the mean |
| `ideal_normalized_error` | Ideal loss normalized by 2S/r for Intel and S/r for Electricity |
| `dimension`, `paired_batches`, `case_id` | Coordinate dimension, paired batch count (16), and case identifier |

The paired H-minus-U CSV contains eight rows with dataset, family, plot row,
normalized difference, difference in percentage points, interval endpoints,
paired-batch count, plotted flag, and case identifier.

## Physical execution: `fig6_physical_execution/`

The matched-host-traffic CSV contains eight rows. Identifiers include plot
row/label, condition, family, placement, exact lambda, and pair count.
Measurements include fixed-U and adaptive median/minimum/maximum KiB,
adaptive/fixed ratio summaries, median percentage reduction, and alternative
candidate-family completeness.

The matched-online-time CSV also contains eight rows, with the same
identification fields and median/minimum/maximum/mean adaptive/fixed time
ratios. The partial-reuse CSV has three rows for application bytes, TLS records,
and online time, with unit, pair count, no-sharing/sharing ratio summaries,
and an indicator that allocation and routes are identical.

Current `reuse_pairs.json` retains ten paired ratios for each of the three
metrics. `supplement_execution/paired_comparisons.json` contains eight modeled
MSE ratios and 160 paired execution ratios for the supplementary figure.

## Tables

`tables/table1_design/values.csv` contains six rows, with study label, suite,
configuration display/ASCII values, planned cases, weighted workloads,
privacy-workload conditions, observed/terminal cases, and status. For example,
`40x3+4` represents `$40\times3+4$` in the manuscript.

`values_complete.csv` adds `weighted_workloads_source` and fills the sole
missing displayed workload count with `8` for finite reports, from
`summary.coverage.E.primary_instances`. The original CSV keeps that cell empty
for byte-for-byte extraction checks. The complete view supplies all 12 numeric
cells shown in Table I.

`table1_design/source.tex` is the archived table environment, including its
caption and label. `sources.json` records field origins, summary hash, and
checks against coverage records, factual macros, and intermediate table data.

`tables/table2_data/values.csv` has six rows and two numeric columns, with row
label, unit, Electricity/Intel values and dataset names, and status.
`supporting_fields.csv` has six rows for calendar days, qualified rows,
clipped rows/cells, source file, qualification rule, and normalization.
Empty cells indicate unavailable archived values. The accompanying LaTeX and
JSON record the archived table and its cell-level sources and checks.

## Intermediate analysis: `results/analysis/`

| File | Rows | Contents |
|---|---:|---|
| `phase.csv` | 216 | Case/workload/condition identifiers, parameters, activation status, B, gamma, and uniform prediction/ratio |
| `case_methods.csv` | 1525 | Method, assembly, sources, execution/solver statuses, usability, standalone/fallback flags, exact/normalized errors, bounds, privacy checks, runtime, allocation checks, and active edges |
| `local_gaps.csv` | 32 | H candidate/fallback values, FULL bounds, excess bounds, normalization, theorem domain, and gap scope |
| `group_plans.csv` | 1344 | Placement, partition, candidate family, price, completeness, verification, errors, endpoint loads, objective, interval count, and active edges |
| `triangle.csv` | 5 | Exact/numeric brackets, status, verification, and target-width checks |
| `portfolios.csv` | 400 | Portfolio selection, usability, standalone/fallback flags, family completeness, error, and timing completeness |
| `dataset_coverage.csv` | 2 | Dataset source, owner/row/date counts, available/roster owner-days, clipping counts, coordinates, qualification, and normalization |
| `factual_strings.tex` | - | Archived numeric macros used to cross-check Tables I and II |
| `table_design.tex`, `table_coverage.tex` | - | Intermediate LaTeX fragments; pending physical-measurement labels describe an earlier analysis state, not the final results |

## Main summary: `results/analysis_v3/summary.json`

The file has 7,795,813 bytes and schema `icde02-summary-v1`. It contains coverage,
phase, method, local-gap, grouping/frontier, portfolio, triangle, finite-report,
dataset, physical, publication-overlay, input-file, identity, hash, creation-time,
and issue records. The issues list is empty.

Coverage spans suites A/B/C/Cfull/D/E, triangle, and physical measurements.
It records planned/observed/terminal cases, workloads and conditions, and
per-method counts for completions, standalone/fallback results, finite brackets,
timeouts, errors, missing/contradictory records, and usable records.

There are 216 phase records, 1,525 method records, eight finite-report records,
and two dataset-coverage records. Finite records include paired batch means,
clipped means, status counts, seeds, paired comparisons, planned/observed/abort
rows, and ideal values. Dataset coverage supplies Table II.

The publication overlay replaces only `C-n1024-range-s1301-r0` and
`C-n1024-mixed-s1301-r0`. It retains original portfolio records, base/overlay
hashes, and `timing_includes_original_precision_failures`.

## Physical analysis: `results/physical_analysis/`

`physical_summary.json` has 1,146,929 bytes and schema
`icde02-physical-summary-v1`. It records complete status, 202 attempts, 17 cases,
eight comparisons, three no-sharing metrics for one condition, coverage,
metric scope, pairing, candidate policy, hosts/closures, and 93 input files.
Unexpected ledger entries, unexpected raw rows, and issues are empty.

`physical_attempts.csv` contains 202 rows with identifiers, attempt kind/order,
observed/raw/ledger statuses, charging, structural validity, primary eligibility,
metrics, issues, application/TLS bytes by host, fixed collection load, exact
frame checks, exact weighted squared error, exact Qz checks, runtime, raw-file
references, exposed owners, and non-success endpoint scope. JSON strings encode
metrics and issues. Status values include `SUCCESS` and `FORCED_ABORT`.

`physical_cases.csv` has 17 rows with configuration/runtime checks, planned
and observed attempts, exact and normalized ideal error, workload identifiers,
active edges, owner counts, collection load, allocation/route/configuration
hashes, candidate-family completeness, finite-bound checks, machine/TLS hashes,
statistics, charging, and model-frame checks.

`physical_comparisons.csv` contains eight condition records with family,
placement, exact lambda, baseline/alternative cases, planned pairs, ideal-error
ratio, family-completeness flags, and metrics encoded as JSON.

The physical-facts JSON, TeX, and text files describe the same snapshot:
202/202 attempts; 17/17 cases; 160 main ordinary attempts; ten no-sharing
attempts; 16 forced aborts; 16 fresh retries; 176 frame checks with no
mismatches; and no readback issues.

`processing_receipts.json` records two actual analysis runs, their commands,
process identifiers, exit codes, peak RSS, resource limits, cleanup, and
three script hashes. Peak RSS was 317,496 KiB for the summary script and
92,820 KiB for the physical plotting script.

`input_snapshot.json` records input paths and hashes. Its original size was
595,074 bytes. The historical machine-root label is normalized in this English
release; file hashes and measurements remain unchanged. Original and
distributed hashes are recorded in provenance.

## Scripts and manifests

`extract_plotted_values.py` selects and aggregates existing records. It
reconstructs 18 panel CSVs and three table-related CSVs without performing new
optimization or measurements. Archived plotting scripts use matplotlib;
summary scripts additionally require the original result tree and, where
applicable, the original scientific source tree. Publication scripts apply
the recorded two-case overlay. The independent triangle verifier checks
rational bounds.

Historical figure/table indexes identify six figures and two tables. Current
main figures use 17 panels with 489 rows; the additional candidate-excess
file retains 32 rows. Historical pending-status receipts refer to the
analysis stage at which they were written.

`MANIFEST.json` records distributed file hashes and byte counts. It excludes
itself and `SHA256SUMS` to avoid self-referential hashing. `SHA256SUMS` uses
`sha256sum -c` syntax and covers every distributed file except itself.
