__version__ = "2.1.0"
__author__ = "Daniyal Akif"
__email__ = "daniyalakif@gmail.com"
__license__ = "Apache-2.0"
__description__ = "Natural deduction proof generator & checker"
__url__ = "https://github.com/daniyal1249/nd-prover"


from .checker import (
    InferenceError, ProofEditError, Rule, Justification, Rules, TFL, FOL, 
    MLK, MLT, MLS4, MLS5, FOMLK, FOMLT, FOMLS4, FOMLS5, ProofObject, 
    Line, Proof, Problem, verify_arity, assumption_constants
)
from .cli import (
    logics, parse_and_verify_formula, parse_and_verify_premises, 
    select_logic, input_premises, input_conclusion, create_problem, 
    select_edit, input_line, input_assumption, perform_edit, main
)
from .parser import (
    ParsingError, Symbols, split_line, strip_parens, find_main_connective, 
    split_args, parse_args_from_parens, parse_term, _parse_formula, 
    parse_formula, parse_assumption, parse_rule, parse_citations, 
    parse_justification, parse_line
)
from .prover import (
    ProverError, _ProofObject, _Line, _Proof, Eliminator, Introducer, 
    Prover, Processor, find_subproof, prove
)
from .syntax import (
    Metavar, Formula, Bot, Not, And, Or, Imp, Iff, Term, Func, Var, Pred, 
    Eq, Forall, Exists, Box, Dia, BoxMarker, is_tfl_formula, 
    is_fol_formula, is_fol_sentence, is_ml_formula, atomic_terms, 
    constants, free_vars, sub_term
)
from .tfl_sat import prop_vars, evaluate, countermodel, is_valid


__all__ = [name for name in globals() if not name.startswith("__")]
