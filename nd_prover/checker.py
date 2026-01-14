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
    rules, strict = {}, set()

    @classmethod
    def add(cls, name, strict=False):
        def decorator(func):
            rule = Rule(name, func)
            cls.rules[name] = rule
            if strict:
                cls.strict.add(rule)
            return staticmethod(func)
        return decorator


class TFL:
    
    @Rules.add("X")
    def X(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a.formula, Bot)):
            raise InferenceError("Invalid application of the rule X.")
        return [Metavar()]
    
    @Rules.add("¬I")
    def NotI(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_subproof() and isinstance(a.conclusion, Bot)):
            raise InferenceError("Invalid application of the rule ¬I.")
        return [Not(a.assumption)]
    
    @Rules.add("¬E")
    def NotE(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Not) 
                and b.is_line() and b.formula == a.inner):
            raise InferenceError("Invalid application of the rule ¬E.")
        return [Bot()]
    
    @Rules.add("∧I")
    def AndI(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_line() and b.is_line()):
            raise InferenceError("Invalid application of the rule ∧I.")
        return [And(a.formula, b.formula)]
    
    @Rules.add("∧E")
    def AndE(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, And)):
            raise InferenceError("Invalid application of the rule ∧E.")
        return [a.left, a.right]
    
    @Rules.add("∨I")
    def OrI(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError("Invalid application of the rule ∨I.")
        m1, m2 = Metavar(), Metavar()
        return [Or(a.formula, m1), Or(m2, a.formula)]

    @Rules.add("∨E")
    def OrE(premises, **kwargs):
        a, b, c = verify_arity(premises, 3)
        if not (a.is_line() and isinstance(a := a.formula, Or) 
                and b.is_subproof() and c.is_subproof()):
            raise InferenceError("Invalid application of the rule ∨E.")
        
        ba, bc = b.assumption, b.conclusion
        ca, cc = c.assumption, c.conclusion
        if not ((a.left, a.right) in [(ba, ca), (ca, ba)] and bc == cc and bc):
            raise InferenceError("Invalid application of the rule ∨E.")
        return [bc]
    
    @Rules.add("→I")
    def ImpI(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_subproof() and a.conclusion):
            raise InferenceError("Invalid application of the rule →I.")
        return [Imp(a.assumption, a.conclusion)]
    
    @Rules.add("→E")
    def ImpE(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Imp) 
                and b.is_line() and b.formula == a.left):
            raise InferenceError("Invalid application of the rule →E.")
        return [a.right]
    
    @Rules.add("↔I")
    def IffI(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_subproof() and b.is_subproof()):
            raise InferenceError("Invalid application of the rule ↔I.")
        
        aa, ac = a.assumption, a.conclusion
        ba, bc = b.assumption, b.conclusion
        if not (aa == bc and ba == ac):
            raise InferenceError("Invalid application of the rule ↔I.")
        return [Iff(aa, ac), Iff(ba, bc)]
    
    @Rules.add("↔E")
    def IffE(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Iff) and b.is_line()):
            raise InferenceError("Invalid application of the rule ↔E.")
        
        if b.formula == a.left:
            return [a.right]
        if b.formula == a.right:
            return [a.left]
        raise InferenceError("Invalid application of the rule ↔E.")
    
    @Rules.add("R")
    def R(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError("Invalid application of the rule R.")
        return [a.formula]
    
    @Rules.add("IP")
    def IP(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_subproof() and isinstance(a.assumption, Not) 
                and isinstance(a.conclusion, Bot)):
            raise InferenceError("Invalid application of the rule IP.")
        return [a.assumption.inner]
    
    @Rules.add("DS")
    def DS(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Or) 
                and b.is_line() and isinstance(b := b.formula, Not)):
            raise InferenceError("Invalid application of the rule DS.")
        
        if b.inner == a.left:
            return [a.right]
        if b.inner == a.right:
            return [a.left]
        raise InferenceError("Invalid application of the rule DS.")

    @Rules.add("MT")
    def MT(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Imp) 
                and b.is_line() and isinstance(b := b.formula, Not) 
                and b.inner == a.right):
            raise InferenceError("Invalid application of the rule MT.")
        return [Not(a.left)]

    @Rules.add("DNE")
    def DNE(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Not) 
                and isinstance(a.inner, Not)):
            raise InferenceError("Invalid application of the rule DNE.")
        return [a.inner.inner]

    @Rules.add("LEM")
    def LEM(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_subproof() and b.is_subproof()):
            raise InferenceError("Invalid application of the rule LEM.")
        
        aa, ac = a.assumption, a.conclusion
        ba, bc = b.assumption, b.conclusion
        if not (((isinstance(aa, Not) and aa.inner == ba) 
                 or (isinstance(ba, Not) and ba.inner == aa)) 
                and ac == bc and ac):
            raise InferenceError("Invalid application of the rule LEM.")
        return [ac]

    @Rules.add("DeM")
    def DeM(premises, **kwargs):
        c = verify_arity(premises, 1)
        if not c.is_line():
            raise InferenceError("Invalid application of the rule DeM.")

        match c.formula:
            case Not(Or(a, b)):
                return [And(Not(a), Not(b))]
            case And(Not(a), Not(b)):
                return [Not(Or(a, b))]
            case Not(And(a, b)):
                return [Or(Not(a), Not(b))]
            case Or(Not(a), Not(b)):
                return [Not(And(a, b))]
        
        raise InferenceError("Invalid application of the rule DeM.")


class FOL(TFL):

    @Rules.add("=I")
    def EqI(premises, **kwargs):
        verify_arity(premises, 0)
        m = Metavar()
        return [Eq(m, m)]
    
    @Rules.add("=E")
    def EqE(premises, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Eq) and b.is_line()):
            raise InferenceError("Invalid application of the rule =E.")
        terms = {a.left, a.right}
        def gen(): return Metavar(terms)
        return [sub_term(b.formula, t, gen) for t in terms]

    @Rules.add("∀I")
    def ForallI(premises, conclusion, scope, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(conclusion, Forall)):
            raise InferenceError("Invalid application of the rule ∀I.")
        var = conclusion.var
        def ignore(v): return v == var
        a_constants = assumption_constants(scope[0])

        schemas = [Forall(var, a.formula)]
        for c in constants(a.formula):
            if c in a_constants:
                continue
            inner = sub_term(a.formula, c, lambda: var, ignore)
            schemas.append(Forall(var, inner))
        return schemas
    
    @Rules.add("∀E")
    def ForallE(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Forall)):
            raise InferenceError("Invalid application of the rule ∀E.")
        m = Metavar()  # FIX: consider restricting to constants
        return [sub_term(a.inner, a.var, lambda: m)]

    @Rules.add("∃I")
    def ExistsI(premises, conclusion, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(conclusion, Exists)):
            raise InferenceError("Invalid application of the rule ∃I.")
        var = conclusion.var
        def ignore(v): return v == var

        schemas = [Exists(var, a.formula)]
        for c in constants(a.formula):
            def gen(): return Metavar({c, var})
            inner = sub_term(a.formula, c, gen, ignore)
            schemas.append(Exists(var, inner))
        return schemas
    
    @Rules.add("∃E")
    def ExistsE(premises, scope, **kwargs):
        a, b = verify_arity(premises, 2)
        if not (a.is_line() and isinstance(a := a.formula, Exists) 
                and b.is_subproof() and b.conclusion):
            raise InferenceError("Invalid application of the rule ∃E.")
        m = Metavar()  # FIX: consider restricting to constants
        schema = sub_term(a.inner, a.var, lambda: m)
        if b.assumption != schema:
            raise InferenceError("Invalid application of the rule ∃E.")
        
        a_constants = assumption_constants(scope[0] + scope[1])
        a_constants.update(constants(a), constants(b.conclusion))
        if m.value in a_constants:
            raise InferenceError("Invalid application of the rule ∃E.")
        return [b.conclusion]

    @Rules.add("CQ")
    def CQ(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError("Invalid application of the rule CQ.")

        match a.formula:
            case Forall(v, Not(b)):
                return [Not(Exists(v, b))]
            case Not(Exists(v, b)):
                return [Forall(v, Not(b))]
            case Exists(v, Not(b)):
                return [Not(Forall(v, b))]
            case Not(Forall(v, b)):
                return [Exists(v, Not(b))]
        
        raise InferenceError("Invalid application of the rule CQ.")


class MLK(TFL):

    @Rules.add("☐I")
    def BoxI(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_subproof() and isinstance(a.assumption, BoxMarker) 
                and a.conclusion):
            raise InferenceError("Invalid application of the rule ☐I.")
        return [Box(a.conclusion)]
    
    @Rules.add("☐E", strict=True)
    def BoxE(premises, scope, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Box)):
            raise InferenceError("Invalid application of the rule ☐E.")
        
        lines = [obj.formula for obj in scope[1] if obj.is_line()]
        if lines.count(BoxMarker()) != 1:
            raise InferenceError("Invalid application of the rule ☐E.")
        return [a.inner]

    @Rules.add("Def◇")
    def DefDia(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError("Invalid application of the rule Def◇.")

        match a.formula:
            case Not(Box(Not(b))):
                return [Dia(b)]
            case Dia(b):
                return [Not(Box(Not(b)))]
        
        raise InferenceError("Invalid application of the rule Def◇.")

    @Rules.add("MC")
    def MC(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not a.is_line():
            raise InferenceError("Invalid application of the rule MC.")

        match a.formula:
            case Not(Box(b)):
                return [Dia(Not(b))]
            case Dia(Not(b)):
                return [Not(Box(b))]
            case Not(Dia(b)):
                return [Box(Not(b))]
            case Box(Not(b)):
                return [Not(Dia(b))]
        
        raise InferenceError("Invalid application of the rule MC.")


class MLT(MLK):

    @Rules.add("RT")
    def RT(premises, scope, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Box)):
            raise InferenceError("Invalid application of the rule RT.")
        
        lines = [obj.formula for obj in scope[1] if obj.is_line()]
        if lines.count(BoxMarker()) != 0:
            raise InferenceError("Invalid application of the rule RT.")
        return [a.inner]


class MLS4(MLT):

    @Rules.add("R4", strict=True)
    def R4(premises, scope, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Box)):
            raise InferenceError("Invalid application of the rule R4.")
        
        lines = [obj.formula for obj in scope[1] if obj.is_line()]
        if lines.count(BoxMarker()) != 1:
            raise InferenceError("Invalid application of the rule R4.")
        return [a]


class MLS5(MLS4):

    @Rules.add("R5", strict=True)
    def R5(premises, scope, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Not) 
                and isinstance(a.inner, Box)):
            raise InferenceError("Invalid application of the rule R5.")
        
        lines = [obj.formula for obj in scope[1] if obj.is_line()]
        if lines.count(BoxMarker()) != 1:
            raise InferenceError("Invalid application of the rule R5.")
        return [a]


class FOMLK(FOL, MLK):

    @Rules.add("BF")
    def BF(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Forall) 
                and isinstance(a.inner, Box)):
            raise InferenceError("Invalid application of the rule BF.")
        return [Box(Forall(a.var, a.inner.inner))]

    @Rules.add("CBF")
    def CBF(premises, **kwargs):
        a = verify_arity(premises, 1)
        if not (a.is_line() and isinstance(a := a.formula, Box) 
                and isinstance(a.inner, Forall)):
            raise InferenceError("Invalid application of the rule CBF.")
        return [Forall(a.inner.var, Box(a.inner.inner))]


class FOMLT(FOMLK, MLT):
    pass


class FOMLS4(FOMLK, MLS4):
    pass


class FOMLS5(FOMLK, MLS5):
    pass


class ProofObject:

    def is_line(self):
        return isinstance(self, Line)

    def is_subproof(self):
        return isinstance(self, Proof)

    def is_strict_subproof(self):
        return self.is_subproof() and isinstance(self.assumption, BoxMarker)


@dataclass
class Line(ProofObject):
    idx: int
    formula: Formula
    justification: Justification


@dataclass
class Proof(ProofObject):
    seq: list[ProofObject]
    context: list[ProofObject]

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
                strict = self.is_strict_subproof() and rule not in Rules.strict
                premises = self.retrieve_citations(citations, obj.idx, strict)
                scope = self.partition_scope(citations, obj.idx, strict)
                schemas = rule(premises, conclusion=obj.formula, scope=scope)

                if not self.match_schemas(obj.formula, schemas):
                    raise InferenceError("Line not justified.")
            
            except InferenceError as e:
                errors_list.append(f"Line {obj.idx}: {e}")
        return errors_list

    def retrieve_citations(self, citations, idx, strict=False):
        scope = self.scope(idx, strict)
        idx_to_obj = {obj.idx: obj for obj in scope}
        premises = []

        for c in citations:
            obj = idx_to_obj.get(c)
            if obj is None:
                raise InferenceError(f"Citation {c} not in scope.")
            premises.append(obj)
        return premises

    def partition_scope(self, citations, idx, strict=False):
        citations = set(citations)
        partitions, current = [], []

        for obj in self.scope(idx, strict):
            current.append(obj)
            if obj.idx in citations:
                partitions.append(current)
                current = []
        partitions.append(current)
        return partitions

    def match_schemas(self, formula, schemas):
        # print(f"Schemas: {', '.join(str(s) for s in schemas)}")
        return any(formula == s for s in schemas)

    def scope(self, idx, strict=False):
        seq = []
        for obj in self.seq:
            if obj.idx == idx:
                break
            seq.append(obj)
        return seq if strict else self.context + seq

    def _add_line_current(self, formula, justification):
        idx = self.idx[1] + 1 if self.idx else len(self.context) + 1
        line = Line(idx, formula, justification)
        self.seq.append(line)

    def _begin_subproof_current(self, assumption):
        idx = self.idx[1] + 1 if self.idx else len(self.context) + 1
        j = Justification(Rules.AS, ())
        line = Line(idx, assumption, j)
        subproof = Proof([line], self.context + self.seq)
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

    def __init__(self, logic, premises, conclusion):
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
        self.proof = Proof([], context)

    def __str__(self):
        lines = self.proof._collect_lines()
        if not lines:
            return ""
        width = max(len(l[1]) for l in lines)

        lines_str = []
        for idx, text, j in lines:
            line_str = f"{idx:>2} {text:<{width + 5}} {j}"
            lines_str.append(line_str)
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
        if self.logic is TFL and is_tfl_formula(formula):
            return
        if self.logic is FOL and is_fol_formula(formula):
            return   
        if self.logic in (MLK, MLT, MLS4, MLS5) and is_ml_formula(formula):
            return
        if self.logic in (FOMLK, FOMLT, FOMLS4, FOMLS5):
            return
        raise InferenceError(
            f'"{formula}" is not a {self.logic.__name__} formula.'
        )

    def verify_assumption(self, assumption):
        if issubclass(self.logic, MLK) and isinstance(assumption, BoxMarker):
            return
        self.verify_formula(assumption)

    def verify_rule(self, rule):
        if not hasattr(self.logic, rule.func.__name__):
            raise InferenceError(
                f"{rule} is not a valid {self.logic.__name__} rule."
            )

    def conclusion_reached(self):
        return self.proof.conclusion == self.conclusion


def verify_arity(premises, n):
    if len(premises) != n:
        raise InferenceError("Invalid number of citations provided.")
    return premises[0] if n == 1 else premises


def assumption_constants(scope):
    a_rules = (Rules.PR, Rules.AS)
    a_constants = set()
    for obj in scope:
        if obj.is_line() and obj.justification.rule in a_rules:
            a_constants.update(constants(obj.formula))
    return a_constants
