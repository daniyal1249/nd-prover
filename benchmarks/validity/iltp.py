from pathlib import Path
import re

from nd_prover import *

from .corpus import library_root, problem_files, split_problem
from .cases import BenchmarkCase, SkippedProblem
from .tptp import (
    UnsupportedTPTPFeature, parse_file, resolve_file, universal_close
)


VERSION = "1.1.2"
_STATS_RE = re.compile(
    r"^([A-Z]{3}\d{3}\+\d+(?:\.\d+)?)\s+"
    r"(Theorem|Non-Theorem|Unsolved|Open)\s+([0-9.]+)\s*$"
)
_HEADER_STATUS_RE = re.compile(
    r"^\s*%\s*Status\s*\(intuit\.\)\s*:\s*"
    r"(Theorem|Non-Theorem|Unsolved|Open)", re.MULTILINE
)
_HEADER_RATING_RE = re.compile(
    r"^\s*%\s*Rating\s*\(intuit\.\)\s*:\s*([0-9.]+)", re.MULTILINE
)


def load_cases(roots, stats_path=None):
    roots = [library_root(root) for root in roots]
    stats = _load_stats_paths(stats_path) if stats_path else _find_stats(roots)
    files = _discover_files(roots, set(stats) if stats else None)

    cases, skipped = [], []
    cache = {}
    for problem_id, path, root in files:
        try:
            parsed = parse_file(path)
            cache[path.resolve()] = parsed
            formulas = resolve_file(path, root, cache)
            premises, conclusion = split_problem(formulas)
            premises = [universal_close(f) for f in premises]
            conclusion = universal_close(conclusion)

            all_formulas = premises + [conclusion]
            propositional = all(is_tfl_formula(f) for f in all_formulas)
            logic = IPL if propositional else IFOL
            problem = Problem(logic, premises, conclusion)

            status, rating = stats.get(
                problem_id, _metadata_from_header(parsed.text)
            )
            case = BenchmarkCase(
                "ILTP", VERSION, problem_id, path, problem,
                source_status=status,
                source_rating=rating,
                metadata={
                    "source_formula_count": len(parsed.formulas),
                    "resolved_formula_count": len(formulas),
                    "propositional": propositional,
                    "domain": problem_id[:3]
                }
            )
            cases.append(case)
        except UnsupportedTPTPFeature as exc:
            skipped.append(SkippedProblem(
                "ILTP", problem_id, path, exc.feature, str(exc)
            ))
        except Exception as exc:
            skipped.append(SkippedProblem(
                "ILTP", problem_id, path, "LOAD_ERROR", str(exc)
            ))

    return cases, skipped


def _discover_files(roots, allowed_ids=None):
    selected = {}
    for root in roots:
        for path in problem_files(root):
            problem_id = path.stem
            # Official statistics distinguish problems from support files.
            if allowed_ids is not None and problem_id not in allowed_ids:
                continue
            old = selected.get(problem_id)
            current = (path, root)
            if old is None or _prefer(path, old[0]):
                selected[problem_id] = current

    return [
        (problem_id, path, root)
        for problem_id, (path, root) in sorted(selected.items())
    ]


def _prefer(new, old):
    def propositional(path):
        return any(
            "propositional" in part.lower() or part.lower().endswith("-prop")
            for part in Path(path).parts
        )

    return propositional(new) and not propositional(old)


def _load_stats_paths(paths):
    if isinstance(paths, (str, Path)):
        paths = [paths]

    stats = {}
    for path in paths:
        stats.update(_load_stats(path))
    return stats


def _load_stats(path):
    path = Path(path)
    stats = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _STATS_RE.fullmatch(line.strip())
        if m:
            stats[m.group(1)] = (m.group(2), float(m.group(3)))
    return stats


def _find_stats(roots):
    stats = {}
    patterns = (
        "*fof-statistics.txt",
        "*prop-statistics.txt"
    )
    search_roots = set(roots)
    search_roots.update(root.parent for root in roots)

    for root in sorted(search_roots):
        for pattern in patterns:
            for path in sorted(root.rglob(pattern)):
                stats.update(_load_stats(path))
    return stats


def _metadata_from_header(text):
    status_match = _HEADER_STATUS_RE.search(text)
    rating_match = _HEADER_RATING_RE.search(text)
    status = status_match.group(1) if status_match else None
    rating = float(rating_match.group(1)) if rating_match else None
    return status, rating

