# Semantic validity benchmarks

This evaluates `nd_prover.check_validity` on ILTP 1.1.2 and QMLTP 1.1.
It does not measure proof generation or countermodel extraction.

## Reproduce a run

Install the project from the repository root with `python -m pip install -e .`.
Download the files listed in [corpora.json](corpora.json) from the
[ILTP](https://www.iltp.de/formulae.html) and
[QMLTP](https://www.iltp.de/qmltp/problems.html) libraries. Extract the three
archives into `benchmark_data/` and put the statistics files there too.
The manifest pins the downloaded files and the extracted `Problems/` and
`Axioms/` trees by SHA-256. Archives may be removed after extraction.

Run these commands from the repository root:

```sh
python -m unittest discover -s benchmarks/validity/tests
python -m benchmarks.validity.run audit --data-root benchmark_data
python -m benchmarks.validity.run iltp benchmark_data/ILTP-v1.1.2-firstorder benchmark_data/ILTP-v1.1.2-propositional --output benchmarks/validity/results/local/iltp-10s.jsonl --timeout-ms 10000
python -m benchmarks.validity.run qmltp benchmark_data/QMLTP-v1.1 --output benchmarks/validity/results/local/qmltp-10s.jsonl --timeout-ms 10000
```

Use `--timeout-ms 60000` and another output filename for the longer runs.
`validate-iltp` and `validate-qmltp` accept the same library paths and only
check imports. Missing libraries and unexpected import skips are errors.

Runs resume by default. Each case is flushed to JSONL. Sidecars use the same
filename stem: `iltp-10s.metadata.json` and `iltp-10s.skips.jsonl`, for example.
An incomplete final line is removed on resume; other corruption is rejected.
New metadata records code
and parsed-input hashes, solver settings, and the watchdog budget. A change to
these settings prevents resume. `--no-resume` replaces a local run.

Use `--case-id` repeatedly, or `--case-list` with one ID per line, to reproduce
selected cases. The four archived runs cannot be overwritten by the CLI.

```sh
python -m benchmarks.validity.run report benchmarks/validity/results/qmltp-60s.jsonl --csv benchmarks/validity/results/local/qmltp-60s.csv
python -m benchmarks.validity.run audit
```

`audit` verifies result integrity and scoring. With `--data-root`, it also
checks corpus hashes and compares the imported cases, including structural
metrics and official labels, with every archived record. CSV exports are
derived files and are not committed.

## Scope and measurement

The importer builds ASTs directly, without the public parser's symbol limits.
Includes and selection lists are resolved before solving. Free variables are
universally closed. Problems without a conjecture are tested for inconsistency.
Unknown roles, interpreted numeric terms, indexed modalities, and process
instructions are rejected rather than given different semantics.

Conjunction and disjunction chains are balanced to avoid recursion limits.
For loosely parenthesized source formulas, precedence is `~`, then `&`, then
`|`, then implication, then equivalence. Implication associates to the right;
quantifiers and modalities bind to the next unitary formula. Source warnings
in the QMLTP records identify parenthesization and equality issues.

ILTP has 2,754 distinct cases: 274 IPL and 2,480 IFOL. The 70 problems shared
between the two archives are counted once, preferring the propositional copy.
Official statistics supply intuitionistic statuses; headers are the fallback.

QMLTP uses 500 problems. The 20 multimodal problems and 80 nonmodal NLP/SET
problems are skipped. The imported formulas give 176 propositional problems,
each run in K, T, S4, and S5, and 324 quantified problems, each run in:

- QK, QT, and QS4 with expanding and constant domains;
- QS5 with constant domains.

This gives 2,972 cases. D and varying domains are unsupported. Terms are rigid
and local. Expanding domains allow equal domains at adjacent worlds.

Wall and CPU timers cover semantic translation and the solver call. Parsing
and structural metrics are outside that interval. The runner passes
`countermodel=False` and `small=False`. Countermodel generation and minimization
are disabled.

A persistent child process runs the checks. The watchdog defaults to the solver
budget plus 2 seconds and restarts a stuck worker. Its `unknown` record includes
wall time but no CPU estimate. Solver timeouts also produce `unknown`; they are
not incorrect answers. Reported CPU averages use only available measurements.
Timing summaries separate solved cases from all attempts; p95 uses nearest rank.

## Archived results and exceptions

The runs were created on September 2 and 4, 2026, with ND-Prover 3.2.0,
cvc5 1.3.4, and Python 3.14.2 on Windows 11. Original JSONL files and sidecars
are preserved byte for byte; [results/manifest.json](results/manifest.json)
records their checksums. Absolute source paths are historical provenance.

| Run | Cases | Solved | Unknown | Gold correct | Gold disagreements | Watchdog timeouts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ILTP 10 s | 2,754 | 1,173 | 1,581 | 716 / 936 | 0 | 344 |
| ILTP 60 s | 2,754 | 1,233 | 1,521 | 723 / 936 | 0 | 664 |
| QMLTP 10 s | 2,972 | 1,986 | 986 | 1,758 / 2,034 | 1 | 173 |
| QMLTP 60 s | 2,972 | 2,004 | 968 | 1,769 / 2,034 | 1 | 373 |

All runs have zero recorded errors. Solved means `valid` or `invalid`.
Theorem and Non-Theorem labels are used for gold scoring. Open and Unsolved
cases remain unlabeled, even when ND-Prover answers them. Such answers are not
independently certified new solutions.

The runs predate commit `0d26dc7` (October 19, 2026), which added the current
`countermodel` option to `sat.py`. The runner uses that API with generation
disabled, as recorded in the original benchmark settings. The historical
metadata lacks implementation/input hashes and an explicit watchdog budget;
its git commit does not establish the exact local code used for the experiment.
Repeating the experiment with today's code is a new run. Legacy runs cannot
be resumed with the revised runner.

Two source problems, `SYM052+1` and `SYM056+1`, use native inequality/equality
in a corpus that also uses the predicate `qmltpeq`. The archived scoring
conservatively excludes all seven configurations of each problem, or 14 cases,
while retaining their answers and timings. This does not mean all 14 labels are
wrong. In particular, native identity makes `SYM052+1` valid for constant domains,
contrary to its Non-Theorem label: two distinct possible individuals must already
belong to the same constant domain. The exclusions are retained for consistency
with the recorded experiment. All supported configurations of `SYM056+1` are
labelled Theorem; its exclusion follows the historical equality policy, not a
disagreement in these runs.

The remaining disagreement is `QMLTP:GSY374+1:QT:cumulative`. Its header says
Theorem, but ND-Prover's invalid answer agrees with an existing published result.
The [supplementary data](https://doi.org/10.5281/zenodo.10802221) for
[Steen, Sutcliffe, and Benzmueller's evaluation](https://arxiv.org/html/2212.09570)
contains Nitpick 2016's `CounterSatisfiable` result for
`GSY374_1.014_t_cumulative_rigid.p` in `QMLTPResults/TH0_N.txt`. This is a direct
result for the disputed configuration, rather than an inference from the paper's
general discussion of conflicting prover results.

The [saved countermodel](countermodels/GSY374+1-QT-expanding.json) records the
source checksum and the published result's location. Its interpretation is:

- Worlds: `w0`, `w1`, `w2`; root: `w0`.
- Accessibility: all reflexive edges, plus `w0 -> w1` and `w1 -> w2`.
- One individual `d0` at every world; `big_p(d0)` holds at `w0` and `w1` only.

This frame is reflexive with constant, hence expanding, domains. It is not
transitive. At `w0`, box P holds while box box P fails, and the source conjecture
is false. Exhaustive finite-model tests establish minimum world and edge counts
within singleton-domain reflexive models. The model check and minimality check
are independent of cvc5 and run with the benchmark tests.

The archived score still counts the disagreement with the original header;
neither the source label nor the recorded results have been changed. The three
original QMLTP files used by the regression tests are in `tests/fixtures/`, with
their source headers. The full corpora remain external.
