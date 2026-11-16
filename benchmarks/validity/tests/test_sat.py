import unittest
from unittest.mock import patch

from nd_prover import *


class FakeSolver:

    def add(self, *args):
        pass


class FakeTranslator:

    extracted = False
    produce_models = None

    def __init__(
        self, logic, domain_semantics, equality_semantics,
        produce_models, small, deadline
    ):
        FakeTranslator.produce_models = produce_models
        self.root = object()
        self.worlded = True
        self.solver = FakeSolver()

    def translate(self, formula, world):
        return formula

    def semantic_constraints(self):
        return []

    def check(self):
        return sat.smt.sat

    def extract(self):
        FakeTranslator.extracted = True
        return object()

    def minimize(self):
        FakeTranslator.extracted = True
        return object()


class BenchmarkSatTests(unittest.TestCase):

    def test_solver_model_option_follows_the_request(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                translator = Translator(IPL, produce_models=enabled, small=False)
                actual = translator.solver.solver.getOption("produce-models")
                self.assertEqual(actual, "true" if enabled else "false")

    def test_real_validity_check_skips_extraction_and_minimization(self):
        with patch.object(Translator, "extract", side_effect=AssertionError), \
                patch.object(Translator, "minimize", side_effect=AssertionError):
            result = sat.check_validity(
                IPL, [], Pred("P", ()), countermodel=False, timeout=1000
            )
        self.assertEqual(result.status, "invalid")
        self.assertIsNone(result.countermodel)

    def test_requested_countermodels_still_work(self):
        for small in (False, True):
            with self.subTest(small=small):
                result = sat.check_validity(
                    IPL, [], Pred("P", ()), countermodel=True,
                    small=small, timeout=2000
                )
                self.assertEqual(result.status, "invalid")
                self.assertIsNotNone(result.countermodel)

    def test_countermodel_disabled_for_truth_table_shortcut(self):
        result = sat.check_validity(
            TFL, [], Pred("P", ()), timeout=None, countermodel=False
        )
        self.assertEqual(result.status, "invalid")
        self.assertIsNone(result.countermodel)

    def test_countermodel_can_be_disabled(self):
        FakeTranslator.extracted = False
        FakeTranslator.produce_models = None

        with patch.object(sat, "Translator", FakeTranslator), patch.object(
            sat.smt, "Not", side_effect=lambda formula: formula
        ):
            result = sat.check_validity(
                IPL, [], Pred("P", ()), timeout=None, countermodel=False
            )

        self.assertEqual(result.status, "invalid")
        self.assertIsNone(result.countermodel)
        self.assertFalse(FakeTranslator.extracted)
        self.assertIs(FakeTranslator.produce_models, False)


if __name__ == "__main__":
    unittest.main()

