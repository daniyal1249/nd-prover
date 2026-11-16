# forall x: Calgary proof benchmark

This compares generated proofs with official solutions to
[*forall x: Calgary*](https://forallx.openlogicproject.org/). It uses the
Fall 2025 text with official corrections through October 22, 2026, pinned to
[commit bb86fe9](https://github.com/rzach/forallx-yyc/tree/bb86fe926ec3cd5d64255070c8f92ace8bf5cb7d).
This revision includes post-release corrections; it is not a release tag.

## Corpus

The benchmark contains 112 problems with 113 checked reference proofs:
44 TFL, 51 FOL, 10 K, 2 T, 3 S4, and 2 S5. One problem has two official proofs.
The shortest reference is selected, breaking ties by maximum subproof depth.
Only problems with a checked official reference enter the run. Identity problems
are excluded because the proof generator does not support identity.

`problems.json` contains the paired corpus. `coverage.json` accounts for all
137 displayed derivations: four deliberately incorrect examples, two incomplete
metatheoretic sketches, and 11 unresolved references are excluded. Another 11
checked references involve identity and are retained only in the inventory.
Identity entries carry an `unsupported_features` field, including those that
also have unresolved reference errors. The manual's substitution instructions
for Celerant, Darii, Celaront, and Darapti supply four
additional references. Exercise groups 20D, 21B, 22A, 22B, and 36G have no complete
formal references and remain outside the benchmark.

Printed arguments and equivalence formulas determine the problems. For exercises
presented as proofs to annotate or rule schemes, the displayed proof defines the
premises and conclusion. Each available equivalence direction is a separate case.
Case IDs identify instances within an exercise group, not printed item numbers.
References retain their source locations and raw LaTeX. Notation and citation
order are normalized; formulas and proof steps are not repaired locally.

Unresolved references are retained in the coverage inventory with diagnostics:

| Case ID | Reason |
| --- | --- |
| `36D:4` | Felapton drops a negation in its final conclusion |
| `38B:3`, `38C:1`, `39C:3` | Undefined citations |
| `38C:10` | Conditional elimination is used to discharge a subproof |
| `39A:5` | Equality elimination cites a double-negated equality |
| `39A:9`, `39C:1` | Malformed formulas |
| `39D:1` | DS uses a shortcut beyond the textbook's displayed rule |
| `43C:1` | Modus tollens cites the wrong lines |
| `43F:2` | Missing justification |

`source.json` records the revision and checksums. The source clone is kept in
`benchmark_data/forallx`, outside the benchmark package.

## Run

From the repository root, with the package installed (`python -m pip install -e .`):

```sh
python -m benchmarks.forallx.run setup
python -m benchmarks.forallx.run audit-corpus --source-dir benchmark_data/forallx
python -m benchmarks.forallx.run run
```

Use AC power for timing measurements. Defaults match Crotts-Tate: derived rules
enabled, exhaustive search followed by fast search after failure or timeout,
5 seconds per stage, and a 12-second process watchdog. `--case-id` selects a case;
`--start` and `--end` select corpus indices. Completed cases are saved immediately.
Repeating the command resumes a run when its code, inputs, and settings match.
Use `--no-resume` to restart a local run.

Audit the results and export the comparison:

```sh
python -m benchmarks.forallx.run audit benchmarks/forallx/results/local/forallx-5s.jsonl
python -m benchmarks.forallx.run report benchmarks/forallx/results/local/forallx-5s.jsonl --csv benchmarks/forallx/results/local/comparison.csv
```

Results have `.metadata.json`, `.inputs.json`, and `.summary.json` sidecars with
the same filename stem. New runs go into ignored `results/local/`; recorded
results in `results/` are protected against replacement. CSV exports are generated
on request and are not committed. To reproduce the corpus in a separate directory
and run the tests:

```sh
python -m benchmarks.forallx.run import --output-dir .build/forallx-import
python -m unittest discover -s benchmarks -t .
```

## Metrics

Proof length includes premises and subproof assumptions, matching Crotts-Tate.
Generated lines exclude premises. Maximum subproof depth starts at zero; ordinary
and modal subproofs each add one level. Subproof counts, assumptions, and distinct
rules are also recorded; distinct rules exclude `PR` and `AS`.

Comparisons use successful generated proofs paired with their selected official
references. Reports give the mean differences and counts of lower, equal, or
higher values, plus the median line ratio. Differences are generated minus
official. Unsuccessful cases stay in the success-rate denominator and contribute
no proof-size measurements.
A `failure` means search did not return a proof; it may include an exception
handled inside the generator and does not establish unprovability.

Search uses the full enabled rule set. The CSV's `reference_rule_constraints_met`
field reports explicit exercise restrictions, including the ban on modal
conversion in 43B and using a rule to justify itself. It does not enforce every
chapter's pedagogical instructions. Timings cover input parsing and generation
with internal checks; they exclude worker startup and result serialization.

## Results

The recorded run uses ND-Prover 3.2.0, Python 3.14.2, and cvc5 1.3.4 with the
default staged search and derived rules enabled. All 110 successful proofs pass
the audit. The two failures are `forallx:36B:1` and `forallx:38C:12`; neither
reaches its time limit. There are no input errors or final timeouts.

| Subset | Solved | Mean lines, generated / official | Mean maximum depth, generated / official |
| --- | ---: | ---: | ---: |
| All | 110 / 112 | 7.99 / 8.78 | 1.05 / 1.24 |
| TFL | 44 / 44 | 7.82 / 8.73 | 1.14 / 1.30 |
| FOL | 49 / 51 | 8.12 / 8.53 | 0.96 / 1.04 |
| K | 10 / 10 | 6.30 / 8.60 | 0.80 / 1.50 |
| T | 2 / 2 | 10.00 / 8.50 | 1.00 / 1.00 |
| S4 | 3 / 3 | 11.33 / 11.33 | 2.00 / 2.00 |
| S5 | 2 / 2 | 10.00 / 13.50 | 1.50 / 2.50 |

Proof-size means use matched successful pairs. Eight generated proofs violate
explicit exercise restrictions: both 21A cases use DeM, both 40A cases use CQ,
and all four 43B cases use MC. Excluding those eight pairs gives mean lengths
8.46 / 8.80 and mean depths 1.14 / 1.21. Overall derivability success is 98.21%;
satisfying the tracked restrictions gives 102 / 112 (91.07%).

The saved run is `results/forallx-5s.jsonl`. Its manifest checks all four artifacts;
metadata retains the implementation hash from collection and records the later
identifier normalization. Measurements and proofs were preserved. Audit or
report this run with `python -m benchmarks.forallx.run audit` or `report`.

## Attribution

The textbook and solutions are by P. D. Magnus, Tim Button, Robert Trueman,
and Richard Zach, with contributions by J. Robert Loftis and Aaron Thomas-Bolduc,
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The benchmark translates the pinned LaTeX, expands the four stated substitution
recipes, and normalizes notation and citation order. The upstream license remains
in the source clone.
