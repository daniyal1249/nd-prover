# Crotts-Tate proof benchmark

This evaluates proof generation on the 288 problems from Crotts and Tate's
[comparison of natural deduction provers](https://joshuacrotts.us/assets/comparison.pdf).
The [source problems](https://raw.githubusercontent.com/joshuacrotts/masters-thesis/main/data/natural_deduction_problems.txt)
are included as `problems.txt`, with a checked SHA-256.

## Run

Install the project from the repository root with `python -m pip install -e .`.
Use AC power for timing measurements.

```sh
python -m benchmarks.crotts_tate.run run --output benchmarks/crotts_tate/results/local/crotts-tate-5s.jsonl
python -m benchmarks.crotts_tate.run audit benchmarks/crotts_tate/results/local/crotts-tate-5s.jsonl
python -m benchmarks.crotts_tate.run report benchmarks/crotts_tate/results/local/crotts-tate-5s.jsonl --tables benchmarks/crotts_tate/results/local/tables.csv
```

Derived rules are enabled by default. The runner tries exhaustive search, then
fast search after failure or timeout. Each stage has a 5-second limit; a process
watchdog allows 12 seconds per problem. See `run --help` for other settings and
problem ranges.

Results are flushed to JSONL after each problem. Adjacent files hold the run
metadata and translated inputs, with a summary written on completion or
interruption. Sidecars share the result's filename stem, for example
`crotts-tate-5s.metadata.json`. Matching runs resume automatically;
`--no-resume` starts afresh.
The CLI protects the recorded result files from replacement. Files under
`results/local/` and CSV exports are not committed.

The audit reconstructs each saved proof and checks it with ND-Prover's proof
checker. It verifies the input translation and recomputes proof metrics.
Recorded artifacts also have checksums. Run the tests with
`python -m unittest discover -s benchmarks -t .`.

## Inputs and metrics

All 288 entries remain in the evaluation, including duplicates. The partition
of 203 propositional and 85 first-order problems is inferred from the source:
83 entries contain quantifiers or identity, and rows 52 and 93 are assigned to
the first-order subset to match the paper. The source does not label subsets.
Rows 48-51 involve identity, which proof generation does not support. They remain
in the published suite's denominator and are recorded as failures.

Propositional rows treat compact tokens such as `Kb` as distinct atoms, renamed
to single capital letters. First-order rows expand `Pxy` to `P(x,y)` and rename
constants that conflict with the parser's variable letters. The saved inputs
include these mappings. Free variables are not implicitly quantified.

Two source issues affect the results:

- Problem 46 has a free `x` in its conclusion and introduces predicate `M`.
  It is recorded as `input_error` without attempting proof search.
- Problem 101 is invalid as written. Domain `{a,b}`, with `G = M = {a}` and
  `e = b`, satisfies its premises and falsifies its conclusion.

Unsuccessful cases count as zero lines and zero distinct rules in the all-case
averages, following Tables 3-5 of the paper. Solved-only means follow Table 6.
Line counts include premises and subproof assumptions; distinct rules exclude
`PR` and `AS`. Generated lines exclude premises but include assumptions.

Elapsed time includes parsing, input validation, and proof generation with its
internal proof checks. Input translation and worker startup are outside the
timer, as are result serialization and the saved-proof audit. A `failure` may
include an exception caught inside the generator; it is not a proof of
unprovability.

`published_results.json` contains the paper's Tables 3-6 for CSV comparison.
Those systems are not rerun. Their rule sets differ, so line counts compare
displayed proofs rather than derivations in a shared primitive calculus.

## Results

The November 15, 2026 run uses ND-Prover 3.2.0, Python 3.14.2, and cvc5 1.3.4,
with derived rules and the default staged search. Metadata records the code
hash used when the run was collected. The recorded results are in
`results/crotts-tate-5s.jsonl`.

| Subset | Solved | Mean lines, all cases | Mean distinct rules, all cases | Total case time (s) |
| --- | ---: | ---: | ---: | ---: |
| All | 278 / 288 | 8.38 | 3.57 | 36.797 |
| Propositional | 203 / 203 | 9.13 | 3.74 | 7.622 |
| First-order | 75 / 85 | 6.59 | 3.15 | 29.175 |

Overall success is 96.53%. Solved-only means are 8.68 lines and 3.70 distinct
rules. Failures are 32, 44, 48-51, 101, and 188. Problem 207 times out; problem
46 is an input error. Problems 40 and 210 succeed in fast search after their
exhaustive stages time out. There are no evaluator errors or watchdog terminations.
All 278 saved proofs pass the audit.
