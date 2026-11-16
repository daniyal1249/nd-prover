from nd_prover import *


def problem_metrics(problem):
    metrics = {
        "premise_count": len(problem.premises),
        "formula_count": len(problem.premises) + 1,
        "formula_nodes": 0,
        "term_nodes": 0,
        "atom_occurrences": 0,
        "connectives": 0,
        "quantifiers": 0,
        "modal_operators": 0,
        "equality_occurrences": 0,
        "max_formula_depth": 0,
        "max_term_depth": 0
    }
    predicates, functions, variables = set(), set(), set()

    formulas = problem.premises + [problem.conclusion]
    stack = [(formula, 1) for formula in formulas]
    while stack:
        formula, depth = stack.pop()
        metrics["formula_nodes"] += 1
        metrics["max_formula_depth"] = max(
            metrics["max_formula_depth"], depth
        )

        match formula:
            case Bot():
                metrics["atom_occurrences"] += 1
            case Pred(name, args):
                metrics["atom_occurrences"] += 1
                predicates.add((name, len(args)))
                for term in args:
                    _term_metrics(
                        term, metrics, functions, variables
                    )
            case Eq(left, right):
                metrics["atom_occurrences"] += 1
                metrics["equality_occurrences"] += 1
                _term_metrics(left, metrics, functions, variables)
                _term_metrics(right, metrics, functions, variables)
            case Not(inner):
                metrics["connectives"] += 1
                stack.append((inner, depth + 1))
            case And(left, right) | Or(left, right) | Imp(left, right) | Iff(
                left, right
            ):
                metrics["connectives"] += 1
                stack.append((left, depth + 1))
                stack.append((right, depth + 1))
            case Forall(var, inner) | Exists(var, inner):
                metrics["quantifiers"] += 1
                variables.add(var.name)
                stack.append((inner, depth + 1))
            case Box(inner) | Dia(inner):
                metrics["modal_operators"] += 1
                stack.append((inner, depth + 1))

    metrics["distinct_predicates"] = len(predicates)
    metrics["distinct_functions"] = len(functions)
    metrics["distinct_variables"] = len(variables)
    return metrics


def _term_metrics(term, metrics, functions, variables):
    stack = [(term, 1)]
    while stack:
        current, depth = stack.pop()
        metrics["term_nodes"] += 1
        metrics["max_term_depth"] = max(metrics["max_term_depth"], depth)

        match current:
            case Var(name):
                variables.add(name)
            case Func(name, args):
                functions.add((name, len(args)))
                stack.extend((arg, depth + 1) for arg in args)

