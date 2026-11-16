from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import asdict
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from nd_prover import *

from benchmarks.crotts_tate.corpus import (
    SOURCE, BenchmarkProblem, load_problems, translate_formula, verify_source
)
from benchmarks.crotts_tate.proofs import count_proof, restore_proof, run_one
from benchmarks.crotts_tate.report import (
    audit_results, comparison_tables, load_results, summarize
)
from benchmarks.crotts_tate.run import (
    main as benchmark_main, run_benchmark, run_metadata, _verify_artifacts, _verify_inputs
)
from benchmarks.worker import WorkerTimeout


SETTINGS = {
    "derived_rules": True, "mode": "staged", "timeout_ms": 1000,
    "hard_timeout_ms": 4000
}


def example(premises=None, conclusion="Q"):
    premises = ["P→Q", "P"] if premises is None else premises
    return BenchmarkProblem(
        1, " ; ".join(premises) + " / " + conclusion, "TFL",
        premises, conclusion, premises, conclusion
    )


class TranslationTests(unittest.TestCase):

    def test_source_is_pinned_and_partition_is_preserved(self):
        verify_source()
        specs = load_problems(SOURCE)
        self.assertEqual(len(specs), 288)
        self.assertEqual(sum(s.logic == "TFL" for s in specs), 203)
        self.assertEqual(specs[51].logic, "FOL")
        self.assertEqual(specs[92].logic, "FOL")

    def test_atom_substitution_does_not_cascade(self):
        mapping = {"C": "A", "A": "B", "B": "C", "D": "D"}
        translated = translate_formula(
            "(C -> A)", fol=False, remap={}, atom_map=mapping
        )
        self.assertEqual(translated, "(A→B)")
        self.assertNotEqual(translated, "(C→C)")

    def test_all_propositional_atoms_keep_their_occurrences(self):
        from collections import Counter

        for spec in load_problems(SOURCE):
            if spec.logic != "TFL":
                continue
            expected = Counter(spec.atom_map[name] for name in re.findall(
                r"[A-Z][a-z]*", spec.raw
            ))
            actual = Counter(re.findall(
                r"[A-Z]", " ".join(spec.premises + [spec.conclusion])
            ))
            with self.subTest(index=spec.index):
                self.assertEqual(actual, expected)
                self.assertEqual(len(set(spec.atom_map.values())), len(spec.atom_map))
                status = check_validity(
                    TFL, [parse_formula(p) for p in spec.premises],
                    parse_formula(spec.conclusion), timeout=1000
                ).status
                self.assertEqual(status, "valid")

    def test_free_variable_source_item_is_an_input_error(self):
        spec = load_problems(SOURCE)[45]
        row = run_one(spec, SETTINGS)
        self.assertEqual(row["status"], "input_error")
        self.assertFalse(row["stages"])
        self.assertIn("not a closed formula", row["error"])

    def test_source_problem_101_is_invalid_as_written(self):
        spec = load_problems(SOURCE)[100]
        result = check_validity(
            FOL, [parse_formula(p) for p in spec.premises],
            parse_formula(spec.conclusion), timeout=1000
        )
        self.assertEqual(result.status, "invalid")


class ProofTests(unittest.TestCase):

    def test_derived_rules_are_explicit_and_optional(self):
        spec = example(["P∨Q", "¬P"])
        for enabled in (False, True):
            row = run_one(spec, {**SETTINGS, "derived_rules": enabled})
            self.assertTrue(row["success"])
            self.assertEqual("DS" in row["rules"], enabled)
            restored = restore_proof(spec, row["proof"], enabled)
            self.assertEqual(row["proof_lines"], count_proof(restored)["proof_lines"])

    def test_staged_search_retries_after_timeout(self):
        spec = example()
        from benchmarks.crotts_tate import proofs

        original = proofs.prove
        responses = [ProofSearchResult("timeout"), None]

        def search(*args, **kwargs):
            response = responses.pop(0)
            return original(*args, **kwargs) if response is None else response

        with patch.object(proofs, "prove", side_effect=search) as called:
            row = run_one(spec, SETTINGS)
        self.assertTrue(row["success"])
        self.assertEqual([s["status"] for s in row["stages"]], ["timeout", "success"])
        self.assertEqual([c.kwargs["exhaustive"] for c in called.call_args_list],
                         [True, False])
        self.assertTrue(all(c.kwargs["derived_rules"] for c in called.call_args_list))

    def test_proof_replay_counts_assumptions_and_rejects_bad_citations(self):
        spec = example(["P∨Q", "P→R", "Q→R"], "R")
        row = run_one(spec, {**SETTINGS, "derived_rules": False})
        problem = restore_proof(spec, row["proof"], False)
        self.assertEqual(count_proof(problem), {
            "proof_lines": 8, "generated_lines": 5, "assumptions": 2,
            "distinct_rules": 2, "distinct_rules_with_assumptions": 3,
            "rules": ["→E", "∨E"]
        })
        broken = deepcopy(row["proof"])
        broken[-1]["citations"] = [999]
        with self.assertRaises(ValueError):
            restore_proof(spec, broken, False)

    def test_proof_replay_rejects_unknown_rules(self):
        spec = example()
        row = run_one(spec, SETTINGS)
        broken = deepcopy(row["proof"])
        broken[-1]["rule"] = "unrecognized"
        with self.assertRaisesRegex(ValueError, "Unknown proof rule"):
            restore_proof(spec, broken, True)

    def test_audit_rejects_forged_metrics_and_missing_results(self):
        spec = example()
        row = run_one(spec, SETTINGS)
        metadata = run_metadata([spec], SETTINGS)
        self.assertEqual(audit_results([row], metadata, [spec])[0]["solved"], 1)
        with self.assertRaises(ValueError):
            audit_results([{**row, "proof_lines": 99}], metadata, [spec])
        with self.assertRaises(ValueError):
            audit_results([], metadata, [spec])

    def test_aggregates_keep_failed_rows_in_the_denominator(self):
        row = run_one(example(), SETTINGS)
        failed = {
            **row, "status": "failure", "success": False,
            "proof_lines": 0, "generated_lines": 0, "distinct_rules": 0
        }
        group = summarize([row, failed])[0]
        self.assertEqual(group["success_percent"], 50)
        self.assertEqual(group["mean_lines_all"], row["proof_lines"] / 2)
        self.assertEqual(group["mean_lines_solved"], row["proof_lines"])

    def test_audit_rejects_invalid_stage_measurements(self):
        spec = example()
        row = run_one(spec, SETTINGS)
        metadata = run_metadata([spec], SETTINGS)
        for changes in (
            {"elapsed_ms": -1}, {"elapsed_ms": float("nan")},
            {"elapsed_ms": row["elapsed_ms"] + 1}, {"status": "unknown"}
        ):
            broken = deepcopy(row)
            broken["stages"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                audit_results([broken], metadata, [spec])

    def test_audit_rejects_search_continuing_after_success(self):
        spec = example()
        row = run_one(spec, SETTINGS)
        row["stages"] = [
            {"mode": "exhaustive", "status": "success", "elapsed_ms": 0},
            {"mode": "fast", "status": "success", "elapsed_ms": 0}
        ]
        with self.assertRaisesRegex(ValueError, "continued after success"):
            audit_results([row], run_metadata([spec], SETTINGS), [spec])

    def test_runner_flushes_resumes_and_records_inputs(self):
        spec = example()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(run_benchmark([spec], path, SETTINGS), 0)
                original = path.read_bytes()
                self.assertEqual(run_benchmark([spec], path, SETTINGS), 0)
            self.assertEqual(original, path.read_bytes())
            self.assertEqual(len(load_results(path)), 1)
            inputs = json.loads(path.with_suffix(".inputs.json").read_text())
            self.assertEqual(inputs, [asdict(spec)])
            with self.assertRaises(ValueError):
                run_benchmark([spec], path, {**SETTINGS, "derived_rules": False})
            saved_inputs = path.with_suffix(".inputs.json")
            saved_inputs.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Saved translated inputs"):
                run_benchmark([spec], path, SETTINGS)

    def test_output_stem_cannot_overwrite_recorded_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            results.mkdir()
            inputs = results / "crotts-tate-5s.inputs.json"
            inputs.write_text("protected", encoding="utf-8")
            (results / "manifest.json").write_text(json.dumps({
                "files": {"crotts-tate-5s.inputs.json": "unused"}
            }), encoding="utf-8")
            with patch("benchmarks.crotts_tate.run.DIRECTORY", root):
                with self.assertRaisesRegex(ValueError, "read-only"):
                    run_benchmark([example()], results / "crotts-tate-5s.scratch", SETTINGS)
            self.assertEqual(inputs.read_text(), "protected")
            self.assertFalse((results / "crotts-tate-5s.metadata.json").exists())

    def test_saved_input_file_matches_the_selected_source(self):
        spec = example()
        metadata = run_metadata([spec], SETTINGS)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            inputs = path.with_suffix(".inputs.json")
            inputs.write_text(json.dumps([asdict(spec)]), encoding="utf-8")
            _verify_inputs(path, metadata, [spec])
            inputs.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Saved translated inputs"):
                _verify_inputs(path, metadata, [spec])

    def test_report_exports_cannot_replace_input_artifacts(self):
        spec = load_problems(SOURCE)[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            with redirect_stdout(io.StringIO()):
                run_benchmark([spec], path, SETTINGS)
            files = [path, path.with_suffix(".metadata.json"),
                     path.with_suffix(".inputs.json"), path.with_suffix(".summary.json")]
            original = {file: file.read_bytes() for file in files}
            for destination in files:
                with self.subTest(destination=destination.name):
                    with patch("sys.argv", [
                        "crotts_tate", "report", str(path), "--csv", str(destination)
                    ]), redirect_stdout(io.StringIO()), patch("sys.stderr", io.StringIO()):
                        self.assertEqual(benchmark_main(), 2)
            self.assertEqual({file: file.read_bytes() for file in files}, original)

    def test_published_table_exports_use_the_correct_subset_and_denominator(self):
        groups = json.loads((SOURCE.parent / "results/crotts-tate-5s.summary.json").read_text())
        tables = [row for row in comparison_tables(groups) if row["system"] == "ND-Prover"]
        self.assertEqual([
            (row["success_percent"], row["mean_lines"], row["mean_distinct_rules"])
            for row in tables
        ], [
            (96.53, 2413 / 288, 1028 / 288),
            (100.0, 1853 / 203, 760 / 203),
            (88.24, 560 / 85, 268 / 85),
            (None, 2413 / 278, 1028 / 278)
        ])

    def test_watchdog_timeout_is_saved_without_a_cpu_estimate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            with patch("benchmarks.crotts_tate.run.Worker") as worker:
                worker.return_value.run.side_effect = WorkerTimeout(4000)
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(run_benchmark([example()], path, SETTINGS), 0)
                worker.return_value.close.assert_called_once()
            row = load_results(path)[0]
            self.assertEqual(row["status"], "timeout")
            self.assertTrue(row["hard_timeout"])
            self.assertIsNone(row["cpu_ms"])

    def test_recorded_run_replays_and_matches_its_summary(self):
        root = SOURCE.parent / "results"
        path = root / "crotts-tate-5s.jsonl"
        _verify_artifacts(path)
        metadata = json.loads(path.with_suffix(".metadata.json").read_text())
        groups = audit_results(load_results(path), metadata)
        saved_summary = json.loads((root / "crotts-tate-5s.summary.json").read_text())
        self.assertEqual(groups, saved_summary)
        self.assertEqual([(g["cases"], g["solved"]) for g in groups],
                         [(288, 278), (203, 203), (85, 75)])


if __name__ == "__main__":
    unittest.main()

