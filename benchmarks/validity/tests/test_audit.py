from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.validity.audit import DIRECTORY, audit_run
from benchmarks.validity.iltp import load_cases
from benchmarks.validity.provenance import case_set_hash
from benchmarks.validity.run import main


class BenchmarkAuditTests(unittest.TestCase):

    def test_archived_runs_have_expected_coverage_and_disagreements(self):
        expected = {
            "iltp-10s": (2754, 1173, 716, 0),
            "iltp-60s": (2754, 1233, 723, 0),
            "qmltp-10s": (2972, 1986, 1758, 1),
            "qmltp-60s": (2972, 2004, 1769, 1)
        }
        for name, counts in expected.items():
            with self.subTest(run=name):
                summary = audit_run(DIRECTORY / "results" / (name + ".jsonl"))
                self.assertEqual(tuple(summary[key] for key in (
                    "cases", "solved", "expected_matches", "expected_mismatches"
                )), counts)

    def test_audit_rejects_duplicate_and_mislabelled_results(self):
        source = DIRECTORY / "results/iltp-10s.jsonl"
        first = json.loads(source.read_text().splitlines()[0])
        metadata = json.loads(source.with_suffix(".metadata.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.jsonl"
            path.with_suffix(".skips.jsonl").write_text("")
            for rows in ([first, first], [{**first, "matches_expected": False}]):
                path.write_text("".join(json.dumps(r) + "\n" for r in rows))
                path.with_suffix(".metadata.json").write_text(json.dumps({
                    **metadata, "case_count": len(rows),
                    "case_set_sha256": case_set_hash(r["case_id"] for r in rows)
                }))
                with self.assertRaises(ValueError):
                    audit_run(path)

    def test_cli_run_resume_report_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ABC001+1.p").write_text(
                "% Status (intuit.) : Theorem\nfof(con,conjecture,(p => p)).\n"
            )
            output = root / "run.jsonl"
            command = [
                "iltp", str(root), "--output", str(output), "--timeout-ms", "1000"
            ]
            self.assertEqual(self._cli(command), 0)
            original = output.read_bytes()
            self.assertEqual(self._cli(command), 0)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(self._cli(["audit", str(output)]), 0)
            cases, skipped = load_cases([root])
            self.assertEqual(audit_run(output, cases, skipped)["solved"], 1)
            csv = root / "export.csv"
            self.assertEqual(self._cli(["report", str(output), "--csv", str(csv)]), 0)
            self.assertIn("matches_expected", csv.read_text())
            artifacts = (output, output.with_suffix(".metadata.json"),
                         output.with_suffix(".skips.jsonl"))
            original = {path: path.read_bytes() for path in artifacts}
            for path in artifacts:
                with self.subTest(destination=path.name):
                    self.assertEqual(self._cli([
                        "report", str(output), "--csv", str(path)
                    ]), 2)
            self.assertEqual({path: path.read_bytes() for path in artifacts}, original)
            self.assertEqual(self._cli([
                "report", str(output), "--csv",
                str(DIRECTORY / "results/iltp-10s.jsonl")
            ]), 2)

    def test_cli_protects_artifacts_sharing_an_output_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ABC001+1.p").write_text("fof(con,conjecture,(p => p)).\n")
            results = root / "results"
            results.mkdir()
            metadata = results / "run.metadata.json"
            metadata.write_text("protected")
            (results / "manifest.json").write_text(json.dumps({
                "files": {"run.metadata.json": "unused"}
            }))
            with patch("benchmarks.validity.run.DIRECTORY", root):
                self.assertEqual(self._cli([
                    "iltp", str(root), "--output", str(results / "run.scratch")
                ]), 2)
            self.assertEqual(metadata.read_text(), "protected")
            self.assertFalse((results / "run.scratch").exists())

    @staticmethod
    def _cli(arguments):
        with patch("sys.argv", ["benchmarks.validity.run", *arguments]):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                return main()


if __name__ == "__main__":
    unittest.main()

