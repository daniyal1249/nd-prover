from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nd_prover import *

from benchmarks.proofs import count_proof, make_problem, proof_shape, restore_proof
from benchmarks.forallx.corpus import (
    DEFAULT_SOURCE, DIRECTORY, load_problems, make_reference, uses_identity
)
from benchmarks.forallx.latex import formula, group, parse_derivation, proof_payload
from benchmarks.forallx.proofs import run_one
from benchmarks.forallx.report import audit_results, meets_rule_constraints, summarize
from benchmarks.forallx.run import (
    artifact_paths, audit_corpus, load_run, main as benchmark_main, metadata_for,
    run_benchmark, writable
)
from benchmarks.forallx.statements import declared_argument, problem_statement
from benchmarks.worker import WorkerTimeout


SETTINGS = {"mode": "staged", "derived_rules": True, "timeout_ms": 1000, "hard_timeout_ms": 4000}


class ImportTests(unittest.TestCase):

    def test_balanced_latex_groups_and_unknown_commands(self):
        self.assertEqual(group(" {a{b}c} tail", 0), ("a{b}c", 8))
        with self.assertRaises(ValueError):
            group("{a{b}", 0)
        with self.assertRaises(ValueError):
            formula(r"\unsupported{A}")

    def test_formula_notation_preserves_quantifiers_and_identity(self):
        translated = formula(
            r"\forall x\bigl[\atom{F}{x} \eif \exists y (\atom{R}{x,y} \eand \enot x=y)\bigr]")
        expected = Forall(Var("x"), Imp(Pred("F", (Var("x"),)), Exists(Var("y"), And(
            Pred("R", (Var("x"), Var("y"))), Not(Eq(Var("x"), Var("y")))))))
        self.assertEqual(parse_formula(translated), expected)
        self.assertEqual(formula(r"\ebox\ediamond A"), "☐◇A")

    def test_declared_argument_collects_separate_math_premises(self):
        self.assertEqual(declared_argument(
            r"\item $A$, $A\eif B \therefore B$"), (["A", "A → B"], "B"))
        self.assertEqual(declared_argument(
            r"\item $\exists x\,\atom{F}{x} \proves A$"), (["∃x F(x)"], "A"))
        self.assertEqual(declared_argument(
            r"Corresponding argument: $A\therefore B$"), (None, None))
        self.assertEqual(declared_argument(
            r"\item $\Box A\vdash_\mlSfour \Box\Box A$"), (["☐A"], "☐☐A"))

    def test_depth_counts_nested_boxes_and_sibling_subproofs(self):
        raw = r"\open\hypo{a}{A}\open\hypo{b}{B}\have{a1}{A}\by{R}{a}\close\have{ba}{B\eif A}\ci{b-a1}\close\have{aba}{A\eif(B\eif A)}\ci{a-ba}"
        parsed = parse_derivation(raw)
        self.assertEqual(parsed["max_subproof_depth"], 2)
        self.assertEqual(parsed["subproof_count"], 2)
        spec = deepcopy(load_problems()[0])
        spec.premises, spec.conclusion = [], "A→(B→A)"
        restored = restore_proof(spec, proof_payload(parsed["lines"], 0), True)
        self.assertEqual(proof_shape(restored), {"max_subproof_depth": 2, "subproof_count": 2})
        self.assertEqual(count_proof(restored)["proof_lines"], 5)

    def test_corpus_coverage_accounts_for_every_derivation(self):
        specs = load_problems()
        coverage = json.loads((DIRECTORY / "coverage.json").read_text(encoding="utf-8"))
        entries = [entry for part in coverage for entry in part["proofs"]]
        displayed = [entry for entry in entries if "source_proof" in entry]
        self.assertEqual(len(displayed), 137)
        self.assertEqual(sum(entry["status"] == "excluded" for entry in displayed), 28)
        self.assertEqual(sum(entry["status"] == "included_recipe" for entry in entries), 4)
        self.assertEqual(len(specs), 112)
        self.assertEqual(sum(len(spec.references) for spec in specs), 113)
        self.assertEqual({spec.logic for spec in specs}, {"TFL", "FOL", "K", "T", "S4", "S5"})
        self.assertEqual({entry["case_id"] for entry in entries if entry["status"].startswith("included")}, {
                         spec.case_id for spec in specs})
        self.assertTrue(all(reference["validated"] for spec in specs for reference in spec.references))

    def test_identity_is_excluded_but_checked_references_are_preserved(self):
        specs = load_problems()
        self.assertEqual(sum(spec.logic == "FOL" for spec in specs), 51)
        self.assertFalse(any(uses_identity(spec.premises, spec.conclusion) for spec in specs))
        coverage = json.loads((DIRECTORY / "coverage.json").read_text(encoding="utf-8"))
        entries = [entry for part in coverage for entry in part["proofs"]
                   if "identity" in entry.get("unsupported_features", [])]
        self.assertEqual(len(entries), 16)
        self.assertTrue(all(entry["status"] == "excluded" for entry in entries))
        checked = [entry for entry in entries if entry["reference"]["validated"]]
        self.assertEqual(len(checked), 11)
        for entry in checked:
            ref = entry["reference"]
            spec = deepcopy(specs[0])
            spec.logic, spec.premises, spec.conclusion = ref["logic"], ref["premises"], ref["conclusion"]
            with self.subTest(case=entry["case_id"]):
                self.assertTrue(ref["source_tex"])
                restore_proof(spec, ref["proof"], True)

    def test_nested_identity_is_detected_in_premises_and_conclusions(self):
        quantified = str(parse_formula("∀x (F(x) → ¬x=a)"))
        self.assertTrue(uses_identity([quantified], "F(a)"))
        self.assertTrue(uses_identity([], quantified))
        self.assertFalse(uses_identity(["∀x F(x)"], "F(a)"))

    def test_every_problem_statement_is_well_formed(self):
        for spec in load_problems():
            with self.subTest(case=spec.case_id):
                make_problem(spec, True)

    def test_validated_references_and_measured_lengths_are_reproducible(self):
        with redirect_stdout(io.StringIO()):
            audit_corpus()

    @unittest.skipUnless(DEFAULT_SOURCE.exists(), "Pinned source clone is not installed.")
    def test_pinned_source_reimports_without_changes(self):
        with redirect_stdout(io.StringIO()):
            audit_corpus(DEFAULT_SOURCE)

    def test_source_errors_are_preserved_instead_of_repaired(self):
        coverage = json.loads((DIRECTORY / "coverage.json").read_text(encoding="utf-8"))
        entries = [entry for part in coverage for entry in part["proofs"]]
        entry = next(entry for entry in entries if entry.get("case_id") == "forallx:39A:9")
        self.assertEqual(entry["status"], "excluded")
        self.assertFalse(entry["reference"]["validated"])
        self.assertTrue(entry["reference"]["validation_errors"])
        self.assertIsNone(entry["reference"]["lines"][0]["formula"])
        self.assertEqual(entry["reference"]["conclusion"], "B(d)")
        self.assertNotIn(entry["case_id"], {spec.case_id for spec in load_problems()})

    def test_equivalence_goal_comes_from_the_exercise(self):
        raw = r"\hypo{a}{A}\have{b}{A\eor B}\oi{a}"
        reference = make_reference(raw, r"\item $A$, $B$", {"exercise": "20C"}, "TFL", "test")
        self.assertEqual(reference["conclusion"], "B")
        self.assertFalse(reference["validated"])
        spec = next(spec for spec in load_problems() if spec.case_id == "forallx:38B:4")
        self.assertEqual(spec.conclusion, "∀x (¬A(x) → B(d))")
        self.assertTrue(spec.reference["validated"])

    def test_theorem_and_inconsistency_have_independent_statements(self):
        self.assertEqual(problem_statement(r"\item $A\eif A$", "20A", [], "B")[:3],
                         ([], "A → A", "theorem"))
        self.assertEqual(problem_statement(r"\item $A, \enot A$", "38A", ["B"], "B")[:3],
                         (["A", "¬A"], "⊥", "inconsistency"))
        with self.assertRaises(ValueError):
            problem_statement("", "43A", ["A"], "A")

    def test_reference_selection_prefers_shortest_then_shallowest(self):
        for spec in load_problems():
            metrics = [(ref["metrics"]["proof_lines"], ref["metrics"]["max_subproof_depth"])
                       for ref in spec.references]
            self.assertEqual(metrics[spec.reference_index], min(metrics))

    def test_citation_order_normalization_preserves_raw_reference(self):
        raw = r"\hypo{a}{A}\hypo{na}{\enot A}\have{b}{\ered}\ri{a,na}"
        ref = make_reference(raw, r"\item $A,\enot A\proves\ered$",
                             {"exercise": "test"}, "TFL", "test")
        self.assertTrue(ref["validated"])
        self.assertEqual(ref["lines"][-1]["citations"], [1, 2])
        self.assertEqual(ref["proof"][-1]["citations"], (2, 1))
        self.assertEqual(ref["source_tex"], raw)


class EvaluationTests(unittest.TestCase):

    def test_recorded_run_passes_the_proof_audit(self):
        rows, groups = load_run(DIRECTORY / "results/forallx-5s.jsonl", load_problems(), True)
        self.assertEqual(len(rows), 112)
        self.assertEqual(groups[0]["solved"], 110)

    def test_recorded_artifacts_are_protected(self):
        path = DIRECTORY / "results/forallx-5s.jsonl"
        for artifact in [*artifact_paths(path), path.parent / "manifest.json"]:
            with self.subTest(artifact=artifact.name), self.assertRaises(ValueError):
                writable(artifact)
        with self.assertRaises(ValueError):
            run_benchmark(load_problems(), path, SETTINGS, resume=False)

    def test_default_audit_selects_the_recorded_run(self):
        with patch("sys.argv", ["forallx", "audit"]), redirect_stdout(io.StringIO()):
            self.assertEqual(benchmark_main(), 0)

    def test_generated_modal_proof_round_trip_includes_box_depth(self):
        spec = next(spec for spec in load_problems() if spec.logic == "K")
        row = run_one(spec, SETTINGS)
        self.assertTrue(row["success"])
        self.assertEqual(len(row["stages"]), 1)
        problem = restore_proof(spec, row["proof"], True)
        self.assertEqual(row["metrics"]["max_subproof_depth"],
                         proof_shape(problem)["max_subproof_depth"])
        self.assertGreater(row["metrics"]["max_subproof_depth"], 0)

    def test_staged_search_uses_fast_fallback_after_timeout(self):
        from benchmarks.forallx import proofs
        spec = next(spec for spec in load_problems() if spec.logic == "K")
        original = proofs.prove
        results = [ProofSearchResult("timeout"), None]

        def search(*args, **kwargs):
            value = results.pop(0)
            return original(*args, **kwargs) if value is None else value
        with patch.object(proofs, "prove", side_effect=search):
            row = run_one(spec, SETTINGS)
        self.assertEqual([stage["status"] for stage in row["stages"]], ["timeout", "success"])
        self.assertTrue(row["reference_validated"])
        self.assertTrue(row["success"])

    def test_audit_rejects_forged_depth(self):
        spec = load_problems()[0]
        row = run_one(spec, SETTINGS)
        row["metrics"]["max_subproof_depth"] += 1
        with self.assertRaises(ValueError):
            audit_results([row], metadata_for([spec], SETTINGS), [spec])

    def test_paired_summaries_do_not_reward_failures(self):
        spec = load_problems()[0]
        row = run_one(spec, SETTINGS)
        failed = {**deepcopy(row), "success": False, "status": "failure", "metrics": None}
        group = summarize([row, failed])[0]
        self.assertEqual(group["solved"], 1)
        self.assertEqual(group["cases"], 2)
        self.assertEqual(group["success_percent"], 50)
        self.assertEqual(group["comparison"]["pairs"], 1)
        self.assertEqual(group["comparison"]["proof_lines"]["generated_mean"], row["metrics"]["proof_lines"])
        self.assertNotIn("mean_lines_all", group)

    def test_unchecked_references_cannot_enter_a_run(self):
        spec = deepcopy(load_problems()[0])
        spec.reference["validated"] = False
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run.jsonl"
            with self.assertRaises(ValueError):
                run_benchmark([spec], output, SETTINGS)
            self.assertFalse(output.exists())

    def test_excluded_case_cannot_be_selected_from_cli(self):
        for case_id in ("forallx:43F:2", "forallx:39A:1"):
            with self.subTest(case=case_id), patch("sys.argv", ["forallx", "run", "--case-id", case_id]):
                with redirect_stdout(io.StringIO()), patch("sys.stderr", io.StringIO()):
                    self.assertEqual(benchmark_main(), 2)

    def test_identity_cannot_enter_a_run_directly(self):
        spec = deepcopy(load_problems()[0])
        spec.logic, spec.premises, spec.conclusion = "FOL", ["a=b"], "a=b"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run.jsonl"
            with self.assertRaisesRegex(ValueError, "Identity"):
                run_benchmark([spec], output, SETTINGS)
            self.assertFalse(output.exists())

    def test_audit_rejects_unchecked_references_and_wrong_selection(self):
        spec = load_problems()[0]
        row = run_one(spec, SETTINGS)
        for key, value in (("reference_validated", False), ("reference_index", 7), ("hard_timeout", True)):
            changed = {**row, key: value}
            with self.subTest(field=key), self.assertRaises(ValueError):
                audit_results([changed], metadata_for([spec], SETTINGS), [spec])

    def test_watchdog_timeout_is_saved_without_a_proof(self):
        spec = load_problems()[0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run.jsonl"
            with patch("benchmarks.forallx.run.Worker") as worker:
                worker.return_value.run.side_effect = WorkerTimeout(SETTINGS["hard_timeout_ms"])
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(run_benchmark([spec], output, SETTINGS), 0)
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(row["status"], "timeout")
            self.assertTrue(row["hard_timeout"])
            self.assertIsNone(row["proof"])
            self.assertIsNone(row["cpu_ms"])

    def test_single_stage_modes_without_derived_rules(self):
        spec = load_problems()[0]
        for mode in ("fast", "exhaustive"):
            settings = {**SETTINGS, "mode": mode, "derived_rules": False}
            with self.subTest(mode=mode):
                row = run_one(spec, settings)
                self.assertTrue(row["success"])
                self.assertEqual([stage["mode"] for stage in row["stages"]], [mode])
                audit_results([row], metadata_for([spec], settings), [spec])

    def test_exercise_restrictions_are_reported_separately(self):
        spec = load_problems()[0]
        row = run_one(spec, SETTINGS)
        row["reference_constraints"] = ["no_modal_conversion"]
        row["metrics"]["rules"] = ["MC"]
        self.assertFalse(meets_rule_constraints(row))

    def test_resume_checks_settings_and_preserves_saved_results(self):
        spec = load_problems()[0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run.jsonl"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(run_benchmark([spec], output, SETTINGS), 0)
                saved = output.read_bytes()
                self.assertEqual(run_benchmark([spec], output, SETTINGS), 0)
            self.assertEqual(output.read_bytes(), saved)
            metadata = json.loads(output.with_suffix(".metadata.json").read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(audit_results(rows, metadata, [spec])[0]["solved"], 1)
            with self.assertRaises(ValueError):
                run_benchmark([spec], output, {**SETTINGS, "derived_rules": False})


if __name__ == "__main__":
    unittest.main()

