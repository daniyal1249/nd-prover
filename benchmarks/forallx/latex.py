import re

from nd_prover import *


RULES = {
    "ae": "∧E", "ai": "∧I", "oe": "∨E", "oi": "∨I",
    "ce": "→E", "ci": "→I", "be": "↔E", "bi": "↔I",
    "ni": "¬I", "ne": "¬E", "ri": "¬E", "re": "X",
    "ip": "IP", "dne": "DNE", "ds": "DS", "mt": "MT",
    "dem": "DeM", "tnd": "LEM", "Ae": "∀E", "Ai": "∀I",
    "Ee": "∃E", "Ei": "∃I", "cq": "CQ", "ii": "=I", "ie": "=E",
    "boxi": "☐I", "boxe": "☐E", "diadf": "Def◇", "mc": "MC",
    "rt": "RT", "rfour": "R4", "rfive": "R5"
}
SYMBOLS = {
    "eand": "∧", "land": "∧", "eor": "∨", "lor": "∨",
    "eif": "→", "eiff": "↔", "enot": "¬", "neg": "¬",
    "ered": "⊥", "bot": "⊥", "forall": "∀", "exists": "∃",
    "Box": "☐", "ebox": "☐", "Diamond": "◇", "ediamond": "◇",
    "bigl": "", "bigr": "", "left": "", "right": ""
}


def uncomment(text):
    return re.sub(r"(?<!\\)%[^\n]*", lambda match: " " * len(match[0]), text)


def group(text, position, opening="{", closing="}"):
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text) or text[position] != opening:
        raise ValueError(f"Expected {opening!r} near {text[position:position + 50]!r}.")
    start, depth = position + 1, 1
    position += 1
    while position < len(text):
        ch = text[position]
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if not depth:
                return text[start:position], position + 1
        position += 1
    raise ValueError("Unclosed LaTeX argument.")


def formula(text):
    output, position = [], 0
    while position < len(text):
        if text[position] != "\\":
            ch = text[position]
            output.append({"[": "(", "]": ")", "{": "", "}": "", "$": ""}.get(ch, ch))
            position += 1
            continue
        match = re.match(r"\\([A-Za-z]+|.)", text[position:])
        if not match:
            raise ValueError("Trailing backslash in formula.")
        command = match[1]
        position += len(match[0])
        if command == "atom":
            name, position = group(text, position)
            args, position = group(text, position)
            output.append(formula(name) + "(" + formula(args) + ")")
        elif command == "metav":
            value, position = group(text, position)
            output.append(formula(value))
        elif command in SYMBOLS:
            output.append(SYMBOLS[command])
        elif command in {",", ";", "!", " ", "quad", "qquad"}:
            continue
        else:
            raise ValueError(f"Unsupported formula command: \\{command}.")
    result = re.sub(r"\s+", "", "".join(output))
    return re.sub(r"([A-Z])([a-z]+)", lambda m: m[1] + "(" + ",".join(m[2]) + ")", result)


def parse_derivation(text):
    text = uncomment(text)
    position, depth, maximum, subproofs = 0, 0, 0, 0
    lines, labels, errors = [], {}, []
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        match = re.match(r"\\([A-Za-z]+)", text[position:])
        if not match:
            raise ValueError(f"Unexpected proof text: {text[position:position + 40]!r}.")
        command = match[1]
        position += len(match[0])
        if command == "open":
            depth += 1
            subproofs += 1
            maximum = max(maximum, depth)
            continue
        if command == "close":
            depth -= 1
            if depth < 0:
                raise ValueError("Subproof closes outside the root proof.")
            continue
        if command not in {"hypo", "have"}:
            raise ValueError(f"Unexpected proof command: {command}.")
        options = []
        while position < len(text) and text[position].isspace():
            position += 1
        while position < len(text) and text[position] == "[":
            value, position = group(text, position, "[", "]")
            options.append(value)
        label, position = group(text, position)
        raw, position = group(text, position)
        index = len(lines) + 1
        labels[label] = index
        rule, citations = None, []
        tail = re.match(r"\s*\\([A-Za-z]+)", text[position:])
        if tail and tail[1] in {*RULES, "by"}:
            position += len(tail[0])
            if tail[1] == "by":
                rule, position = group(text, position)
                rule = formula(rule)
            else:
                rule = RULES[tail[1]]
            citation_text, position = group(text, position)
            for citation in citation_text.split(","):
                citation = citation.strip()
                if not citation:
                    continue
                names = re.split(r"-+", citation)
                if any(name not in labels for name in names):
                    errors.append(f"Line {index}: unknown citation {citation}.")
                    citations.append(None)
                else:
                    values = [labels[name] for name in names]
                    citations.append(values[0] if len(values) == 1 else values)
        initial = depth == 0 and all(line["rule"] == "PR" for line in lines)
        if rule is None and initial:
            rule = "PR"
        elif command == "hypo" and rule is None:
            rule = "AS"
        elif rule is None:
            rule = "?"
            errors.append(f"Line {index}: missing justification.")
        try:
            translated = formula(raw)
            parsed = BoxMarker() if translated == "☐" else parse_formula(translated)
            translated = str(parsed)
        except (ValueError, ParsingError) as exc:
            translated = None
            errors.append(f"Line {index}: {exc}")
        lines.append({
            "index": index, "label": label, "depth": depth,
            "formula": translated, "formula_tex": raw, "rule": rule,
            "citations": citations, "numbering": options
        })
    if depth or not lines:
        raise ValueError("Incomplete or empty proof.")
    return {"lines": lines, "max_subproof_depth": maximum,
            "subproof_count": subproofs, "parse_errors": errors}


def proof_payload(lines, premise_count):
    root, stack, depth = [], [], 0
    current = root
    for line in lines[premise_count:]:
        while depth > line["depth"]:
            current = stack.pop()
            depth -= 1
        if line["depth"] > depth:
            if line["depth"] != depth + 1:
                raise ValueError("Subproof depth jumps by more than one level.")
            child = []
            current.append({"subproof": child})
            stack.append(current)
            current, depth = child, depth + 1
        elif line["rule"] == "AS" and current:
            if not stack:
                raise ValueError("Unexpected root assumption.")
            current = []
            stack[-1].append({"subproof": current})
        current.append({k: line[k] for k in ("index", "formula", "rule", "citations")})
    return root

