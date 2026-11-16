import tempfile
import unittest
from pathlib import Path

from benchmarks.validity.iltp import load_cases
from nd_prover import *


class ILTPBenchmarkTests(unittest.TestCase):

    def test_loads_include_axioms_and_header_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Axioms").mkdir()
            (root / "Axioms" / "GEJ001+1.ax").write_text(
                "fof(a1,axiom,(! [X] : p(X))).\n"
            )
            (root / "GEJ003+1.p").write_text("""
                % Status (intuit.) : Theorem
                % Rating (intuit.) : 0.75 v1.1.2
                include('Axioms/GEJ001+1.ax').
                fof(con,conjecture,(! [X] : p(X))).
            """)

            cases, skipped = load_cases([root])

            self.assertEqual(len(skipped), 0)
            self.assertEqual(len(cases), 1)
            case = cases[0]
            self.assertIs(case.problem.logic, IFOL)
            self.assertEqual(len(case.problem.premises), 1)
            self.assertEqual(case.source_status, "Theorem")
            self.assertEqual(case.source_rating, 0.75)

    def test_accepts_problems_directory_as_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Problems").mkdir()
            (root / "Axioms").mkdir()
            (root / "Axioms" / "base.ax").write_text(
                "fof(a1,axiom,p).\n"
            )
            (root / "Problems" / "ABC001+1.p").write_text(
                "include('Axioms/base.ax').\n"
                "fof(con,conjecture,p).\n"
            )

            cases, skipped = load_cases([root / "Problems"])

            self.assertFalse(skipped)
            self.assertEqual(len(cases), 1)
            self.assertEqual(len(cases[0].problem.premises), 1)

    def test_statistics_manifest_filters_support_files(self):
        with tempfile.TemporaryDirectory() as directory:
            outer = Path(directory)
            root = outer / "ILTP-v1.1.2-firstorder"
            (root / "Problems").mkdir(parents=True)
            (root / "Axioms").mkdir()
            (root / "Problems" / "ABC001+1.p").write_text(
                "fof(con,conjecture,p).\n"
            )
            # Deliberately use a problem-looking filename in a support folder.
            (root / "Axioms" / "DEF001+1.p").write_text(
                "fof(a1,axiom,q).\n"
            )
            stats = outer / "ILTP-v1.1.2-fof-statistics.txt"
            stats.write_text("ABC001+1 Theorem 0.00\n")

            cases, skipped = load_cases([outer], stats)

            self.assertFalse(skipped)
            self.assertEqual([case.problem_id for case in cases], ["ABC001+1"])

            cases, skipped = load_cases([outer])
            self.assertFalse(skipped)
            self.assertEqual([case.problem_id for case in cases], ["ABC001+1"])

    def test_statistics_override_header_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SYJ001+1.p").write_text("""
                % Status (intuit.) : Open
                fof(con,conjecture,(p => p)).
            """)
            stats = root / "ILTP-v1.1.2-prop-statistics.txt"
            stats.write_text("SYJ001+1 Theorem 0.25\n")

            cases, skipped = load_cases([root], stats)

            self.assertFalse(skipped)
            self.assertEqual(cases[0].source_status, "Theorem")
            self.assertEqual(cases[0].source_rating, 0.25)


if __name__ == "__main__":
    unittest.main()

