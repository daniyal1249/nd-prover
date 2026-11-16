import re

from nd_prover import *

from .corpus import library_root, problem_files, split_problem
from .cases import BenchmarkCase, SkippedProblem
from .tptp import (
    UnsupportedTPTPFeature, parse_file, resolve_file, universal_close
)


VERSION = "1.1"
_STATUS_LINE_RE = re.compile(
    r"^%\s*(K|D|T|S4|S5)\s+"
    r"(Theorem|Non-Theorem|Unsolved)\s+"
    r"(Theorem|Non-Theorem|Unsolved)\s+"
    r"(Theorem|Non-Theorem|Unsolved)(?:\s+.*)?$"
)
_RATING_LINE_RE = re.compile(
    r"^%\s*(K|D|T|S4|S5)\s+"
    r"([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)(?:\s+.*)?$"
)
_CLASSICAL_DOMAINS = {"NLP", "SET"}
_SOURCE_WARNINGS = {
    "APM004+1": "Known parenthesization issue in the original QMLTP source.",
    "APM007+1": "qmltpeq occurs without the intended equality axiomatization.",
    "SYM035+1": "Known parenthesization issue in the original QMLTP source.",
    "SYM052+1": "Native inequality occurs although QMLTP uses qmltpeq.",
    "SYM054+1": "qmltpeq occurs without the intended equality axiomatization.",
    "SYM055+1": "Native equality occurs without the intended axiomatization.",
    "SYM056+1": "Native equality occurs without the intended axiomatization.",
    "SYM057+1": "Native equality occurs without the intended axiomatization.",
    "SYM058+1": "qmltpeq occurs without the intended equality axiomatization.",
    "SYM064+1": "Native equality occurs without the intended axiomatization.",
    "SYM068+1": "Native equality and qmltpeq occur without intended axioms.",
    "SYM069+1": "qmltpeq occurs without the intended equality axiomatization.",
    "SYM070+1": "qmltpeq occurs without the intended equality axiomatization.",
    "SYM071+1": "qmltpeq occurs without the intended equality axiomatization.",
    "SYM072+1": "qmltpeq occurs without the intended equality axiomatization.",
    "SYM082+1": "Known parenthesization issue in the original QMLTP source.",
    "SYM085+1": "Native equality occurs without the intended axiomatization.",
    "SYM113+1": "Known parenthesization issue in the original QMLTP source.",
    "SYM114+1": "Known parenthesization issue in the original QMLTP source.",
    "SYM122+1": "Known parenthesization issue in the original QMLTP source.",
    "SYM163+1": "Known parenthesization issue in the original QMLTP source."
}
_NON_GOLD = {"SYM052+1", "SYM056+1"}
_LOGICS = {
    "K": (K, QK),
    "T": (T, QT),
    "S4": (S4, QS4),
    "S5": (S5, QS5)
}


def load_cases(root, include_classical=False):
    root = library_root(root)
    files = [(path.stem, path) for path in problem_files(root)]
    cases, skipped = [], []
    cache = {}

    for problem_id, path in files:
        domain = problem_id[:3]
        if domain == "MML":
            skipped.append(SkippedProblem(
                "QMLTP", problem_id, path, "MULTIMODAL"
            ))
            continue
        if domain in _CLASSICAL_DOMAINS and not include_classical:
            skipped.append(SkippedProblem(
                "QMLTP", problem_id, path, "CLASSICAL_ONLY"
            ))
            continue

        try:
            parsed = parse_file(path)
            cache[path.resolve()] = parsed
            formulas = resolve_file(path, root, cache)
            premises, conclusion = split_problem(formulas)
            premises = [universal_close(f) for f in premises]
            conclusion = universal_close(conclusion)
            all_formulas = premises + [conclusion]
            propositional = all(is_ml_formula(f) for f in all_formulas)
            statuses, ratings = _metadata_from_header(parsed.text)

            for source_logic, source_domain, logic, domain_semantics in (
                _configurations(propositional)
            ):
                problem = Problem(
                    logic, premises, conclusion, domain_semantics
                )
                status = _value_for(
                    statuses, source_logic, source_domain
                )
                rating = _value_for(
                    ratings, source_logic, source_domain
                )
                cases.append(BenchmarkCase(
                    "QMLTP", VERSION, problem_id, path, problem,
                    source_status=status,
                    source_rating=rating,
                    source_logic=source_logic,
                    source_domain=source_domain,
                    metadata={
                        "source_formula_count": len(parsed.formulas),
                        "resolved_formula_count": len(formulas),
                        "propositional": propositional,
                        "domain": domain,
                        "source_warning": _SOURCE_WARNINGS.get(problem_id),
                        "exclude_from_gold": problem_id in _NON_GOLD
                    }
                ))
        except UnsupportedTPTPFeature as exc:
            skipped.append(SkippedProblem(
                "QMLTP", problem_id, path, exc.feature, str(exc)
            ))
        except Exception as exc:
            skipped.append(SkippedProblem(
                "QMLTP", problem_id, path, "LOAD_ERROR", str(exc)
            ))

    return cases, skipped


def _configurations(propositional):
    if propositional:
        for source_logic, (logic, _) in _LOGICS.items():
            yield source_logic, "constant", logic, None
        return

    for source_logic in ("K", "T", "S4"):
        _, logic = _LOGICS[source_logic]
        yield source_logic, "cumulative", logic, "expanding"
        yield source_logic, "constant", logic, "constant"

    _, logic = _LOGICS["S5"]
    yield "S5", "constant", logic, "constant"


def _metadata_from_header(text):
    statuses, ratings = {}, {}
    section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if lower.startswith("% status"):
            section = "status"
            continue
        if lower.startswith("% rating"):
            section = "rating"
            continue
        if not line.startswith("%"):
            continue

        if section == "status":
            m = _STATUS_LINE_RE.fullmatch(line)
            if m:
                statuses[m.group(1)] = {
                    "varying": m.group(2),
                    "cumulative": m.group(3),
                    "constant": m.group(4)
                }
        elif section == "rating":
            m = _RATING_LINE_RE.fullmatch(line)
            if m:
                ratings[m.group(1)] = {
                    "varying": float(m.group(2)),
                    "cumulative": float(m.group(3)),
                    "constant": float(m.group(4))
                }

    return statuses, ratings


def _value_for(table, logic, domain):
    return table.get(logic, {}).get(domain)

