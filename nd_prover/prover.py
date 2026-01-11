import time

from .checker import *
from .tfl_sat import *


class ProverError(Exception):
    pass


class _ProofObject:
    count = 0

    def __init__(self):
        _ProofObject.count += 1
        self.id = _ProofObject.count

    def is_line(self):
        return isinstance(self, _Line)

    def is_subproof(self):
        return isinstance(self, _Proof)


@dataclass
class _Line(_ProofObject):
    formula: Formula
    rule: str
    citations: tuple

    def __post_init__(self):
        self.is_assumption = self.rule in ("PR", "AS")
        super().__init__()

    def copy(self):
        return _Line(self.formula, self.rule, self.citations)


@dataclass
class _Proof(_ProofObject):
    _seq: list[_ProofObject]
    goal: Formula

    def __post_init__(self):
        self.seq = self.seq[:]
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
        self.assumptions = {
            obj.formula 
            for obj in self.seq 
            if obj.is_line() and obj.is_assumption
        }
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
                self.formulas.add(obj.formula)
                if obj.is_assumption:
                    self.assumptions.add(obj.formula)
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
        def key(p): return (p.ip_count, p.line_count)
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
            return False

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
            if not (obj.is_line() and isinstance(obj.formula, Not)):
                continue

            for obj2 in proof.seq:
                if obj2.is_line() and obj2.formula == obj.formula.inner:
                    line = _Line(Bot(), "¬E", (obj.id, obj2.id))
                    proof.add(line)
                    return True
        return False

    @staticmethod
    def AndE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(obj.formula, And)):
                continue

            for conjunct in (obj.formula.left, obj.formula.right):
                if conjunct not in proof.formulas:
                    line = _Line(conjunct, "∧E", (obj.id,))
                    proof.add(line)
                    return True
        return False

    @staticmethod
    def ImpE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(obj.formula, Imp)):
                continue
            if obj.formula.right in proof.formulas:
                continue

            for obj2 in proof.seq:
                if obj2.is_line() and obj2.formula == obj.formula.left:
                    line = _Line(obj.formula.right, "→E", (obj.id, obj2.id))
                    proof.add(line)
                    return True
        return False

    @staticmethod
    def IffE(prover):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(obj.formula, Iff)):
                continue

            have_left = obj.formula.left in proof.formulas
            have_right = obj.formula.right in proof.formulas

            if have_left and not have_right:
                for obj2 in proof.seq:
                    if obj2.is_line() and obj2.formula == obj.formula.left:
                        line = _Line(obj.formula.right, "↔E", (obj.id, obj2.id))
                        proof.add(line)
                        return True

            if have_right and not have_left:
                for obj2 in proof.seq:
                    if obj2.is_line() and obj2.formula == obj.formula.right:
                        line = _Line(obj.formula.left, "↔E", (obj.id, obj2.id))
                        proof.add(line)
                        return True
        return False

    @staticmethod
    def OrE(prover, complete):
        proof = prover.proof
        goal = proof.goal
        branches = []

        for obj in proof.seq:
            if not (obj.is_line() and isinstance(obj.formula, Or)):
                continue
            disjunct1, disjunct2 = obj.formula.left, obj.formula.right
            objs = []

            subproof1 = find_subproof(proof.seq, disjunct1, goal)
            found1 = subproof1 is not None

            if not found1:
                assumption1 = _Line(disjunct1, "AS", ())
                subproof1 = _Proof(proof.seq + [assumption1], goal)
                p1 = Prover(subproof1, prover.seen, prover.deadline)
                if not p1.prove(complete):
                    continue
                subproof1.seq = subproof1.seq[len(proof.seq):]
                objs.append(subproof1)

            seq = proof.seq + objs
            subproof2 = find_subproof(seq, disjunct2, goal)
            found2 = subproof2 is not None

            if not found2:
                assumption2 = _Line(disjunct2, "AS", ())
                subproof2 = _Proof(seq + [assumption2], goal)
                p2 = Prover(subproof2, prover.seen.copy(), prover.deadline)
                if not p2.prove(complete):
                    continue
                subproof2.seq = subproof2.seq[len(seq):]
                objs.append(subproof2)

            line = _Line(goal, "∨E", (obj.id, subproof1.id, subproof2.id))
            objs.append(line)
            branch = _Proof(proof.seq + objs, goal)
            branches.append(branch)
            if not complete:
                break

        return proof.commit_best_branch(branches)

    @staticmethod
    def NotE_force(prover, complete):
        proof = prover.proof
        branches = []
        if not is_valid(proof.assumptions, Bot()):
            return False

        for obj in proof.seq:
            if not (obj.is_line() and isinstance(obj.formula, Not)):
                continue
            branch = _Proof(proof.seq, obj.formula.inner)
            p = Prover(branch, prover.seen, prover.deadline)
            if not p.prove(complete):
                continue

            branch.pop_reiteration()
            if branch.seq != proof.seq:
                branches.append(branch)
                if not complete:
                    break

        return proof.commit_best_branch(branches)

    @staticmethod
    def ImpE_force(prover, complete):
        proof = prover.proof
        for obj in proof.seq:
            if not (obj.is_line() and isinstance(obj.formula, Imp)):
                continue
            if obj.formula.right in proof.formulas:
                continue

            if is_valid(proof.assumptions, obj.formula.left):
                branch = _Proof(proof.seq, obj.formula.left)
                p = Prover(branch, prover.seen, prover.deadline)
                if p.prove(complete):
                    branch.pop_reiteration()
                    if branch.seq != proof.seq:
                        proof.seq = branch.seq
                        return True
        return False

    @staticmethod
    def IffE_force(prover, complete):
        proof = prover.proof
        formulas = proof.formulas

        for obj in proof.seq:
            if not (obj.is_line() and isinstance(obj.formula, Iff)):
                continue
            if obj.formula.left in formulas or obj.formula.right in formulas:
                continue
            if not is_valid(proof.assumptions, obj.formula.left):
                continue

            branches = []
            for formula in (obj.formula.left, obj.formula.right):
                branch = _Proof(proof.seq, formula)
                p = Prover(branch, prover.seen.copy(), prover.deadline)
                if not p.prove(complete):
                    continue

                branch.pop_reiteration()
                if branch.seq != proof.seq:
                    branches.append(branch)
                    # FIX: consider always breaking
                    if not complete:
                        break

            if proof.commit_best_branch(branches):
                return True
        return False


class Introducer:

    @staticmethod
    def intro(prover, complete):
        match prover.proof.goal:
            case Not():
                return Introducer.NotI(prover, complete)
            case And():
                return Introducer.AndI(prover, complete)
            case Or():
                return Introducer.OrI(prover, complete)
            case Imp():
                return Introducer.ImpI(prover, complete)
            case Iff():
                return Introducer.IffI(prover, complete)
        return False

    @staticmethod
    def NotI(prover, complete):
        proof = prover.proof
        subproof = find_subproof(proof.seq, proof.goal.inner, Bot())
        found = subproof is not None

        if not found:
            assumption = _Line(proof.goal.inner, "AS", ())
            subproof = _Proof(proof.seq + [assumption], Bot())
            p = Prover(subproof, prover.seen, prover.deadline)
            if not p.prove(complete):
                return False
            subproof.seq = subproof.seq[len(proof.seq):]

        line = _Line(proof.goal, "¬I", (subproof.id,))
        objs = (line,) if found else (subproof, line)
        proof.add(*objs)
        return True

    @staticmethod
    def AndI(prover, complete):
        proof = prover.proof
        left, right = proof.goal.left, proof.goal.right
        branches = []

        for conjunct1, conjunct2 in [(left, right), (right, left)]:
            branch1 = _Proof(proof.seq, conjunct1)
            p1 = Prover(branch1, prover.seen, prover.deadline)
            if not p1.prove(complete):
                continue
            conjunct1_id = branch1.pop_reiteration()

            branch2 = _Proof(branch1.seq, conjunct2)
            p2 = Prover(branch2, prover.seen, prover.deadline)
            if not p2.prove(complete):
                continue
            conjunct2_id = branch2.pop_reiteration()

            line = _Line(proof.goal, "∧I", (conjunct1_id, conjunct2_id))
            branch2.add(line)
            branches.append(branch2)
            if not complete:
                break

        return proof.commit_best_branch(branches)

    @staticmethod
    def OrI(prover, complete):
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
            if is_valid(proof.assumptions, disjunct):
                branch = _Proof(proof.seq, disjunct)
                p = Prover(branch, prover.seen, prover.deadline)
                if not p.prove(complete):
                    continue

                disjunct_id = branch.pop_reiteration()
                line = _Line(proof.goal, "∨I", (disjunct_id,))
                branch.add(line)
                branches.append(branch)
                if not complete:
                    break

        return proof.commit_best_branch(branches)

    @staticmethod
    def ImpI(prover, complete):
        proof = prover.proof
        left, right = proof.goal.left, proof.goal.right
        subproof = find_subproof(proof.seq, left, right)
        found = subproof is not None

        if not found:
            assumption = _Line(left, "AS", ())
            subproof = _Proof(proof.seq + [assumption], right)
            p = Prover(subproof, prover.seen, prover.deadline)
            if not p.prove(complete):
                return False
            subproof.seq = subproof.seq[len(proof.seq):]

        line = _Line(proof.goal, "→I", (subproof.id,))
        objs = (line,) if found else (subproof, line)
        proof.add(*objs)
        return True

    @staticmethod
    def IffI(prover, complete):
        proof = prover.proof
        left, right = proof.goal.left, proof.goal.right
        objs = []

        subproof1 = find_subproof(proof.seq, left, right)
        found1 = subproof1 is not None

        if not found1:
            assumption1 = _Line(left, "AS", ())
            subproof1 = _Proof(proof.seq + [assumption1], right)
            p1 = Prover(subproof1, prover.seen, prover.deadline)
            if not p1.prove(complete):
                return False
            subproof1.seq = subproof1.seq[len(proof.seq):]
            objs.append(subproof1)

        seq = proof.seq + objs
        subproof2 = find_subproof(seq, right, left)
        found2 = subproof2 is not None

        if not found2:
            assumption2 = _Line(right, "AS", ())
            subproof2 = _Proof(seq + [assumption2], left)
            p2 = Prover(subproof2, prover.seen, prover.deadline)
            if not p2.prove(complete):
                return False
            subproof2.seq = subproof2.seq[len(seq):]
            objs.append(subproof2)

        line = _Line(proof.goal, "↔I", (subproof1.id, subproof2.id))
        objs.append(line)
        proof.add(*objs)
        return True

    @staticmethod
    def IP(prover, complete):
        proof = prover.proof
        if is_valid([proof.goal], Bot()):
            return False
        subproof = find_subproof(proof.seq, Not(proof.goal), Bot())
        found = subproof is not None

        if not found:
            assumption = _Line(Not(proof.goal), "AS", ())
            subproof = _Proof(proof.seq + [assumption], Bot())
            p = Prover(subproof, prover.seen, prover.deadline)
            if not p.prove(complete):
                return False
            subproof.seq = subproof.seq[len(proof.seq):]

        line = _Line(proof.goal, "IP", (subproof.id,))
        objs = (line,) if found else (subproof, line)
        proof.add(*objs)
        return True


class Prover:

    def __init__(self, proof, seen=None, deadline=None):
        self.proof = proof
        self.seen = {} if seen is None else seen
        self.deadline = deadline

    def prove(self, complete):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError()
        if not self._enter_state():
            return False

        if Eliminator.elim(self):
            return True
        if Introducer.intro(self, complete):
            return True

        strategies = (
            lambda p: Eliminator.NotE_force(p, complete) and p.prove(complete),
            lambda p: Eliminator.ImpE_force(p, complete) and p.prove(complete),
            lambda p: Eliminator.IffE_force(p, complete) and p.prove(complete),
            lambda p: Eliminator.OrE(p, complete),
            lambda p: Introducer.IP(p, complete),
        )

        branches = []
        for strategy in strategies:
            p = self.copy()
            if strategy(p):
                branches.append(p.proof)
                if not complete:
                    break

        return self.proof.commit_best_branch(branches)

    def copy(self):
        return Prover(self.proof.copy(), self.seen, self.deadline)

    def _enter_state(self):
        proof = self.proof
        key = (frozenset(proof.assumptions), proof.goal)

        cost = (proof.ip_count, proof.line_count)
        formulas = frozenset(proof.formulas)

        prev = self.seen.get(key)
        if prev is not None:
            prev_cost, prev_formulas = prev

            if cost >= prev_cost and formulas <= prev_formulas:
                return False

            if cost > prev_cost:
                cost = prev_cost
            if formulas < prev_formulas:
                formulas = prev_formulas

        self.seen[key] = (cost, formulas)
        return True


class Processor:

    @staticmethod
    def process(proof):
        Processor.remove_uncited(proof, proof.id_to_citers())
        id_to_obj, id_to_citers = proof.id_to_obj(), proof.id_to_citers()
        Processor.replace_reiterations(proof, id_to_obj, id_to_citers, {})
        return Processor.translate(proof, 1, [], {})

    @staticmethod
    def remove_uncited(proof, id_to_citers):
        while True:
            seq, n = [], len(proof.seq)
            for idx, obj in enumerate(proof.seq):

                if obj.is_subproof():
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

            if obj.is_subproof():
                Processor.replace_reiterations(obj, id_to_obj, id_to_citers, replace)
                seq.append(obj)
                continue
            line = replace.get(obj.id)
            if line is not None:
                seq.append(line.copy())
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
    def translate(proof, start_idx, context, id_to_idx):
        seq, idx = [], start_idx
        for obj in proof.seq:

            if obj.is_line():
                rule = Rules.rules.get(obj.rule) or getattr(Rules, obj.rule)
                citations = tuple(id_to_idx[c] for c in obj.citations)
                j = Justification(rule, citations)
                seq.append(Line(idx, obj.formula, j))
                id_to_idx[obj.id] = idx
                idx += 1
                continue

            subproof = Processor.translate(obj, idx, context + seq, id_to_idx)
            seq.append(subproof)
            new_idx = idx + obj.line_count
            id_to_idx[obj.id] = (idx, new_idx - 1)
            idx = new_idx

        return Proof(seq, context)


def find_subproof(seq, assumption, conclusion):
    for obj in seq:
        if obj.is_line() or len(obj.seq) == 1:
            continue
        start, end = obj.seq[0], obj.seq[-1]
        if not end.is_line():
            continue
        if start.formula == assumption and end.formula == conclusion:
            return obj
    return None


def prove(premises, conclusion, timeout=3):
    cm = countermodel(premises, conclusion)
    if cm is not None:
        cm_str = "\n".join(f"{k} : {v}" for k, v in sorted(cm.items()))
        raise ProverError(f"Invalid argument. Countermodel:\n\n{cm_str}")

    seq = [_Line(p, "PR", ()) for p in premises]
    _proof = _Proof(seq, conclusion)
    p = Prover(_proof, deadline=time.monotonic() + timeout)

    try:
        proved = p.prove(complete=True)
    except TimeoutError:
        proved = False

    if not proved:
        _proof = _Proof(seq, conclusion)
        p = Prover(_proof)
        if not p.prove(complete=False):
            raise ProverError("Argument is valid, but no proof was found.")

    problem = Problem(TFL, premises, conclusion)
    proof = Processor.process(_proof)
    proof.seq = proof.seq[len(seq):]
    proof.context = problem.proof.context
    problem.proof = proof
    return problem
