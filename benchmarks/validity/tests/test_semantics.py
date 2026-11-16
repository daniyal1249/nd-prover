from pathlib import Path
from itertools import product
import json
import unittest

from benchmarks.validity.corpus import split_problem
from benchmarks.validity.qmltp import load_cases
from benchmarks.validity.provenance import file_hash
from benchmarks.validity.tptp import parse_file
from nd_prover import *


FIXTURES = Path(__file__).resolve().parent / "fixtures"
COUNTERMODEL = FIXTURES.parents[1] / "countermodels/GSY374+1-QT-expanding.json"


def evaluate_countermodel(formula, world, domains, edges, predicates, env=None):
    """Evaluate the source AST in a finite model without using cvc5."""
    env = {} if env is None else env

    def holds(inner, at=world, bindings=env):
        return evaluate_countermodel(inner, at, domains, edges, predicates, bindings)

    match formula:
        case Bot():
            return False
        case Pred(name, args):
            values = tuple(env[arg.name] for arg in args)
            return (world, *values) in predicates.get(name, set())
        case Eq(Var(left), Var(right)):
            return env[left] == env[right]
        case Not(inner):
            return not holds(inner)
        case And(left, right):
            return holds(left) and holds(right)
        case Or(left, right):
            return holds(left) or holds(right)
        case Imp(left, right):
            return not holds(left) or holds(right)
        case Iff(left, right):
            return holds(left) == holds(right)
        case Box(inner):
            return all(
                holds(inner, target) for source, target in edges if source == world
            )
        case Dia(inner):
            return any(
                holds(inner, target) for source, target in edges if source == world
            )
        case Forall(var, inner):
            return all(
                holds(inner, bindings={**env, var.name: d}) for d in domains[world]
            )
        case Exists(var, inner):
            return any(
                holds(inner, bindings={**env, var.name: d}) for d in domains[world]
            )
    raise TypeError(f"Unsupported formula in finite-model test: {type(formula)}")


class SourceSemanticsTests(unittest.TestCase):

    def test_gsy374_has_a_reflexive_expanding_countermodel(self):
        model = json.loads(COUNTERMODEL.read_text())
        self.assertEqual(file_hash(FIXTURES / "GSY374+1.p"), model["source_sha256"])
        parsed = parse_file(FIXTURES / "GSY374+1.p")
        premises, conclusion = split_problem(parsed.formulas)
        self.assertFalse(premises)
        domains = {w: set(d) for w, d in model["domains"].items()}
        edges = {tuple(edge) for edge in model["accessibility"]}
        predicates = {
            "tptp_pred_" + name.encode().hex(): {tuple(row) for row in rows}
            for name, rows in model["predicates"].items()
        }
        self.assertTrue(all((w, w) in edges for w in domains))
        self.assertTrue(all(domains[a] <= domains[b] for a, b in edges))
        self.assertNotIn(("w0", "w2"), edges)
        self.assertFalse(evaluate_countermodel(
            conclusion, model["root_world"], domains, edges, predicates
        ))
        for edge in edges:
            if edge[0] != edge[1]:
                self.assertTrue(evaluate_countermodel(
                    conclusion, model["root_world"], domains, edges - {edge}, predicates
                ))
        for name, extension in predicates.items():
            for atom in extension:
                reduced = {**predicates, name: extension - {atom}}
                self.assertTrue(evaluate_countermodel(
                    conclusion, model["root_world"], domains, edges, reduced
                ))
        result = check_validity(QT, [], conclusion, "expanding", timeout=2000)
        self.assertEqual(result.status, "invalid")

    def test_saved_model_is_minimal_in_singleton_domain_reflexive_models(self):
        model = json.loads(COUNTERMODEL.read_text())
        conclusion = parse_file(FIXTURES / "GSY374+1.p").formulas[0].formula
        predicate = "tptp_pred_" + "big_p".encode().hex()
        for count in (1, 2, 3):
            countermodels = []
            worlds = tuple(f"w{i}" for i in range(count))
            domains = {w: {"d0"} for w in worlds}
            reflexive = {(w, w) for w in worlds}
            optional = [(a, b) for a in worlds for b in worlds if a != b]
            for mask in product((False, True), repeat=len(optional)):
                edges = reflexive | {edge for edge, keep in zip(optional, mask) if keep}
                for valuation in product((False, True), repeat=count):
                    extension = {
                        (w, "d0") for w, value in zip(worlds, valuation) if value
                    }
                    if not evaluate_countermodel(
                        conclusion, "w0", domains, edges, {predicate: extension}
                    ):
                        countermodels.append((len(edges), len(extension)))
            if count < 3:
                self.assertFalse(countermodels)
            else:
                self.assertEqual(min(edges for edges, _ in countermodels),
                                 model["minimality"]["accessibility_edges"])
                self.assertEqual(min(atoms for _, atoms in countermodels),
                                 model["minimality"]["positive_predicate_instances"])

    def test_native_inequality_changes_sym052_constant_status(self):
        cases, skipped = load_cases(FIXTURES)
        self.assertFalse(skipped)
        case = next(c for c in cases if c.problem_id == "SYM052+1"
                    and c.problem.logic is QK and c.source_domain == "constant")
        self.assertEqual(case.source_status, "Non-Theorem")
        result = check_validity(
            QK, [], case.problem.conclusion, "constant", timeout=2000
        )
        self.assertEqual(result.status, "valid")
        self.assertIsNone(case.expected_status)

    def test_equality_source_exclusions_remain_explicit(self):
        cases, _ = load_cases(FIXTURES)
        excluded = [c for c in cases if c.metadata["exclude_from_gold"]]
        self.assertEqual(len(excluded), 14)
        self.assertTrue(all(c.expected_status is None for c in excluded))


if __name__ == "__main__":
    unittest.main()

