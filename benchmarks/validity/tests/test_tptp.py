import tempfile
import unittest
from pathlib import Path

from benchmarks.validity.metrics import problem_metrics
from benchmarks.validity.tptp import (
    TPTPError, UnsupportedTPTPFeature, parse_text, resolve_file, universal_close
)
from nd_prover import *


class TPTPBenchmarkParserTests(unittest.TestCase):

    def test_parses_iltp_formula_directly_to_ast(self):
        parsed = parse_text("""
            fof(con_name,conjecture,(
              ! [X,Y,Z] :
                ((con(X,Y) & (~apt(Z,X) & ~apt(Z,Y)))
                 => ~dipt(Z,pt(X,Y)))
            )).
        """)

        formula = parsed.formulas[0].formula
        self.assertIsInstance(formula, Forall)
        self.assertIsInstance(formula.inner.inner.inner, Imp)
        self.assertIsInstance(formula.inner.inner.inner.left, And)

    def test_quantifier_scope_follows_tptp_unitary_grammar(self):
        parsed = parse_text("fof(a,axiom,(! [X] : p(X) & q)).")
        formula = parsed.formulas[0].formula

        self.assertIsInstance(formula, And)
        self.assertIsInstance(formula.left, Forall)
        self.assertIsInstance(formula.right, Pred)

    def test_internal_ast_has_no_interactive_identifier_limits(self):
        variables = ",".join(f"X{i}" for i in range(30))
        atoms = " & ".join(
            f"predicate_{i}(constant_{i},X0)" for i in range(35)
        )
        parsed = parse_text(
            f"fof(con,conjecture,(! [{variables}] : ({atoms})))."
        )
        formula = universal_close(parsed.formulas[0].formula)
        problem = Problem(IFOL, [], formula)
        metrics = problem_metrics(problem)

        self.assertEqual(metrics["distinct_predicates"], 35)
        self.assertEqual(metrics["distinct_functions"], 35)
        self.assertEqual(metrics["distinct_variables"], 30)

    def test_parses_deeply_parenthesized_associative_formula(self):
        formula = "p0"
        for idx in range(1500):
            formula = f"({formula} & p{idx + 1})"

        parsed = parse_text(f"fof(con,conjecture,{formula}).")
        problem = Problem(IPL, [], parsed.formulas[0].formula)
        metrics = problem_metrics(problem)

        self.assertEqual(metrics["distinct_predicates"], 1501)
        self.assertLess(metrics["max_formula_depth"], 20)

    def test_parses_qmltp_box(self):
        parsed = parse_text("""
            qmf(con,conjecture,
              ((! [X] : (#box : f(X))) => (#box : (! [X] : f(X))))).
        """)
        formula = parsed.formulas[0].formula

        self.assertIsInstance(formula, Imp)
        self.assertIsInstance(formula.left, Forall)
        self.assertIsInstance(formula.left.inner, Box)
        self.assertIsInstance(formula.right, Box)

    def test_rejects_indexed_modalities(self):
        with self.assertRaises(UnsupportedTPTPFeature) as cm:
            parse_text("qmf(con,conjecture,(#box(a) : p)).")
        self.assertEqual(cm.exception.feature, "MULTIMODAL")

    def test_resolves_includes_and_selection_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Axioms").mkdir()
            (root / "Axioms" / "base.ax").write_text(
                "fof(a1,axiom,p).\nfof(a2,axiom,q).\n"
            )
            problem = root / "ABC001+1.p"
            problem.write_text(
                "include('Axioms/base.ax',[a2]).\n"
                "fof(con,conjecture,q).\n"
            )

            formulas = resolve_file(problem, root)
            self.assertEqual([f.name for f in formulas], ["a2", "con"])

    def test_comment_markers_inside_quoted_atoms_are_preserved(self):
        parsed = parse_text("fof(a,axiom,'name%with/*markers*/').")
        self.assertEqual(len(parsed.formulas), 1)

    def test_skips_unneeded_tptp_annotations(self):
        parsed = parse_text(
            "fof(a,axiom,p,file('dir/a-b.p',source),[useful{info}])."
        )
        self.assertEqual(len(parsed.formulas), 1)

    def test_normalizes_nand_and_reverse_implication(self):
        parsed = parse_text("fof(a,axiom,((p ~& q) <= r)).")
        formula = parsed.formulas[0].formula

        self.assertIsInstance(formula, Imp)
        self.assertIsInstance(formula.right, Not)

    def test_empty_include_selection_imports_no_axioms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "base.ax").write_text("fof(a,axiom,p).\n")
            problem = root / "ABC001+1.p"
            problem.write_text("include('base.ax',[]).\nfof(c,conjecture,q).\n")
            self.assertEqual([f.name for f in resolve_file(problem, root)], ["c"])
            problem.write_text("include('base.ax',[missing]).\n")
            with self.assertRaises(TPTPError):
                resolve_file(problem, root)

    def test_include_cycle_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ABC001+1.p"
            path.write_text("include('ABC001+1.p').\n")
            with self.assertRaises(TPTPError):
                resolve_file(path)

    def test_unsupported_semantics_are_not_silently_discarded(self):
        for source in ("fof(a,axiom,p(1)).", "tpi(a,set_logic,k)."):
            with self.subTest(source=source), self.assertRaises(UnsupportedTPTPFeature):
                parse_text(source)


if __name__ == "__main__":
    unittest.main()

