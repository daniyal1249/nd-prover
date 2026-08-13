# Copyright 2026 Daniyal Akif

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from .syntax import *


_rule_labels = {
    "¬I": r"$\neg$I",
    "¬E": r"$\neg$E",
    "∧I": r"$\wedge$I",
    "∧E": r"$\wedge$E",
    "∨I": r"$\vee$I",
    "∨E": r"$\vee$E",
    "→I": r"$\to$I",
    "→E": r"$\to$E",
    "↔I": r"$\leftrightarrow$I",
    "↔E": r"$\leftrightarrow$E",
    "∀I": r"$\forall$I",
    "∀E": r"$\forall$E",
    "∃I": r"$\exists$I",
    "∃E": r"$\exists$E",
    "☐I": r"$\Box$I",
    "☐E": r"$\Box$E",
    "Def◇": r"Def$\Diamond$",
    "RT": r"R$\mathbf{T}$",
    "R4": r"R$\mathbf{4}$",
    "R5": r"R$\mathbf{5}$",
}


def _term_to_latex(term):
    match term:
        case Var(name):
            return name
        case Func(name, args):
            if not args:
                return name
            args = ",".join(_term_to_latex(t) for t in args)
            return f"{name}({args})"


def _quantifier_sep(inner):
    if isinstance(inner, (Not, Box, Dia, Forall, Exists)):
        return " "
    return r"\, "


def _prefix_formula(command, formula):
    inner = _formula_to_latex(formula)
    if isinstance(formula, Eq):
        inner = f"({inner})"

    sep = " " if inner and inner[0].isalpha() else ""
    return f"{command}{sep}{inner}"


def _formula_to_latex(formula):
    match formula:
        case Pred(name, args):
            if not args:
                return name
            args = ",".join(_term_to_latex(t) for t in args)
            return f"{name}({args})"
        case Bot():
            return r"\bot"
        case BoxMarker():
            return r"\Box"
        case Not(a):
            return _prefix_formula(r"\neg", a)
        case Box(a):
            return _prefix_formula(r"\Box", a)
        case Dia(a):
            return _prefix_formula(r"\Diamond", a)
        case And(a, b):
            a = _formula_to_latex(a)
            b = _formula_to_latex(b)
            return rf"({a} \wedge {b})"
        case Or(a, b):
            a = _formula_to_latex(a)
            b = _formula_to_latex(b)
            return rf"({a} \vee {b})"
        case Imp(a, b):
            a = _formula_to_latex(a)
            b = _formula_to_latex(b)
            return rf"({a} \to {b})"
        case Iff(a, b):
            a = _formula_to_latex(a)
            b = _formula_to_latex(b)
            return rf"({a} \leftrightarrow {b})"
        case Eq(a, b):
            a = _formula_to_latex(a)
            b = _formula_to_latex(b)
            return f"{a} = {b}"
        case Forall(var, a):
            inner = _formula_to_latex(a)
            sep = _quantifier_sep(a)
            return rf"\forall {var.name}{sep}{inner}"
        case Exists(var, a):
            inner = _formula_to_latex(a)
            sep = _quantifier_sep(a)
            return rf"\exists {var.name}{sep}{inner}"


def formula_to_latex(formula):
    latex = _formula_to_latex(formula)
    if isinstance(formula, (And, Or, Imp, Iff)):
        return latex[1:-1]
    return latex


def _citations_to_latex(citations):
    refs = []
    for c in citations:
        ref = str(c) if isinstance(c, int) else f"{c[0]}-{c[1]}"
        refs.append(ref)
    return ",".join(refs)


def justification_to_latex(justification):
    rule_name = justification.rule.name
    rule_label = _rule_labels.get(rule_name, rule_name)
    refs = _citations_to_latex(justification.citations)
    return rf"\by{{{rule_label}}}{{{refs}}}"


def _line_to_latex(line, depth):
    indent = "  " * depth
    j = line.justification
    command = r"\hypo" if j.rule.name in {"PR", "AS"} else r"\have"

    formula = formula_to_latex(line.formula)
    j = justification_to_latex(j)
    return f"{indent}{command}{{{line.idx}}}{{{formula}}} {j}"


def _render_seq(seq, lines, depth):
    for idx, obj in enumerate(seq):
        if obj.is_line():
            lines.append(_line_to_latex(obj, depth))
            continue

        indent = "  " * depth
        lines.append(rf"{indent}\open")
        _render_seq(obj.seq, lines, depth + 1)
        if idx != len(seq) - 1:
            lines.append(rf"{indent}\close")


def problem_to_latex(problem):
    lines = [
        r"% Requires: \usepackage{fitch}",
        r"% Modal proofs also require: \usepackage{amssymb}",
        r"",
        r"$\begin{nd}"
    ]

    for line in problem.proof.context:
        lines.append(_line_to_latex(line, 1))

    _render_seq(problem.proof.seq, lines, 1)
    lines.append(r"\end{nd}$")
    return "\n".join(lines)
