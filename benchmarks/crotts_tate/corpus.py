from dataclasses import dataclass, field
from pathlib import Path
import re

from ..common import file_hash


SOURCE = Path(__file__).with_name("problems.txt")
SOURCE_URL = (
    "https://raw.githubusercontent.com/joshuacrotts/masters-thesis/"
    "main/data/natural_deduction_problems.txt"
)
SOURCE_SHA256 = "b3efc3403785316ecf0a2551af0e8f0b32be35ba92336294519412f1872d8ee6"
SOURCE_ISSUES = {
    46: "The conclusion has a free x and introduces predicate M.",
    101: "The argument is invalid as written."
}


@dataclass
class BenchmarkProblem:
    index: int
    raw: str
    logic: str
    premises_raw: list[str]
    conclusion_raw: str
    premises: list[str]
    conclusion: str
    atom_map: dict = field(default_factory=dict)
    constant_map: dict = field(default_factory=dict)


def split_top_level(text, separators):
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in separators:
            part = text[start:i].strip()
            if part:
                parts.append(part)
            start = i + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def split_argument(line):
    """Split premises from the top-level conclusion marker."""
    depth = 0
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            if line.startswith("=>", i):
                return line[:i].rstrip(" ,"), line[i + 2 :].strip()
            if ch in {"∴", "⊢", "/"}:
                return line[:i].rstrip(" ,"), line[i + 1 :].strip()
        i += 1
    raise ValueError(f"No top-level conclusion marker found: {line}")


def is_first_order(text, index=None):
    """Use quantifiers/identity and the inferred FOL rows 52 and 93."""
    if re.search(r"\((?:∃|∀)?[wxyz]\)", text):
        return True
    if re.search(r"(?<![<>=])=(?![=>])", text):
        return True
    if index in {52, 93}:
        return True
    return False


def _bound_variable_names(text):
    return set(re.findall(r"\((?:∃|∀)?([wxyz])\)", text))


def _constant_remap(text):
    """Rename constants that collide with ND-Prover variable letters."""
    bound = _bound_variable_names(text)
    used_constants = set(re.findall(r"[a-r]", text))
    candidates = [c for c in "abcdefghijklmnopqr" if c not in used_constants]
    conflicts = sorted(set(re.findall(r"[s-z]", text)) - bound)
    mapping = {}
    for old in conflicts:
        if not candidates:
            raise ValueError("No unused constant names remain.")
        mapping[old] = candidates.pop(0)
    return mapping


def _propositional_atom_map(text):
    """Assign a distinct capital letter to each source atom."""
    atoms = []
    for atom in re.findall(r"[A-Z][a-z]*", text):
        if atom not in atoms:
            atoms.append(atom)
    if len(atoms) > 26:
        raise ValueError("More than 26 propositional atoms in one problem.")
    return {atom: chr(ord("A") + i) for i, atom in enumerate(atoms)}


def translate_formula(text, *, fol, remap, atom_map=None):
    s = text.strip()

    # Longest/multi-character operators first.
    replacements = [
        ("<->", "↔"), ("<>", "↔"), ("↔", "↔"),
        ("->", "→"), ("→", "→"),
        ("||", "∨"), ("∨", "∨"),
        ("&&", "∧"), ("&", "∧"), ("∧", "∧"),
        ("~", "¬"),
    ]
    for old, new in replacements:
        s = s.replace(old, new)

    # Single-character operator variants.
    s = s.replace("|", "∨").replace(">", "→")

    # Source quantifiers: (x)F means ∀xF; (∃x)F means ∃xF.
    s = re.sub(r"\(∃([wxyz])\)", r"∃\1", s)
    s = re.sub(r"\(∀([wxyz])\)", r"∀\1", s)
    s = re.sub(r"\(([wxyz])\)", r"∀\1", s)

    if fol:
        # Source constants may use letters reserved for ND-Prover variables.
        if remap:
            s = "".join(remap.get(ch, ch) if ch.islower() else ch for ch in s)

        # Convert compact predicate notation: Pxy -> P(x,y), Fa -> F(a).
        def pred_repl(m):
            name, args = m.group(1), m.group(2)
            return f"{name}({','.join(args)})"

        s = re.sub(r"([A-Z])([a-z]+)", pred_repl, s)
    elif atom_map:
        # One pass prevents newly assigned names from being renamed again.
        s = re.sub(r"[A-Z][a-z]*", lambda m: atom_map[m.group()], s)

    return re.sub(r"\s+", "", s)


def load_problems(path):
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    problems = []
    for line in raw_lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        left, right = split_argument(line)
        premises_raw = split_top_level(left, {","}) if left.strip() else []
        index = len(problems) + 1
        fol = is_first_order(line, index)
        logic = "FOL" if fol else "TFL"
        remap = _constant_remap(line) if fol else {}
        atom_map = {} if fol else _propositional_atom_map(line)
        premises = [
            translate_formula(p, fol=fol, remap=remap, atom_map=atom_map)
            for p in premises_raw
        ]
        conclusion = translate_formula(right, fol=fol, remap=remap, atom_map=atom_map)
        problems.append(BenchmarkProblem(
            index=index,
            raw=line,
            logic=logic,
            premises_raw=premises_raw,
            conclusion_raw=right,
            premises=premises,
            conclusion=conclusion,
            atom_map=atom_map,
            constant_map=remap,
        ))
    return problems


def verify_source():
    if file_hash(SOURCE) != SOURCE_SHA256:
        raise ValueError("The Crotts-Tate source file has changed.")

