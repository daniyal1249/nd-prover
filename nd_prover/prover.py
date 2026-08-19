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

from .sat import *


class ProverError(Exception):
    pass


@dataclass
class ProofSearchResult:
    status: str
    problem: Problem = None


class _ProofObject:
    count = 0

    def __init__(self):
        _ProofObject.count += 1
        self.id = _ProofObject.count

    def is_line(self):
        return isinstance(self, _Line)


@dataclass
class _Line(_ProofObject):
    formula: Formula
    rule: str
    citations: tuple

    def __post_init__(self):
        self.is_assumption = self.rule in {"PR", "AS"}
        self.is_eff_assumption = self.rule in {"PR", "AS", "☐E", "R4", "R5"}
        super().__init__()

    def copy(self):
        return _Line(self.formula, self.rule, self.citations)


@dataclass
class _Proof(_ProofObject):
    _seq: list[_ProofObject]
    goal: Formula

    def __post_init__(self):
        self.seq = self.seq[:]  # FIX: check if correct
        super().__init__()

    @property
    def seq(self):
        return self._seq

    @seq.setter
    def seq(self, new_seq):
        self._seq = new_seq
        self.init()

    def init(self):
        self.formulas = {
            obj.formula 
            for obj in self.seq 
            if obj.is_line()
        }
        self.formulas.discard(BoxMarker())
        self.eff_assumptions = {
            obj.formula 
            for obj in self.seq 
            if obj.is_line() and obj.is_eff_assumption
        }
        self.eff_assumptions.discard(BoxMarker())
        self.used_constants = constants(self.goal).union(
            *(constants(f) for f in self.eff_assumptions)
        )
        self.line_count = sum(
            1 if obj.is_line() else obj.line_count 
            for obj in self.seq
        )
        self.ip_count = sum(
            (1 if obj.rule == "IP" else 0) 
            if obj.is_line() else obj.ip_count 
            for obj in self.seq
        )

    def copy(self):
        return _Proof(self.seq, self.goal)

    def add(self, *objs):
        for obj in objs:
            if obj.is_line():
                f = obj.formula
                self.formulas.add(f)
                if obj.is_eff_assumption:
                    self.eff_assumptions.add(f)
                    self.used_constants.update(constants(f))

                self.line_count += 1
                if obj.rule == "IP":
                    self.ip_count += 1
            else:
                self.line_count += obj.line_count
                self.ip_count += obj.ip_count
            self.seq.append(obj)

    def id_to_obj(self):
        id_to_obj = {}
        for obj in self.seq:
            if obj.is_line():
                id_to_obj[obj.id] = obj
            else:
                id_to_obj.update(obj.id_to_obj())
        return id_to_obj

    def id_to_citers(self):
        id_to_citers = {}
        for obj in self.seq:
            if obj.is_line():
                for c in obj.citations:
                    citers = id_to_citers.setdefault(c, set())
                    citers.add(obj.id)
                id_to_citers[obj.id] = set()
            else:
                for k, v in obj.id_to_citers().items():
                    citers = id_to_citers.setdefault(k, set())
                    citers.update(v)
                id_to_citers[obj.id] = set()
        return id_to_citers

    def pop_reiteration(self):
        end = self.seq[-1]
        if end.is_line() and end.rule == "R":
            self.seq.pop()
            self.line_count -= 1
            return end.citations[0]
        return end.id

    def commit_best_branch(self, branches):
        if not branches:
            return False
        def key(p): return (p.line_count, p.ip_count)
        # FIX: consider copying seq
        self.seq = min(branches, key=key).seq
        return True


class Eliminator:

    @staticmethod
    def elim(prover):
        while True:
            if Eliminator.R(prover):
                return True
            if Eliminator.X(prover):
                return True
            if Eliminator.NotE(prover):
                continue
            if Eliminator.AndE(prover):
                continue
            if Eliminator.ImpE(prover):
                continue
            if Eliminator.IffE(prover):
                continue

            if prover.derived_rules:
                if Eliminator.DS(prover):
                    continue
                if Eliminator.MT(prover):
                    continue
                if not prover.intuitionistic and Eliminator.DNE(prover):
                    continue
                if Eliminator.DeM(prover):
                    continue

            if prover.first_order:
                if prover.derived_rules and Eliminator.CQ(prover):
                    continue
                if Eliminator.ForallE(prover):
                    continue

            if prover.modal:
                if prover.derived_rules and Eliminator.MC(prover):
                    continue
                if Eliminator.DefDia(prover):
                    continue
                if prover.reflexive and Eliminator.RT(prover):
                    continue

            if prover.first_order and prover.modal:
                ds = prover.domain_semantics
                if ds == "constant" and Eliminator.BF(prover):
                    continue
                if prover.derived_rules and Eliminator.CBF(prover):
                    continue

            return False

    @staticmethod
    def strict_elim(prover, subproof):
        if prover.modal:
            Eliminator.BoxE(prover, subproof)
        if prover.transitive:
            Eliminator.R4(prover, subproof)
        if prover.s5:
            Eliminator.R5(prover, subproof)

    @staticmethod
    def R(prover):
        proof = prover.proof
        if proof.seq and (end := proof.seq[-1]).is_line():
            if end.formula == proof.goal and not end.is_assumption:
                return True

        for obj in proof.seq:
            if obj.is_line() and obj.formula == proof.goal:
                line = _Line(obj.formula, "R", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def X(prover):
        proof = prover.proof
        for obj in proof.seq:
            if obj.is_line() and isinstance(obj.formula, Bot):
                line = _Line(proof.goal, "X", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def NotE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Not)):
                continue

            for obj2 in proof.seq:
                if obj2.is_line() and obj2.formula == f.inner:
                    line = _Line(Bot(), "¬E", (obj.id, obj2.id))
                    proof.add(line)
                    return True
        return False

    @staticmethod
    def AndE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, And)):
                continue

            for conjunct in (f.left, f.right):
                if conjunct not in proof.formulas:
                    line = _Line(conjunct, "∧E", (obj.id,))
                    proof.add(line)
                    return True
        return False

    @staticmethod
    def ImpE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Imp)):
                continue
            if f.right in proof.formulas:
                continue

            for obj2 in proof.seq:
                if obj2.is_line() and obj2.formula == f.left:
                    line = _Line(f.right, "→E", (obj.id, obj2.id))
                    proof.add(line)
                    return True
        return False

    @staticmethod
    def IffE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Iff)):
                continue

            have_left = f.left in proof.formulas
            have_right = f.right in proof.formulas

            if have_left and not have_right:
                for obj2 in proof.seq:
                    if obj2.is_line() and obj2.formula == f.left:
                        line = _Line(f.right, "↔E", (obj.id, obj2.id))
                        proof.add(line)
                        return True

            if have_right and not have_left:
                for obj2 in proof.seq:
                    if obj2.is_line() and obj2.formula == f.right:
                        line = _Line(f.left, "↔E", (obj.id, obj2.id))
                        proof.add(line)
                        return True
        return False

    @staticmethod
    def DS(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Or)):
                continue
            if f.left in proof.formulas or f.right in proof.formulas:
                continue

            for obj2 in proof.seq:
                if obj2.is_line() and isinstance(f2 := obj2.formula, Not):
                    line = None
                    if f2.inner == f.left:
                        line = _Line(f.right, "DS", (obj.id, obj2.id))
                    elif f2.inner == f.right:
                        line = _Line(f.left, "DS", (obj.id, obj2.id))
                    if line is not None:
                        proof.add(line)
                        return True
        return False

    @staticmethod
    def MT(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Imp)):
                continue
            if Not(f.left) in proof.formulas:
                continue

            for obj2 in proof.seq:
                if obj2.is_line() and isinstance(f2 := obj2.formula, Not):
                    if f2.inner == f.right:
                        line = _Line(Not(f.left), "MT", (obj.id, obj2.id))
                        proof.add(line)
                        return True
        return False

    @staticmethod
    def DNE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Not) 
                    and isinstance(f.inner, Not)):
                continue

            if f.inner.inner not in proof.formulas:
                line = _Line(f.inner.inner, "DNE", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def DeM(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not obj.is_line():
                continue

            match obj.formula:
                case Not(Or(a, b)):
                    transformed = And(Not(a), Not(b))
                case And(Not(a), Not(b)):
                    transformed = Not(Or(a, b))
                case Not(And(a, b)) if not prover.intuitionistic:
                    transformed = Or(Not(a), Not(b))
                case Or(Not(a), Not(b)):
                    transformed = Not(And(a, b))
                case _:
                    continue

            if transformed not in proof.formulas:
                line = _Line(transformed, "DeM", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def CQ(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not obj.is_line():
                continue

            match obj.formula:
                case Forall(v, Not(b)):
                    transformed = Not(Exists(v, b))
                case Not(Exists(v, b)):
                    transformed = Forall(v, Not(b))
                case Exists(v, Not(b)):
                    transformed = Not(Forall(v, b))
                case Not(Forall(v, b)) if not prover.intuitionistic:
                    transformed = Exists(v, Not(b))
                case _:
                    continue

            if transformed not in proof.formulas:
                line = _Line(transformed, "CQ", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def ForallE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Forall)):
                continue

            for term in _ground_terms(proof):
                inner = sub_term(f.inner, f.var, lambda: term)
                if inner not in proof.formulas:
                    line = _Line(inner, "∀E", (obj.id,))
                    proof.add(line)
                    return True
        return False

    @staticmethod
    def MC(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not obj.is_line():
                continue

            match obj.formula:
                case Not(Box(b)):
                    transformed = Dia(Not(b))
                    if transformed != proof.goal:
                        continue
                case Dia(Not(b)):
                    transformed = Not(Box(b))
                case Not(Dia(b)):
                    transformed = Box(Not(b))
                case Box(Not(b)):
                    transformed = Not(Dia(b))
                case _:
                    continue

            if transformed not in proof.formulas:
                line = _Line(transformed, "MC", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def DefDia(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Dia)):
                continue

            expanded = Not(Box(Not(f.inner)))
            if expanded not in proof.formulas:
                line = _Line(expanded, "Def◇", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def RT(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Box)):
                continue

            if f.inner not in proof.formulas:
                line = _Line(f.inner, "RT", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def BF(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Forall) 
                    and isinstance(f.inner, Box)):
                continue

            box_forall = Box(Forall(f.var, f.inner.inner))
            if box_forall not in proof.formulas:
                line = _Line(box_forall, "BF", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def CBF(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Box) 
                    and isinstance(f.inner, Forall)):
                continue

            forall_box = Forall(f.inner.var, Box(f.inner.inner))
            if forall_box not in proof.formulas:
                line = _Line(forall_box, "CBF", (obj.id,))
                proof.add(line)
                return True
        return False

    @staticmethod
    def BoxE(prover, subproof):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Box)):
                continue

            if f.inner not in subproof.formulas:
                line = _Line(f.inner, "☐E", (obj.id,))
                subproof.add(line)

    @staticmethod
    def R4(prover, subproof):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Box)):
                continue

            if f not in subproof.formulas:
                line = _Line(f, "R4", (obj.id,))
                subproof.add(line)

    @staticmethod
    def R5(prover, subproof):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Not) 
                    and isinstance(f.inner, Box)):
                continue

            if f not in subproof.formulas:
                line = _Line(f, "R5", (obj.id,))
                subproof.add(line)

    @staticmethod
    def OrE(prover):
        proof = prover.proof
        goal = proof.goal
        branches = []

        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Or)):
                continue
            if f.left in proof.formulas or f.right in proof.formulas:
                continue

            objs = []
            subproof1 = _find_subproof(proof.seq, f.left, goal)

            if subproof1 is None:
                assumption1 = _Line(f.left, "AS", ())
                subproof1 = _Proof(proof.seq + [assumption1], goal)
                p1 = prover.new(subproof1)
                if not p1.prove():
                    continue
                subproof1.seq = subproof1.seq[len(proof.seq):]
                objs.append(subproof1)

            seq = proof.seq + objs
            subproof2 = _find_subproof(seq, f.right, goal)

            if subproof2 is None:
                assumption2 = _Line(f.right, "AS", ())
                subproof2 = _Proof(seq + [assumption2], goal)
                p2 = prover.new(subproof2, copy_seen=True)
                if not p2.prove():
                    continue
                subproof2.seq = subproof2.seq[len(seq):]
                objs.append(subproof2)

            line = _Line(goal, "∨E", (obj.id, subproof1.id, subproof2.id))
            objs.append(line)
            branch = _Proof(proof.seq + objs, goal)
            branches.append(branch)
            if not prover.exhaustive:
                break

        return proof.commit_best_branch(branches)

    @staticmethod
    def ExistsE(prover):
        proof = prover.proof
        goal = proof.goal
        branches = []

        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Exists)):
                continue
            m = Metavar(is_ground_term)
            schema = sub_term(f.inner, f.var, lambda: m)

            matched = False
            for formula in proof.formulas:
                if formula == schema:
                    matched = True
                    break
                m.value = None

            if matched:
                continue

            c = _fresh_constant(proof)
            inner = sub_term(f.inner, f.var, lambda: c)
            subproof = _find_subproof(proof.seq, inner, goal)

            objs = []
            if subproof is None:
                assumption = _Line(inner, "AS", ())
                subproof = _Proof(proof.seq + [assumption], goal)
                p = prover.new(subproof)
                if not p.prove():
                    continue
                subproof.seq = subproof.seq[len(proof.seq):]
                objs.append(subproof)

            line = _Line(goal, "∃E", (obj.id, subproof.id))
            objs.append(line)
            branch = _Proof(proof.seq + objs, goal)
            branches.append(branch)
            # if not prover.exhaustive:  # FIX: break?
            break

        return proof.commit_best_branch(branches)

    @staticmethod
    def NotE_force(prover):
        proof = prover.proof
        ds, es = prover.domain_semantics, prover.equality_semantics
        result = check_validity(
            prover.logic, proof.eff_assumptions, Bot(), ds, es
        )
        if result.status == "invalid":
            return False

        branches = []
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Not)):
                continue
            branch = _Proof(proof.seq, f.inner)
            p = prover.new(branch)
            if not p.prove():
                continue

            branch.pop_reiteration()
            if branch.seq != proof.seq:
                branches.append(branch)
                if not prover.exhaustive:
                    break

        return proof.commit_best_branch(branches)

    @staticmethod
    def ImpE_force(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Imp)):
                continue
            if f.right in proof.formulas:
                continue

            ds, es = prover.domain_semantics, prover.equality_semantics
            result = check_validity(
                prover.logic, proof.eff_assumptions, f.left, ds, es
            )

            if result.status != "invalid":
                branch = _Proof(proof.seq, f.left)
                p = prover.new(branch)
                if p.prove():
                    branch.pop_reiteration()
                    if branch.seq != proof.seq:
                        proof.seq = branch.seq
                        return True
        return False

    @staticmethod
    def IffE_force(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(f := obj.formula, Iff)):
                continue
            if f.left in proof.formulas or f.right in proof.formulas:
                continue

            ds, es = prover.domain_semantics, prover.equality_semantics
            result = check_validity(
                prover.logic, proof.eff_assumptions, f.left, ds, es
            )
            if result.status == "invalid":
                continue

            branches = []
            for formula in (f.left, f.right):
                branch = _Proof(proof.seq, formula)
                p = prover.new(branch, copy_seen=True)
                if not p.prove():
                    continue

                branch.pop_reiteration()
                if branch.seq != proof.seq:
                    branches.append(branch)
                    # FIX: consider always breaking
                    if not prover.exhaustive:
                        break

            if proof.commit_best_branch(branches):
                return True
        return False


class Introducer:

    @staticmethod
    def intro(prover):
        match prover.proof.goal:
            case Not():
                return Introducer.NotI(prover)
            case And():
                return Introducer.AndI(prover)
            case Or():
                return Introducer.OrI(prover)
            case Imp():
                return Introducer.ImpI(prover)
            case Iff():
                return Introducer.IffI(prover)
            case Forall():
                return Introducer.ForallI(prover)
            case Exists():
                return Introducer.ExistsI(prover)
            case Box():
                return Introducer.BoxI(prover)
            case Dia():
                return Introducer.DefDia(prover)
        return False

    @staticmethod
    def NotI(prover):
        proof = prover.proof
        inner = proof.goal.inner
        subproof = _find_subproof(proof.seq, inner, Bot())
        found = subproof is not None

        if not found:
            if inner in proof.formulas:
                return False

            # ds, es = prover.domain_semantics, prover.equality_semantics
            # result = check_validity(
            #     prover.logic, proof.eff_assumptions, inner, ds, es
            # )
            # if result.status == "valid":
            #     return False

            assumption = _Line(inner, "AS", ())
            subproof = _Proof(proof.seq + [assumption], Bot())
            p = prover.new(subproof, ip=False)
            if not p.prove():
                return False
            subproof.seq = subproof.seq[len(proof.seq):]

        line = _Line(proof.goal, "¬I", (subproof.id,))
        objs = (line,) if found else (subproof, line)
        proof.add(*objs)
        return True

    @staticmethod
    def AndI(prover):
        proof = prover.proof
        left, right = proof.goal.left, proof.goal.right
        branches = []

        for conjunct1, conjunct2 in [(left, right), (right, left)]:
            branch1 = _Proof(proof.seq, conjunct1)
            p1 = prover.new(branch1, copy_seen=True)
            if not p1.prove():
                continue
            conjunct1_id = branch1.pop_reiteration()

            branch2 = _Proof(branch1.seq, conjunct2)
            p2 = prover.new(branch2)
            if not p2.prove():
                continue
            conjunct2_id = branch2.pop_reiteration()

            line = _Line(proof.goal, "∧I", (conjunct1_id, conjunct2_id))
            branch2.add(line)
            branches.append(branch2)
            if not prover.exhaustive:
                break

        return proof.commit_best_branch(branches)

    @staticmethod
    def OrI(prover):
        proof = prover.proof
        left, right = proof.goal.left, proof.goal.right
        branches = []

        # For efficiency
        for obj in proof.seq:
            if obj.is_line() and obj.formula in (left, right):
                line = _Line(proof.goal, "∨I", (obj.id,))
                proof.add(line)
                return True

        for disjunct in (left, right):
            ds, es = prover.domain_semantics, prover.equality_semantics
            result = check_validity(
                prover.logic, proof.eff_assumptions, disjunct, ds, es
            )

            if result.status != "invalid":
                branch = _Proof(proof.seq, disjunct)
                p = prover.new(branch)
                if not p.prove():
                    continue

                disjunct_id = branch.pop_reiteration()
                line = _Line(proof.goal, "∨I", (disjunct_id,))
                branch.add(line)
                branches.append(branch)
                if not prover.exhaustive:
                    break

        return proof.commit_best_branch(branches)

    @staticmethod
    def ImpI(prover):
        proof = prover.proof
        left, right = proof.goal.left, proof.goal.right
        subproof = _find_subproof(proof.seq, left, right)
        found = subproof is not None

        if not found:
            assumption = _Line(left, "AS", ())
            subproof = _Proof(proof.seq + [assumption], right)
            p = prover.new(subproof, copy_seen=True)
            if not p.prove():
                return False
            subproof.seq = subproof.seq[len(proof.seq):]

        line = _Line(proof.goal, "→I", (subproof.id,))
        objs = (line,) if found else (subproof, line)
        proof.add(*objs)
        return True

    @staticmethod
    def IffI(prover):
        proof = prover.proof
        left, right = proof.goal.left, proof.goal.right

        objs = []
        subproof1 = _find_subproof(proof.seq, left, right)

        if subproof1 is None:
            assumption1 = _Line(left, "AS", ())
            subproof1 = _Proof(proof.seq + [assumption1], right)
            p1 = prover.new(subproof1)
            if not p1.prove():
                return False
            subproof1.seq = subproof1.seq[len(proof.seq):]
            objs.append(subproof1)

        seq = proof.seq + objs
        subproof2 = _find_subproof(seq, right, left)

        if subproof2 is None:
            assumption2 = _Line(right, "AS", ())
            subproof2 = _Proof(seq + [assumption2], left)
            p2 = prover.new(subproof2)
            if not p2.prove():
                return False
            subproof2.seq = subproof2.seq[len(seq):]
            objs.append(subproof2)

        line = _Line(proof.goal, "↔I", (subproof1.id, subproof2.id))
        objs.append(line)
        proof.add(*objs)
        return True

    @staticmethod
    def ForallI(prover):
        proof = prover.proof
        c = _fresh_constant(proof)
        inner = sub_term(proof.goal.inner, proof.goal.var, lambda: c)
        branch = _Proof(proof.seq, inner)
        p = prover.new(branch)
        if not p.prove():
            return False

        inner_id = branch.pop_reiteration()
        line = _Line(proof.goal, "∀I", (inner_id,))
        branch.add(line)
        proof.seq = branch.seq
        return True

    @staticmethod
    def ExistsI(prover):
        proof = prover.proof
        branches = []

        exists, m = proof.goal, Metavar(is_ground_term)
        schema = sub_term(exists.inner, exists.var, lambda: m)

        for obj in proof.seq:
            if obj.is_line() and obj.formula == schema:
                line = _Line(exists, "∃I", (obj.id,))
                proof.add(line)
                return True
            m.value = None

        for term in _ground_terms(proof):
            inner = sub_term(exists.inner, exists.var, lambda: term)
            branch = _Proof(proof.seq, inner)
            p = prover.new(branch)
            if not p.prove():
                continue

            inner_id = branch.pop_reiteration()
            line = _Line(exists, "∃I", (inner_id,))
            branch.add(line)
            branches.append(branch)
            # if not prover.exhaustive:  # FIX: break?
            break

        return proof.commit_best_branch(branches)

    @staticmethod
    def BoxI(prover):
        proof = prover.proof
        subproof = _find_subproof(proof.seq, BoxMarker(), proof.goal.inner)
        found = subproof is not None

        if not found:
            assumption = _Line(BoxMarker(), "AS", ())
            subproof = _Proof([assumption], proof.goal.inner)
            subproof.used_constants.update(proof.used_constants)
            Eliminator.strict_elim(prover, subproof)
            p = prover.new(subproof, ip=True)  # FIX: copy?
            if not p.prove():
                return False

        line = _Line(proof.goal, "☐I", (subproof.id,))
        objs = (line,) if found else (subproof, line)
        proof.add(*objs)
        return True

    @staticmethod
    def DefDia(prover):
        proof = prover.proof
        expanded = Not(Box(Not(proof.goal.inner)))
        branch = _Proof(proof.seq, expanded)
        p = prover.new(branch, ip=False, copy_seen=True)
        if not p.prove():
            return False

        expanded_id = branch.pop_reiteration()
        line = _Line(proof.goal, "Def◇", (expanded_id,))
        branch.add(line)
        proof.seq = branch.seq
        return True

    @staticmethod
    def IP(prover):
        proof = prover.proof
        not_goal = Not(proof.goal)
        subproof = _find_subproof(proof.seq, not_goal, Bot())
        found = subproof is not None

        if not found:
            if not_goal in proof.formulas:
                return False

            # ds, es = prover.domain_semantics, prover.equality_semantics
            # result = check_validity(
            #     prover.logic, proof.eff_assumptions, not_goal, ds, es
            # )
            # if result.status == "valid":
            #     return False

            assumption = _Line(not_goal, "AS", ())
            subproof = _Proof(proof.seq + [assumption], Bot())
            p = prover.new(subproof, ip=False)
            if not p.prove():
                return False
            subproof.seq = subproof.seq[len(proof.seq):]

        line = _Line(proof.goal, "IP", (subproof.id,))
        objs = (line,) if found else (subproof, line)
        proof.add(*objs)
        return True


class Prover:

    def __init__(
        self,
        logic,
        proof,
        domain_semantics=None,
        equality_semantics=None,
        derived_rules=True,
        ip=None,
        exhaustive=True,
        seen=None,
        deadline=None
    ):
        self.logic = logic
        self.intuitionistic = intuitionistic(logic)
        self.first_order = first_order(logic)
        self.modal = modal(logic)
        self.reflexive = reflexive(logic)
        self.transitive = transitive(logic)
        self.s5 = s5(logic)

        self.proof = proof
        self.domain_semantics, self.equality_semantics = resolve_semantics(
            logic, domain_semantics, equality_semantics
        )

        self.derived_rules = derived_rules
        self.ip = not self.intuitionistic if ip is None else ip
        self.exhaustive = exhaustive
        self.seen = {} if seen is None else seen
        self.deadline = deadline

    def prove(self):
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise TimeoutError()

        if Eliminator.elim(self):
            return True
        if not self.enter_state():
            return False
        if Introducer.intro(self):
            return True

        strategies = (
            lambda p: Eliminator.NotE_force(p) and p.prove(),
            lambda p: Eliminator.ImpE_force(p) and p.prove(),
            lambda p: Eliminator.IffE_force(p) and p.prove(),
            lambda p: p.first_order and Eliminator.ExistsE(p),
            lambda p: Eliminator.OrE(p),
            lambda p: p.ip and Introducer.IP(p),
        )

        branches = []
        for strategy in strategies:
            p = self.new()
            if strategy(p):
                branches.append(p.proof)
                if not p.exhaustive:
                    break

        return self.proof.commit_best_branch(branches)

    def new(self, proof=None, ip=None, copy_seen=False):
        proof = self.proof.copy() if proof is None else proof
        ip = self.ip if ip is None else ip
        seen = self.seen.copy() if copy_seen else self.seen

        return Prover(
            self.logic,
            proof,
            self.domain_semantics,
            self.equality_semantics,
            self.derived_rules,
            ip,
            self.exhaustive,
            seen,
            self.deadline
        )

    def enter_state(self):
        proof = self.proof
        state = (frozenset(proof.formulas), proof.goal)
        cost = (proof.line_count, proof.ip_count)

        old_cost = self.seen.get(state)
        if old_cost is None or cost < old_cost:
            self.seen[state] = cost
            return True
        return False


class Processor:

    @staticmethod
    def process(proof, target, logic, premise_count):
        Processor.remove_uncited(proof, proof.id_to_citers())
        id_to_obj, id_to_citers = proof.id_to_obj(), proof.id_to_citers()
        Processor.replace_reiterations(proof, id_to_obj, id_to_citers, {})

        premises = proof.seq[:premise_count]
        id_to_idx = {line.id: idx for idx, line in enumerate(premises, 1)}
        Processor.translate(proof.seq[premise_count:], target, logic, id_to_idx)

    @staticmethod
    def remove_uncited(proof, id_to_citers):
        while True:
            seq, n = [], len(proof.seq)
            for idx, obj in enumerate(proof.seq):

                if not obj.is_line():
                    if id_to_citers[obj.id]:
                        Processor.remove_uncited(obj, id_to_citers)
                        seq.append(obj)
                    continue
                if obj.is_assumption or idx == n - 1:
                    seq.append(obj)
                    continue
                if id_to_citers[obj.id]:
                    seq.append(obj)

            proof.seq = seq
            if len(seq) == n:
                break
            id_to_citers = proof.id_to_citers()

    @staticmethod
    def replace_reiterations(proof, id_to_obj, id_to_citers, replace):
        seq, n = [], len(proof.seq)
        for idx, obj in enumerate(proof.seq):

            if not obj.is_line():
                Processor.replace_reiterations(
                    obj, id_to_obj, id_to_citers, replace
                )
                seq.append(obj)
                continue

            line = replace.get(obj.id)
            if line is not None:
                replacement = line.copy()
                replacement.id = obj.id
                seq.append(replacement)
                continue
            if obj.is_assumption or idx == n - 1:
                seq.append(obj)
                continue

            citers = id_to_citers[obj.id]
            if not all(id_to_obj[c].rule == "R" for c in citers):
                seq.append(obj)
                continue
            for c in citers:
                replace[c] = obj

        proof.seq = seq

    @staticmethod
    def translate(seq, target, logic, id_to_idx):
        active_subproof = False

        for obj in seq:
            if obj.is_line():
                rule = getattr(Rules, obj.rule, None)
                if rule is None:
                    func_name = Rules.rules[obj.rule]
                    rule = Rule(obj.rule, getattr(logic, func_name))

                citations = tuple(id_to_idx[c] for c in obj.citations)
                j = Justification(rule, citations)

                if active_subproof:
                    target.end_subproof(obj.formula, j)
                    active_subproof = False
                else:
                    target.add_line(obj.formula, j)

                id_to_idx[obj.id] = target.idx[1]
                continue

            assumption = obj.seq[0]

            if active_subproof:
                target.end_and_begin_subproof(assumption.formula)
            else:
                target.begin_subproof(assumption.formula)

            start_idx = target.idx[1]
            id_to_idx[assumption.id] = start_idx
            Processor.translate(obj.seq[1:], target, logic, id_to_idx)
            id_to_idx[obj.id] = (start_idx, target.idx[1])
            active_subproof = True


def _find_subproof(seq, assumption, conclusion):
    for obj in seq:
        if obj.is_line() or len(obj.seq) == 1:
            continue
        start, end = obj.seq[0], obj.seq[-1]
        if not end.is_line():
            continue
        if start.formula == assumption and end.formula == conclusion:
            return obj
    return None


def _ground_terms(proof):
    goal_terms = ground_terms(proof.goal)
    assumption_terms = set()

    for obj in proof.seq:
        if obj.is_line() and obj.is_eff_assumption:
            assumption_terms.update(ground_terms(obj.formula))

    seed = goal_terms.union(assumption_terms)
    if not seed:
        seed = {Func("a", ())}

    frontier = set()
    for obj in proof.seq:
        if obj.is_line() and isinstance(f := obj.formula, Forall):
            for term in seed:
                inner = sub_term(f.inner, f.var, lambda: term)
                frontier.update(ground_terms(inner))

    result, seen = [], set()
    for group in (goal_terms, assumption_terms, seed, frontier):
        for term in sorted(group, key=lambda t: (len(s := str(t)), s)):
            if term not in seen:
                result.append(term)
                seen.add(term)

    return result


def _fresh_constant(proof):
    for obj in proof.seq:
        if not (obj.is_line() and not obj.is_eff_assumption):
            continue
        for c in sorted(constants(obj.formula), key=str):
            if c not in proof.used_constants:
                return c

    for name in Func.names:
        c = Func(name, ())
        if c not in proof.used_constants:
            return c
    raise ProverError()


def prove(
    logic,
    premises,
    conclusion,
    domain_semantics=None,
    equality_semantics=None,
    derived_rules=True,
    exhaustive=True,
    timeout=None
):
    seq = [_Line(p, "PR", ()) for p in premises]
    proof = _Proof(seq, conclusion)

    deadline = None
    if timeout is not None:
        deadline = time.monotonic() + timeout / 1000

    p = Prover(
        logic,
        proof,
        domain_semantics,
        equality_semantics,
        derived_rules,
        exhaustive=exhaustive,
        deadline=deadline
    )

    try:
        proved = p.prove()
    except TimeoutError:
        return ProofSearchResult("timeout")
    except Exception:
        return ProofSearchResult("failure")

    if not proved:
        return ProofSearchResult("failure")

    problem = Problem(
        logic,
        premises,
        conclusion,
        domain_semantics,
        equality_semantics,
        derived_rules
    )

    Processor.process(proof, problem.proof, logic, len(premises))
    if problem.errors() or not problem.conclusion_reached():
        return ProofSearchResult("failure")
    return ProofSearchResult("success", problem)
