from pathlib import Path
import re

from nd_prover import *


PROBLEM_NAME = re.compile(r"^[A-Z]{3}\d{3}\+\d+(?:\.\d+)?\.p$")
PREMISE_ROLES = {
    "axiom", "hypothesis", "definition", "assumption", "lemma", "theorem",
    "negated_conjecture", "plain"
}


def library_root(path):
    path = Path(path).resolve()
    if not path.is_dir():
        raise ValueError(f'Library directory does not exist: "{path}".')
    if path.name.lower() == "problems":
        return path.parent
    if (path / "Problems").is_dir():
        return path
    directories = sorted(p for p in path.rglob("Problems") if p.is_dir())
    if len(directories) == 1:
        return directories[0].parent
    return path


def problem_files(root):
    directory = root / "Problems" if (root / "Problems").is_dir() else root
    files = sorted(
        p for p in directory.rglob("*.p") if PROBLEM_NAME.fullmatch(p.name)
    )
    if not files:
        raise ValueError(f'No benchmark problems found in "{directory}".')
    return files


def split_problem(formulas):
    conjectures, premises = [], []
    for item in formulas:
        if item.role == "conjecture":
            conjectures.append(item.formula)
        elif item.role in PREMISE_ROLES:
            premises.append(item.formula)
        else:
            raise ValueError(f'Unsupported formula role "{item.role}".')
    if len(conjectures) > 1:
        raise ValueError("Multiple conjectures in one problem.")
    return premises, conjectures[0] if conjectures else Bot()

