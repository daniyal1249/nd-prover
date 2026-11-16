import tempfile
import unittest
from pathlib import Path

from benchmarks.validity.qmltp import load_cases
from nd_prover import *


HEADER = """
% Status       : varying cumulative constant
% K              Non-Theorem Non-Theorem Theorem v1.1
% D              Non-Theorem Non-Theorem Theorem v1.1
% T              Non-Theorem Non-Theorem Theorem v1.1
% S4             Non-Theorem Non-Theorem Theorem v1.1
% S5             Non-Theorem Theorem Theorem v1.1
% Rating       : varying cumulative constant
% K              0.50 0.75 0.25 v1.1
% D              0.50 0.75 0.25 v1.1
% T              0.50 0.75 0.25 v1.1
% S4             0.50 0.75 0.25 v1.1
% S5             0.50 0.75 0.25 v1.1
"""


class QMLTPBenchmarkTests(unittest.TestCase):

    def test_expands_quantified_problem_into_supported_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SYM001+1.p").write_text(HEADER + """
                qmf(con,conjecture,
                  ((! [X] : (#box : f(X))) => (#box : (! [X] : f(X))))).
            """)

            cases, skipped = load_cases(root)

            self.assertFalse(skipped)
            self.assertEqual(len(cases), 7)
            configs = {
                (case.problem.logic, case.source_domain)
                for case in cases
            }
            self.assertEqual(configs, {
                (QK, "cumulative"), (QK, "constant"),
                (QT, "cumulative"), (QT, "constant"),
                (QS4, "cumulative"), (QS4, "constant"),
                (QS5, "constant")
            })

            k_constant = next(
                case for case in cases
                if case.source_logic == "K"
                and case.source_domain == "constant"
            )
            self.assertEqual(k_constant.source_status, "Theorem")
            self.assertEqual(k_constant.source_rating, 0.25)

    def test_known_source_issue_is_not_counted_as_gold_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SYM052+1.p").write_text(HEADER + """
                qmf(con,conjecture,(#box : p)).
            """)

            cases, skipped = load_cases(root)

            self.assertFalse(skipped)
            self.assertTrue(cases)
            self.assertTrue(all(case.metadata["source_warning"] for case in cases))
            self.assertTrue(all(case.metadata["exclude_from_gold"] for case in cases))
            self.assertTrue(all(case.expected_status is None for case in cases))

    def test_accepts_known_original_parenthesization_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "APM004+1.p").write_text(HEADER + """
                qmf(ax1,axiom,(#box : (? [B] : bomb(B)))).
                qmf(ax2,axiom,
                  (? [A] : (#box : (! [X] :
                    (bomb(X) & h(A) => (#box : bomb(X))))))).
                qmf(con,conjecture,(#box : (! [X] : bomb(X)))).
            """)

            cases, skipped = load_cases(root)

            self.assertFalse(skipped)
            self.assertEqual(len(cases), 7)
            self.assertTrue(all(
                case.metadata["source_warning"] for case in cases
            ))
            self.assertTrue(all(
                not case.metadata["exclude_from_gold"] for case in cases
            ))

    def test_records_multimodal_and_classical_skips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "MML001+1.p").write_text(
                "qmf(con,conjecture,(#box(a) : p)).\n"
            )
            (root / "NLP001+1.p").write_text(
                HEADER + "qmf(con,conjecture,(p => p)).\n"
            )

            cases, skipped = load_cases(root)

            self.assertFalse(cases)
            self.assertEqual(
                {item.reason for item in skipped},
                {"MULTIMODAL", "CLASSICAL_ONLY"}
            )


if __name__ == "__main__":
    unittest.main()

