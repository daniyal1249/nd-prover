from nd_prover import *


def make_problem(spec, derived_rules):
    logic = {"TFL": TFL, "FOL": FOL, "K": K, "T": T, "S4": S4, "S5": S5}[spec.logic]
    return Problem(
        logic, [parse_formula(p) for p in spec.premises],
        parse_formula(spec.conclusion), derived_rules=derived_rules
    )


def proof_lines(problem):
    yield from problem.proof.context

    def walk(seq):
        for obj in seq:
            if obj.is_line():
                yield obj
            else:
                yield from walk(obj.seq)

    yield from walk(problem.proof.seq)


def count_proof(problem):
    labels = [line.justification.rule.name for line in proof_lines(problem)]
    rules = sorted(set(labels) - {"PR", "AS"})
    return {
        "proof_lines": len(labels),
        "generated_lines": len(labels) - labels.count("PR"),
        "assumptions": labels.count("AS"),
        "distinct_rules": len(rules),
        "distinct_rules_with_assumptions": len(set(labels) - {"PR"}),
        "rules": rules
    }


def serialize_proof(proof):
    return [
        {
            "index": obj.idx, "formula": str(obj.formula),
            "rule": obj.justification.rule.name,
            "citations": obj.justification.citations
        } if obj.is_line() else {"subproof": serialize_proof(obj)}
        for obj in proof.seq
    ]


def restore_proof(spec, payload, derived_rules, validate=True):
    problem = make_problem(spec, derived_rules)
    next_index = len(problem.premises) + 1

    def build(items, context, nested=False):
        nonlocal next_index
        if nested and (not items or items[0].get("rule") != "AS"):
            raise ValueError("A subproof must begin with an assumption.")
        seq = []
        for position, item in enumerate(items):
            if "subproof" in item:
                scope = context + seq
                child = build(item["subproof"], scope, nested=True)
                seq.append(Proof(child, scope, None))
                continue
            if item["index"] != next_index:
                raise ValueError("Proof line numbers are not consecutive.")
            next_index += 1
            name = item["rule"]
            formula = (parse_assumption if name == "AS" else parse_formula)(item["formula"])
            (problem.verify_assumption if name == "AS" else problem.verify_formula)(formula)
            if name == "AS":
                if not nested or position != 0 or item["citations"]:
                    raise ValueError("Misplaced assumption in saved proof.")
                rule = Rules.AS
            else:
                if name == "PR":
                    raise ValueError("Premises belong in the root context.")
                if name not in Rules.rules:
                    raise ValueError(f"Unknown proof rule: {name}.")
                rule = Rule(name, getattr(problem.logic, Rules.rules[name]))
                problem.verify_rule(rule)
            citations = tuple(
                tuple(c) if isinstance(c, (list, tuple)) else c
                for c in item["citations"]
            )
            seq.append(Line(item["index"], formula, Justification(rule, citations)))
        return seq

    problem.proof.seq = build(payload, problem.proof.context)
    if validate and (problem.errors() or not problem.conclusion_reached()):
        raise ValueError("The saved proof does not establish its conclusion.")
    return problem


def proof_shape(problem):
    def walk(proof, depth):
        children = [obj for obj in proof.seq if not obj.is_line()]
        shapes = [walk(child, depth + 1) for child in children]
        return max([depth] + [shape[0] for shape in shapes]), len(children) + sum(shape[1] for shape in shapes)

    depth, count = walk(problem.proof, 0)
    return {"max_subproof_depth": depth, "subproof_count": count}

