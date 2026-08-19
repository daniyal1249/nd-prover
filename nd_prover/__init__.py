__version__ = "3.2.0"
__author__ = "Daniyal Akif"
__email__ = "daniyalakif@gmail.com"
__license__ = "Apache-2.0"
__description__ = "Natural deduction proof generator & checker"
__url__ = "https://github.com/daniyal1249/nd-prover"


from .checker import (
    InferenceError, ProofEditError, SemanticsError, Rule, Justification, 
    Rules, IPL, TFL, IFOL, FOL, IK, K, IT, T, IS4, S4, IS5, S5, IQK, QK, 
    IQT, QT, IQS4, QS4, IQS5, QS5, ProofObject, Line, Proof, Problem, 
    intuitionistic, first_order, modal, reflexive, transitive, s5, 
    resolve_semantics
)
from .cli import (
    logics, parse_and_verify_formula, parse_and_verify_premises, 
    select_logic, input_premises, input_conclusion, create_problem, 
    select_edit, input_line, input_assumption, perform_edit, main
)
from .latex import (
    formula_to_latex, justification_to_latex, problem_to_latex
)
from .parser import (
    ParsingError, Symbols, split_line, strip_parens, find_main_connective, 
    split_args, parse_args_from_parens, parse_term, _parse_formula, 
    parse_formula, parse_assumption, parse_rule, parse_citations, 
    parse_justification, parse_line
)
from .prover import (
    ProverError, ProofSearchResult, _ProofObject, _Line, _Proof, 
    Eliminator, Introducer, Prover, Processor, prove
)
from .sat import (
    Countermodel, ValidityResult, Translator, prop_vars, evaluate, 
    check_validity_tfl, check_validity
)
from .syntax import (
    Metavar, Formula, Bot, Not, And, Or, Imp, Iff, Term, Func, Var, Pred, 
    Eq, Forall, Exists, Box, Dia, BoxMarker, is_tfl_formula, 
    is_fol_formula, is_ml_formula, is_constant, is_ground_term, terms, 
    constants, ground_terms, free_vars, sub_term
)


__all__ = [name for name in globals() if not name.startswith("__")]
