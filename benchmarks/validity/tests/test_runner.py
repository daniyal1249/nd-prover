import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.validity.runner import _remove_partial_tail, run_cases, _CaseWorker
from benchmarks.validity.provenance import (
    input_hash, validate_run_metadata, write_run_metadata
)
from benchmarks.validity.cases import BenchmarkCase
from benchmarks.validity.report import load_results
from nd_prover import *


class BenchmarkRunnerTests(unittest.TestCase):

    def test_resume_metadata_rejects_different_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.metadata.json"
            extra = {"library": "ILTP", "case_set_sha256": "abc"}
            write_run_metadata(path, 1000, extra)

            with self.assertRaises(ValueError):
                validate_run_metadata(path, 2000, extra)

    def test_resume_metadata_accepts_same_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.metadata.json"
            extra = {"library": "QMLTP", "case_set_sha256": "abc"}
            write_run_metadata(path, 1000, extra)
            validate_run_metadata(path, 1000, extra)

            metadata = json.loads(path.read_text())
            self.assertEqual(metadata["countermodel"], False)
            self.assertEqual(metadata["produce_models"], False)
            self.assertEqual(metadata["small"], False)
            self.assertIn("implementation_sha256", metadata)

    def test_resume_removes_truncated_final_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            path.write_text('{"case_id":"a"}\n{"case_id":')

            _remove_partial_tail(path)

            self.assertEqual(path.read_text(), '{"case_id":"a"}\n')

    def test_resume_adds_missing_final_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            path.write_text('{"case_id":"a"}')

            _remove_partial_tail(path)

            self.assertEqual(path.read_text(), '{"case_id":"a"}\n')

    def test_resume_rejects_changed_watchdog_or_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.metadata.json"
            original = {"hard_timeout_ms": 3000, "input_sha256": "before"}
            write_run_metadata(path, 1000, original)
            for change in (
                {"hard_timeout_ms": 4000}, {"input_sha256": "after"}
            ):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    validate_run_metadata(path, 1000, {**original, **change})

    def test_complete_corrupt_record_is_not_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            path.write_text('{"case_id":"a"}\ninvalid\n')
            with self.assertRaises(ValueError):
                _remove_partial_tail(path)
            self.assertTrue(path.read_text().endswith("invalid\n"))

    def test_resume_rejects_an_incomplete_json_object(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            case = self._case("p")
            path.write_text(json.dumps({"case_id": case.case_id}) + "\n")
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                run_cases([case], path, 1000, progress=False)
            self.assertEqual(original, path.read_bytes())

    def test_formula_changes_affect_input_hash(self):
        first = self._case("p")
        second = self._case("q")
        self.assertEqual(first.case_id, second.case_id)
        self.assertNotEqual(input_hash([first]), input_hash([second]))

    def test_spawn_worker_records_results_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            case = self._case("p")
            self.assertTrue(run_cases([case], path, 1000, progress=False))
            first = path.read_bytes()
            row = load_results(path)[0]
            self.assertEqual(row["status"], "valid")
            self.assertTrue(row["matches_expected"])
            self.assertTrue(run_cases([case], path, 1000, progress=False))
            self.assertEqual(first, path.read_bytes())

    def test_watchdog_restarts_worker(self):
        worker = _CaseWorker()
        try:
            case = self._case("p")
            result = worker.run(case, 1000, 0)
            self.assertEqual(result["status"], "unknown")
            self.assertTrue(result["hard_timeout"])
            self.assertNotIn("cpu_ms", result)
            self.assertEqual(worker.run(case, 1000, 3000)["status"], "valid")
        finally:
            worker.close()

    @staticmethod
    def _case(atom):
        formula = Pred(atom, ())
        return BenchmarkCase(
            "ILTP", "1.1.2", "ABC001+1", Path("ABC001+1.p"),
            Problem(IPL, [formula], formula), source_status="Theorem"
        )


if __name__ == "__main__":
    unittest.main()

