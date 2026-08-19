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


class InferenceError(Exception):
    pass


class ProofEditError(Exception):
    pass


class SemanticsError(Exception):
    pass


@dataclass(frozen=True)
class Rule:
    name: str
    func: object = field(compare=False, hash=False)

    def __str__(self):
        return self.name
    
    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


@dataclass(frozen=True)
class Justification:
    rule: Rule
    citations: tuple

    def __str__(self):
        if not self.citations:
            return str(self.rule)

        j_list = []
        for idx in self.citations:
            if isinstance(idx, int):
                j_list.append(str(idx))
            else:
                i, j = idx
                j_list.append(f"{i}-{j}")
        return f"{self.rule}, {','.join(j_list)}"


class Rules:
    PR = Rule("PR", None)
    AS = Rule("AS", None)
    rules, derived, strict = {}, set(), set()

    @classmethod
    def add(cls, name, derived=False, strict=False):
        def decorator(func):
            cls.rules[name] = func.__name__
            if derived:
                cls.derived.add(name)
            if strict:
                cls.strict.add(name)
            return staticmethod(func)
        return decorator


class IPL:

    @Rules.add("X")
    def X(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a.formula, Bot)):
            raise InferenceError()
        return [Metavar()]
    
    @Rules.add("¬I")
    def NotI(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_subproof() and isinstance(a.conclusion, Bot)):
            raise InferenceError()
        return [Not(a.assumption)]
    
    @Rules.add("¬E")
    def NotE(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Not) 
                and b.is_line() and b.formula == a.inner):
            raise InferenceError()
        return [Bot()]
    
    @Rules.add("∧I")
    def AndI(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_line() and b.is_line()):
            raise InferenceError()
        a, b = a.formula, b.formula
        return [And(a, b), And(b, a)]
    
    @Rules.add("∧E")
    def AndE(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, And)):
            raise InferenceError()
        return [a.left, a.right]
    
    @Rules.add("∨I")
    def OrI(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError()
        m1, m2 = Metavar(), Metavar()
        return [Or(a.formula, m1), Or(m2, a.formula)]

    @Rules.add("∨E")
    def OrE(premises, **kwargs):
        a, b, c = _verify_arity(premises, 3)
        if not (a.is_line() and isinstance(a := a.formula, Or) 
                and b.is_subproof() and c.is_subproof()):
            raise InferenceError()
        
        ba, bc = b.assumption, b.conclusion
        ca, cc = c.assumption, c.conclusion
        if not ((a.left, a.right) in [(ba, ca), (ca, ba)] and bc == cc and bc):
            raise InferenceError()
        return [bc]
    
    @Rules.add("→I")
    def ImpI(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_subproof() and a.conclusion):
            raise InferenceError()
        return [Imp(a.assumption, a.conclusion)]
    
    @Rules.add("→E")
    def ImpE(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Imp) 
                and b.is_line() and b.formula == a.left):
            raise InferenceError()
        return [a.right]
    
    @Rules.add("↔I")
    def IffI(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_subproof() and b.is_subproof()):
            raise InferenceError()
        
        aa, ac = a.assumption, a.conclusion
        ba, bc = b.assumption, b.conclusion
        if not (aa == bc and ba == ac):
            raise InferenceError()
        return [Iff(aa, ac), Iff(ba, bc)]
    
    @Rules.add("↔E")
    def IffE(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Iff) and b.is_line()):
            raise InferenceError()
        
        if b.formula == a.left:
            return [a.right]
        if b.formula == a.right:
            return [a.left]
        raise InferenceError()
    
    @Rules.add("R")
    def R(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError()
        return [a.formula]

    @Rules.add("DS", derived=True)
    def DS(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Or) 
                and b.is_line() and isinstance(b := b.formula, Not)):
            raise InferenceError()
        
        if b.inner == a.left:
            return [a.right]
        if b.inner == a.right:
            return [a.left]
        raise InferenceError()

    @Rules.add("MT", derived=True)
    def MT(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Imp) 
                and b.is_line() and isinstance(b := b.formula, Not) 
                and b.inner == a.right):
            raise InferenceError()
        return [Not(a.left)]

    @Rules.add("DeM", derived=True)
    def DeM(premises, **kwargs):
        c = _verify_arity(premises, 1)
        if not c.is_line():
            raise InferenceError()

        match c.formula:
            case Not(Or(a, b)):
                return [And(Not(a), Not(b))]
            case And(Not(a), Not(b)):
                return [Not(Or(a, b))]
            case Not(And(a, b)):
                raise InferenceError(
                    "This direction of DeM is not intuitionistically valid."
                )
            case Or(Not(a), Not(b)):
                return [Not(And(a, b))]
        
        raise InferenceError()


class TFL(IPL):

    @Rules.add("IP")
    def IP(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_subproof() and isinstance(a.assumption, Not) 
                and isinstance(a.conclusion, Bot)):
            raise InferenceError()
        return [a.assumption.inner]

    @Rules.add("DNE", derived=True)
    def DNE(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Not) 
                and isinstance(a.inner, Not)):
            raise InferenceError()
        return [a.inner.inner]

    @Rules.add("LEM", derived=True)
    def LEM(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_subproof() and b.is_subproof()):
            raise InferenceError()
        
        aa, ac = a.assumption, a.conclusion
        ba, bc = b.assumption, b.conclusion
        if not (((isinstance(aa, Not) and aa.inner == ba) 
                 or (isinstance(ba, Not) and ba.inner == aa)) 
                and ac == bc and ac):
            raise InferenceError()
        return [ac]

    @Rules.add("DeM", derived=True)
    def DeM(premises, **kwargs):
        c = _verify_arity(premises, 1)
        if not c.is_line():
            raise InferenceError()

        match c.formula:
            case Not(Or(a, b)):
                return [And(Not(a), Not(b))]
            case And(Not(a), Not(b)):
                return [Not(Or(a, b))]
            case Not(And(a, b)):
                return [Or(Not(a), Not(b))]
            case Or(Not(a), Not(b)):
                return [Not(And(a, b))]
        
        raise InferenceError()


class IFOL(IPL):

    @Rules.add("=I")
    def EqI(premises, **kwargs):
        _verify_arity(premises, 0)
        m = Metavar()
        return [Eq(m, m)]
    
    @Rules.add("=E")
    def EqE(premises, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Eq) and b.is_line()):
            raise InferenceError()
        terms = {a.left, a.right}
        def gen(): return Metavar(lambda obj: obj in terms)
        return [sub_term(b.formula, t, gen) for t in terms]

    @Rules.add("∀I")
    def ForallI(premises, conclusion, scope, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(b := conclusion, Forall)):
            raise InferenceError()
        m = Metavar(is_constant)
        schema = sub_term(b.inner, b.var, lambda: m)

        # Also rejects variable capture
        if a.formula != schema:
            raise InferenceError(
                f"Line {a.idx} is an invalid substitution instance."
            )

        if (c := m.value) is not None:
            if c in constants(b):
                raise InferenceError(
                    f'Every occurence of the constant "{c}" must be replaced.'
                )
            if c in _assumption_constants(scope[0]):
                raise InferenceError(f'Constant "{c}" is not fresh.')

        return [b]

    @Rules.add("∀E")
    def ForallE(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Forall)):
            raise InferenceError()
        m = Metavar(is_ground_term)
        return [sub_term(a.inner, a.var, lambda: m)]

    @Rules.add("∃I")
    def ExistsI(premises, conclusion, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(conclusion, Exists)):
            raise InferenceError()
        var = conclusion.var
        def ignore(v): return v == var

        schemas = [Exists(var, a.formula)]
        for t in ground_terms(a.formula):
            def gen(): return Metavar(lambda obj: obj in {t, var})
            inner = sub_term(a.formula, t, gen, ignore)
            schemas.append(Exists(var, inner))
        return schemas
    
    @Rules.add("∃E")
    def ExistsE(premises, scope, **kwargs):
        a, b = _verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Exists) 
                and b.is_subproof() and b.conclusion):
            raise InferenceError()
        m = Metavar(is_constant)
        schema = sub_term(a.inner, a.var, lambda: m)

        if b.assumption != schema:
            raise InferenceError(
                f"Line {b.seq[0].idx} is an invalid substitution instance."
            )

        a_constants = _assumption_constants(scope[0] + scope[1])
        a_constants.update(constants(a), constants(b.conclusion))
        if m.value in a_constants:
            raise InferenceError(
                f'Instantiating constant "{m.value}" is not fresh.'
            )

        return [b.conclusion]

    @Rules.add("CQ", derived=True)
    def CQ(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError()

        match a.formula:
            case Forall(v, Not(b)):
                return [Not(Exists(v, b))]
            case Not(Exists(v, b)):
                return [Forall(v, Not(b))]
            case Exists(v, Not(b)):
                return [Not(Forall(v, b))]
            case Not(Forall(v, b)):
                raise InferenceError(
                    "This direction of CQ is not intuitionistically valid."
                )
        
        raise InferenceError()


class FOL(IFOL, TFL):

    @Rules.add("CQ", derived=True)
    def CQ(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError()

        match a.formula:
            case Forall(v, Not(b)):
                return [Not(Exists(v, b))]
            case Not(Exists(v, b)):
                return [Forall(v, Not(b))]
            case Exists(v, Not(b)):
                return [Not(Forall(v, b))]
            case Not(Forall(v, b)):
                return [Exists(v, Not(b))]
        
        raise InferenceError()


class IK(IPL):
    pass


class K(IK, TFL):

    @Rules.add("☐I")
    def BoxI(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_subproof() and isinstance(a.assumption, BoxMarker) 
                and a.conclusion):
            raise InferenceError()
        return [Box(a.conclusion)]
    
    @Rules.add("☐E", strict=True)
    def BoxE(premises, scope, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a.formula, Box)):
            raise InferenceError()

        lines = [obj.formula for obj in scope[1] if obj.is_line()]
        box_count = lines.count(BoxMarker())

        if box_count < 1:
            raise InferenceError(
                f"☐E must be used inside a strict subproof "
                f"opened after line {a.idx}."
            )
        if box_count > 1:
            raise InferenceError(
                f"☐E cannot be used inside nested strict subproofs "
                f"opened after line {a.idx}."
            )

        return [a.formula.inner]

    @Rules.add("Def◇")
    def DefDia(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError()

        match a.formula:
            case Not(Box(Not(b))):
                return [Dia(b)]
            case Dia(b):
                return [Not(Box(Not(b)))]
        
        raise InferenceError()

    @Rules.add("MC", derived=True)
    def MC(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError()

        match a.formula:
            case Not(Box(b)):
                return [Dia(Not(b))]
            case Dia(Not(b)):
                return [Not(Box(b))]
            case Not(Dia(b)):
                return [Box(Not(b))]
            case Box(Not(b)):
                return [Not(Dia(b))]
        
        raise InferenceError()


class IT(IK):
    pass


class T(IT, K):

    @Rules.add("RT")
    def RT(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Box)):
            raise InferenceError()
        return [a.inner]


class IS4(IT):
    pass


class S4(IS4, T):

    @Rules.add("R4", strict=True)
    def R4(premises, scope, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a.formula, Box)):
            raise InferenceError()

        lines = [obj.formula for obj in scope[1] if obj.is_line()]
        box_count = lines.count(BoxMarker())

        if box_count < 1:
            raise InferenceError(
                f"R4 must be used inside a strict subproof "
                f"opened after line {a.idx}."
            )
        if box_count > 1:
            raise InferenceError(
                f"R4 cannot be used inside nested strict subproofs "
                f"opened after line {a.idx}."
            )

        return [a.formula]


class IS5(IS4):
    pass


class S5(IS5, S4):

    @Rules.add("R5", strict=True)
    def R5(premises, scope, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a.formula, Not) 
                and isinstance(a.formula.inner, Box)):
            raise InferenceError()

        lines = [obj.formula for obj in scope[1] if obj.is_line()]
        box_count = lines.count(BoxMarker())

        if box_count < 1:
            raise InferenceError(
                f"R5 must be used inside a strict subproof "
                f"opened after line {a.idx}."
            )
        if box_count > 1:
            raise InferenceError(
                f"R5 cannot be used inside nested strict subproofs "
                f"opened after line {a.idx}."
            )

        return [a.formula]


class IQK(IFOL, IK):
    pass


class QK(IQK, FOL, K):

    @Rules.add("BF")
    def BF(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Forall) 
                and isinstance(a.inner, Box)):
            raise InferenceError()
        return [Box(Forall(a.var, a.inner.inner))]

    @Rules.add("ND")
    def ND(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Not) 
                and isinstance(a.inner, Eq)):
            raise InferenceError()
        return [Box(a)]

    @Rules.add("CBF", derived=True)
    def CBF(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Box) 
                and isinstance(a.inner, Forall)):
            raise InferenceError()
        return [Forall(a.inner.var, Box(a.inner.inner))]

    @Rules.add("NI", derived=True)
    def NI(premises, **kwargs):
        a = _verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Eq)):
            raise InferenceError()
        return [Box(a)]


class IQT(IQK, IT):
    pass


class QT(IQT, QK, T):
    pass


class IQS4(IQT, IS4):
    pass


class QS4(IQS4, QT, S4):
    pass


class IQS5(IQS4, IS5):
    pass


class QS5(IQS5, QS4, S5):
    pass


class ProofObject:

    def is_line(self):
        return isinstance(self, Line)

    def is_subproof(self):
        return isinstance(self, Proof)


@dataclass
class Line(ProofObject):
    idx: int
    formula: Formula
    justification: Justification


@dataclass
class Proof(ProofObject):
    seq: list[ProofObject]
    context: list[ProofObject]
    strict_context: list[ProofObject]

    @property
    def idx(self):
        if not self.seq:
            return None
        start, end = self.seq[0], self.seq[-1]
        start_idx = start.idx if start.is_line() else start.idx[0]
        end_idx = end.idx if end.is_line() else end.idx[1]
        return (start_idx, end_idx)

    @property
    def assumption(self):
        if not (self.seq and (start := self.seq[0]).is_line()):
            return None
        if start.justification.rule is not Rules.AS:
            return None
        return start.formula

    @property
    def conclusion(self):
        if not (self.seq and (end := self.seq[-1]).is_line()):
            return None
        if end.justification.rule is Rules.AS:
            return None
        return end.formula

    def add_line(self, formula, justification):
        if self.seq and (end := self.seq[-1]).is_subproof():
            return end.add_line(formula, justification)
        self._add_line_current(formula, justification)

    def begin_subproof(self, assumption):
        if self.seq and (end := self.seq[-1]).is_subproof():
            return end.begin_subproof(assumption)
        self._begin_subproof_current(assumption)

    def end_subproof(self, formula, justification):
        if not (self.seq and (end := self.seq[-1]).is_subproof()):
            raise ProofEditError("No active subproof to close.")
        if end.seq[-1].is_subproof():
            return end.end_subproof(formula, justification)
        self._add_line_current(formula, justification)

    def end_and_begin_subproof(self, assumption):
        if not (self.seq and (end := self.seq[-1]).is_subproof()):
            raise ProofEditError("No active subproof to close.")
        if end.seq[-1].is_subproof():
            return end.end_and_begin_subproof(assumption)
        self._begin_subproof_current(assumption)

    def delete_line(self):
        if not self.seq:
            raise ProofEditError("No lines to delete.")
        if (end := self.seq[-1]).is_subproof() and len(end.seq) != 1:
            return end.delete_line()
        self.seq.pop()

    def errors(self):
        errors_list = []
        for obj in self.seq:
            if obj.is_subproof():
                errors_list.extend(obj.errors())
                continue
            if (rule := obj.justification.rule) is Rules.AS:
                continue
            try:
                citations = obj.justification.citations
                full_scope = self.strict_context is None or rule.name in Rules.strict
                premises = self.retrieve_cited_at(citations, obj.idx, full_scope)
                scope = self.partition_scope_at(citations, obj.idx)
                schemas = rule(premises, conclusion=obj.formula, scope=scope)

                if not self.match_schemas(obj.formula, schemas):
                    raise InferenceError()

            except InferenceError as e:
                if not (error_msg := str(e)):
                    error_msg = f"Invalid application of the rule {rule.name}."
                errors_list.append(f"Line {obj.idx}: {error_msg}")

        return errors_list

    def retrieve_cited_at(self, citations, idx, full_scope):
        scope = self.scope_at(idx, full_scope)
        idx_to_obj = {obj.idx: obj for obj in scope}
        premises = []

        for c in citations:
            obj = idx_to_obj.get(c)
            if obj is None:
                raise InferenceError(f"Citation {c} is not in scope.")
            premises.append(obj)
        return premises

    def partition_scope_at(self, citations, idx):
        citations = set(citations)
        partitions, current = [], []

        for obj in self.scope_at(idx):
            current.append(obj)
            if obj.idx in citations:
                partitions.append(current)
                current = []

        partitions.append(current)
        return partitions

    def match_schemas(self, formula, schemas):
        # print(f"Schemas: {', '.join(str(s) for s in schemas)}")
        return any(formula == s for s in schemas)

    def scope_at(self, idx, full=True):
        seq = []
        for obj in self.seq:
            if obj.idx == idx:
                break
            seq.append(obj)

        if full:
            return self.context + seq
        return self.strict_context + seq

    def _add_line_current(self, formula, justification):
        idx = self.idx[1] + 1 if self.idx else len(self.context) + 1
        line = Line(idx, formula, justification)
        self.seq.append(line)

    def _begin_subproof_current(self, assumption):
        idx = self.idx[1] + 1 if self.idx else len(self.context) + 1
        j = Justification(Rules.AS, ())
        line = Line(idx, assumption, j)

        strict_context = None
        if isinstance(assumption, BoxMarker):
            strict_context = []
        elif self.strict_context is not None:
            strict_context = self.strict_context + self.seq

        subproof = Proof([line], self.context + self.seq, strict_context)
        self.seq.append(subproof)

    def _collect_lines(self, depth=0):
        indent = "│ " * depth
        seq = self.seq if self.assumption else self.context + self.seq
        bar_idx = 0 if self.assumption else len(self.context) - 1

        lines = []
        for idx, obj in enumerate(seq):
            if obj.is_line():
                formula = str(obj.formula)
                j = obj.justification
                lines.append((obj.idx, f"{indent}│ {formula}", j))
            else:
                lines.extend(obj._collect_lines(depth + 1))

            if idx == bar_idx:
                bar = f"{indent}├{'─' * (len(formula) + 2)}"
                lines.append(("", bar, ""))
            elif idx != len(seq) - 1:
                lines.append(("", f"{indent}│", ""))

        return lines


class Problem:

    def __init__(
        self,
        logic,
        premises,
        conclusion,
        domain_semantics=None,
        equality_semantics=None,
        derived_rules=True
    ):
        self.logic = logic
        self.verify_formula(conclusion)

        context, idx = [], 1
        for p in premises:
            self.verify_formula(p)
            j = Justification(Rules.PR, ())
            context.append(Line(idx, p, j))
            idx += 1

        self.premises = premises
        self.conclusion = conclusion
        self.domain_semantics, self.equality_semantics = resolve_semantics(
            logic, domain_semantics, equality_semantics
        )
        self.derived_rules = derived_rules
        self.proof = Proof([], context, None)

    def __str__(self):
        return self.to_plain_text()

    def to_plain_text(self):
        lines = self.proof._collect_lines()
        if not lines:
            return ""
        width = max(len(l[1]) for l in lines)

        lines_str = ["```"]
        for idx, text, j in lines:
            line_str = f"{idx:>2} {text:<{width + 5}} {j}"
            lines_str.append(line_str)

        lines_str.append("```")
        return "\n".join(lines_str)

    def add_line(self, formula, justification):
        self.verify_formula(formula)
        self.verify_rule(justification.rule)
        self.proof.add_line(formula, justification)

    def begin_subproof(self, assumption):
        self.verify_assumption(assumption)
        self.proof.begin_subproof(assumption)

    def end_subproof(self, formula, justification):
        self.verify_formula(formula)
        self.verify_rule(justification.rule)
        self.proof.end_subproof(formula, justification)

    def end_and_begin_subproof(self, assumption):
        self.verify_assumption(assumption)
        self.proof.end_and_begin_subproof(assumption)

    def delete_line(self):
        self.proof.delete_line()

    def errors(self):
        return self.proof.errors()

    def verify_formula(self, formula):
        logic = self.logic
        if logic in (TFL, IPL) and not is_tfl_formula(formula):
            raise InferenceError(f'"{formula}" is not a TFL formula.')
        if logic in (FOL, IFOL) and not is_fol_formula(formula):
            raise InferenceError(f'"{formula}" is not an FOL formula.')
        if modal(logic) and not first_order(logic) and not is_ml_formula(formula):
            raise InferenceError(f'"{formula}" is not an ML formula.')
        if first_order(logic) and free_vars(formula):
            raise InferenceError(f'"{formula}" is not a closed formula.')

    def verify_assumption(self, assumption):
        if not (modal(self.logic) and isinstance(assumption, BoxMarker)):
            self.verify_formula(assumption)

    def verify_rule(self, rule):
        logic = self.logic
        func_name = Rules.rules[rule.name]
        if not hasattr(logic, func_name):
            raise InferenceError(f"{rule} is not a valid {logic.__name__} rule.")
        if rule.name in Rules.derived and not self.derived_rules:
            raise InferenceError(f"Derived rule {rule} is unavailable.")
        if rule.name == "BF" and self.domain_semantics == "expanding":
            raise InferenceError("BF is not valid in expanding-domain semantics.")

    def conclusion_reached(self):
        return self.proof.conclusion == self.conclusion


def intuitionistic(logic):
    return not issubclass(logic, TFL)


def first_order(logic):
    return issubclass(logic, IFOL)


def modal(logic):
    return issubclass(logic, IK)


def reflexive(logic):
    return issubclass(logic, IT)


def transitive(logic):
    return issubclass(logic, IS4)


def s5(logic):
    return issubclass(logic, IS5)


def resolve_semantics(logic, domain=None, equality=None):
    is_intuitionistic = intuitionistic(logic)
    is_first_order = first_order(logic)
    is_modal = modal(logic)
    is_s5 = s5(logic)

    if not is_first_order:
        if not (domain is None and equality is None):
            raise SemanticsError()
        return None, None

    worlded = is_intuitionistic or is_modal
    if not worlded:
        if domain not in {None, "constant"}:
            raise SemanticsError()
        domain = "constant"
    else:
        if domain is None:
            domain = "expanding"
        if domain not in {"constant", "expanding"}:
            raise SemanticsError()

        # QS5
        if is_s5 and not is_intuitionistic:
            domain = "constant"

    if equality is None:
        equality = "equivalence" if is_intuitionistic else "identity"
    if equality not in {"identity", "equivalence"}:
        raise SemanticsError()

    # Classical logic
    if not is_intuitionistic and equality != "identity":
        raise SemanticsError()

    return domain, equality


def _verify_arity(premises, n):
    if len(premises) != n:
        raise InferenceError("Invalid number of line(s)/subproof(s) cited.")
    return premises[0] if n == 1 else premises


def _assumption_constants(scope):
    eff_assumptions = {"PR", "AS", "☐E", "R4", "R5"}
    a_constants = set()

    for obj in scope[::-1]:
        if not obj.is_line():
            continue
        if isinstance(obj.formula, BoxMarker):
            return a_constants

        rule_name = obj.justification.rule.name
        if rule_name in eff_assumptions:
            a_constants.update(constants(obj.formula))

    return a_constants
