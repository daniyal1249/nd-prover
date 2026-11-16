import re

from nd_prover import *

from .latex import formula


EQUIVALENCES = {"20C", "36H", "38B", "38C", "39B", "39C"}


def split_formulas(text):
    depth, start, parts = 0, 0, []
    for index, ch in enumerate(text + ","):
        if ch in "{([":
            depth += 1
        elif ch in "})]":
            depth -= 1
        elif ch == "," and depth == 0 and (index == 0 or text[index - 1] != "\\"):
            if text[start:index].strip():
                parts.append(text[start:index].strip())
            start = index + 1
    if depth:
        raise ValueError("Unbalanced problem statement.")
    return parts


def translate(text):
    return str(parse_formula(formula(text)))


def declared_argument(context):
    if "\\item" not in context:
        return None, None
    matches = list(re.finditer(r"\$([^$]*)\$", context, re.S))
    for index in range(len(matches) - 1, -1, -1):
        parts = re.split(r"\\(?:therefore|vdash|proves)(?![A-Za-z])", matches[index][1])
        if len(parts) != 2:
            continue
        goal = re.sub(r"^\s*_\s*\\ml(?:Sfour|Sfive|K|T)\b", "", parts[1])
        prefix = parts[0]
        while index and re.fullmatch(r"[\s,]*", context[matches[index - 1].end():matches[index].start()]):
            index -= 1
            prefix = matches[index][1] + "," + prefix
        return [translate(part) for part in split_formulas(prefix)], translate(goal)
    return None, None


def problem_statement(context, exercise, proof_premises, proof_goal):
    if exercise == "39D":
        arguments = re.findall(r"\\begin\{earg\}(.*?)\\end\{earg\}", context, re.S)
        text = arguments[-1]
        formulas = re.findall(r"\$([^$]*)\$", text, re.S)
        premises = [translate(re.split(r"\\therefore\b", part)[0]) for part in formulas[:-1]]
        return premises, translate(formulas[-1]), "argument", text
    premises, conclusion = declared_argument(context)
    if premises is not None:
        return premises, conclusion, "argument", context.strip()
    header = context.split(r"\myanswer", 1)[0]
    if exercise in EQUIVALENCES:
        formulas = [translate(part) for text in re.findall(r"\$([^$]*)\$", header, re.S)
                    for part in split_formulas(text)]
        if len(formulas) not in {2, 3} or len(proof_premises) != 1 or proof_premises[0] not in formulas:
            raise ValueError(f"Cannot match the printed equivalence in {exercise}.")
        index = formulas.index(proof_premises[0])
        return proof_premises, formulas[(index + 1) % len(formulas)], "equivalence", header.strip()
    if exercise in {"20A", "38A"}:
        formulas = [translate(part) for text in re.findall(r"\$([^$]*)\$", header, re.S)
                    for part in split_formulas(text)]
        if exercise == "20A" and len(formulas) == 1:
            return [], formulas[0], "theorem", header.strip()
        if exercise == "38A" and formulas:
            return formulas, "⊥", "inconsistency", header.strip()
        raise ValueError(f"Cannot read the printed statement in {exercise}.")
    if exercise not in {"17B", "19A", "21A", "36B", "36C", "40A"}:
        raise ValueError(f"Missing independent problem statement in {exercise}.")
    return proof_premises, proof_goal, "reference", ""

