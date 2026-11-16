import unittest

from benchmarks.validity.metrics import problem_metrics
from benchmarks.validity.tptp import parse_text
from nd_prover import *


class BenchmarkMetricsTests(unittest.TestCase):

    def test_counts_formula_and_term_structure(self):
        x = Var("x")
        c = Func("c", ())
        formula = Forall(
            x,
            And(Pred("p", (x,)), Box(Pred("q", (c,))))
        )
        problem = Problem(QK, [], formula, "constant")

        metrics = problem_metrics(problem)

        self.assertEqual(metrics["formula_count"], 1)
        self.assertEqual(metrics["quantifiers"], 1)
        self.assertEqual(metrics["modal_operators"], 1)
        self.assertEqual(metrics["distinct_predicates"], 2)
        self.assertEqual(metrics["distinct_functions"], 1)
        self.assertEqual(metrics["distinct_variables"], 1)

    def test_importer_balances_long_associative_formula(self):
        atoms = [f"p{idx}" for idx in range(2001)]
        source = f"fof(long, conjecture, ({' & '.join(atoms)}))."
        formula = parse_text(source).formulas[0].formula
        problem = Problem(IPL, [], formula)

        metrics = problem_metrics(problem)

        self.assertEqual(metrics["connectives"], 2000)
        self.assertEqual(metrics["distinct_predicates"], 2001)
        self.assertLess(metrics["max_formula_depth"], 20)


if __name__ == "__main__":
    unittest.main()

