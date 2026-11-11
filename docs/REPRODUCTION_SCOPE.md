# Reproduction scope

## Implementation snapshot

The supplied minimum package contains 12 core Python modules, 55 driver scripts,
12 test modules, and 70 experiment/configuration files. Its original code is
preserved except for one test-only floating-point comparison, described below.
The numerical implementations and original configurations are unchanged.

Some configurations and drivers predate the current manuscript's final
experiment setup. They should not be treated as interchangeable with that
setup. In particular, older protocol configurations have different release
horizons; use the matching configuration and threat model for any new run.

## Local tests

`python reproduce.py --tests` runs the provided tests. Two integration tests
need processed data that was absent from the supplied package:

- `data/processed/intel_daily.json`
- `data/processed/electricity_verification.json`
- `data/processed/electricity_kwh_clipped.f32`

`tests/conftest.py` reports those two tests as **skipped only when their required
files are absent**. Supplying the files enables the tests automatically. To
require the data instead of skipping, run:

```bash
python -m pytest -q --require-data tests
```

In `test_spectral_every_deletion`, the original equality compared a NumPy
floating-point sum to a Python sum. On the tested platform these differed by
`4.44e-16`. The comparison now uses a relative tolerance of eight machine
epsilons and zero absolute tolerance. The privacy constraints in that test and
all implementation code are unchanged. The four graph parametrizations are
still executed. Original and distributed hashes are recorded in
`provenance/ORIGINAL_FILE_MAP.json`.

## Archived figures and tables

The summary-to-CSV extractor and the current plotting code have all their
inputs in this repository. Extraction compares 18 panel CSVs (including the
32-row supplemental approximation file) and three table-related CSVs against
the archive. The complete table-I view is also retained separately as
`tables/table1_design/values_complete.csv`; its finite-report workload count
comes from the archived summary's `coverage.E.primary_instances`.

PDF bytes can change with font, backend, or library versions. Numeric CSVs,
data hashes, pairwise calculations, axis coverage, and plotted values are the
appropriate checks. Plot regeneration preserves all comparison methods and
reported intervals.

## Requirements for full measurement reruns

The supplied archive is missing the original remote result trees and the
complete revision-specific experiment source tree. For example,
`scripts/archived_analysis/summarize_results.py` expects external modules
`common.py`, `solvers.py`, `uniform_oracle.py`, `triangle_exact.py`, `grouping.py`,
and `finite_sim.py`, together with the original frozen run manifest. These
modules are not present in the supplied minimum package.

The original `scripts/protocol_run.py` also expects the authors' two-host SSH
setup, original project locks, Linux CPU-affinity controls, and staged peer
files. Its paths and host labels are retained as historical configuration;
they are not working defaults on a new machine. The local entry points in
`reproduce.py` do not invoke this runner or access SSH.

Some baseline adapters expect separately obtained original DECOR and
WhisperDSGD source repositories under `literature/code/`. Those third-party
repositories were not included, so `scripts/microcases.py` is not the local
quick-start command.

No missing experiment source, raw data, execution record, or result has been
fabricated. The repository supports local implementation checks and exact
archived-number reconstruction; it is not a complete from-scratch replication
of all manuscript measurements.


## Local setup and commands

The validated environment uses Python 3.13. Install dependencies with
`python -m pip install -r requirements.txt` in a virtual environment.
Run `python reproduce.py --check` for file integrity, `--demo` for the small
synthetic example, `--tests` for implementation tests, and
`--extract --figures` for archived CSV reconstruction and current figures.
New output is written to `generated/`.

## English distribution

The data dictionary is provided in English. Historical non-English archive
names and machine-root labels use English aliases. These aliases describe
the original sources and are not new executable paths. Original archive and
input-file hashes remain available in provenance records. Core algorithms,
experiment configurations, numeric results, figures, and paper PDFs are
unchanged by this language cleanup.
