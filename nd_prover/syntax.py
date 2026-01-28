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

from dataclasses import dataclass, field


class Metavar:
    count = 0

    def __init__(self, domain=None):
        Metavar.count += 1
        self.id = Metavar.count
        self.domain = domain
        self.value = None

    def __repr__(self):
        return (
            f"Metavar(id={self.id!r}, "
            f"domain={self.domain!r}, "
            f"value={self.value!r})"
        )

    def __str__(self):
        return f"?m{self.id}"

    def __eq__(self, other):
        if self.domain and other not in self.domain:
            return False
        if self.value is None:
            self.value = other
            return True
        return self.value == other

    def _unify(self, other, metavars):
        if self.domain and other not in self.domain:
            return False
        if self.value is None:
            self.value = other
            metavars.append(self)
            return True
        return self.value._unify(other, metavars)


class Formula:

    def __str__(self):
        s = self._str()
        if s[0] == "(" and s[-1] == ")":
            return s[1:-1]
        return s

    def unify(self, other, metavars):
        _metavars = []
        if self._unify(other, _metavars):
            metavars.extend(_metavars)
            return True
        for metavar in _metavars:
            metavar.value = None
        return False

# TFL
@dataclass(frozen=True)
class Bot(Formula):

    def _str(self):
        return "⊥"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return isinstance(other, Bot)

@dataclass(frozen=True)
class Not(Formula):
    inner: Formula

    def _str(self):
        return f"¬{self.inner._str()}"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Not) 
            and self.inner._unify(other.inner, metavars)
        )

@dataclass(frozen=True)
class And(Formula):
    left: Formula
    right: Formula

    def _str(self):
        return f"({self.left._str()} ∧ {self.right._str()})"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, And) 
            and self.left._unify(other.left, metavars) 
            and self.right._unify(other.right, metavars)
        )

@dataclass(frozen=True)
class Or(Formula):
    left: Formula
    right: Formula

    def _str(self):
        return f"({self.left._str()} ∨ {self.right._str()})"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Or) 
            and self.left._unify(other.left, metavars) 
            and self.right._unify(other.right, metavars)
        )

@dataclass(frozen=True)
class Imp(Formula):
    left: Formula
    right: Formula

    def _str(self):
        return f"({self.left._str()} → {self.right._str()})"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Imp) 
            and self.left._unify(other.left, metavars) 
            and self.right._unify(other.right, metavars)
        )

@dataclass(frozen=True)
class Iff(Formula):
    left: Formula
    right: Formula

    def _str(self):
        return f"({self.left._str()} ↔ {self.right._str()})"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Iff) 
            and self.left._unify(other.left, metavars) 
            and self.right._unify(other.right, metavars)
        )

# FOL
class Term:

    def __str__(self):
        return self._str()

@dataclass(frozen=True)
class Func(Term):
    name: str
    args: tuple[Term]

    names = "abcdefghijklmnopqr"

    def _str(self):
        if not self.args:
            return self.name
        return f"{self.name}({', '.join(str(t) for t in self.args)})"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        if not (isinstance(other, Func) and self.name == other.name 
                and len(self.args) == len(other.args)):
            return False
        return all(
            t1._unify(t2, metavars) for t1, t2 in zip(self.args, other.args)
        )

@dataclass(frozen=True)
class Var(Term):
    name: str

    names = "stuvwxyz"

    def _str(self):
        return self.name

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return isinstance(other, Var) and self.name == other.name

@dataclass(frozen=True)
class Pred(Formula):
    name: str
    args: tuple[Term]

    def _str(self):
        if not self.args:
            return self.name
        return f"{self.name}({', '.join(str(t) for t in self.args)})"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        if not (isinstance(other, Pred) and self.name == other.name 
                and len(self.args) == len(other.args)):
            return False
        return all(
            t1._unify(t2, metavars) for t1, t2 in zip(self.args, other.args)
        )

@dataclass(frozen=True)
class Eq(Formula):
    left: Term
    right: Term

    def _str(self):
        return f"{self.left} = {self.right}"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Eq) 
            and self.left._unify(other.left, metavars) 
            and self.right._unify(other.right, metavars)
        )

@dataclass(frozen=True)
class Forall(Formula):
    var: Var
    inner: Formula

    def _str(self):
        return f"∀{self.var} {self.inner._str()}"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Forall) 
            and self.var._unify(other.var, metavars) 
            and self.inner._unify(other.inner, metavars)
        )

@dataclass(frozen=True)
class Exists(Formula):
    var: Var
    inner: Formula

    def _str(self):
        return f"∃{self.var} {self.inner._str()}"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Exists) 
            and self.var._unify(other.var, metavars) 
            and self.inner._unify(other.inner, metavars)
        )

# ML
@dataclass(frozen=True)
class Box(Formula):
    inner: Formula

    def _str(self):
        return f"☐{self.inner._str()}"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Box) 
            and self.inner._unify(other.inner, metavars)
        )

@dataclass(frozen=True)
class Dia(Formula):
    inner: Formula

    def _str(self):
        return f"◇{self.inner._str()}"

    def _unify(self, other, metavars):
        if isinstance(other, Metavar):
            return other._unify(self, metavars)
        return (
            isinstance(other, Dia) 
            and self.inner._unify(other.inner, metavars)
        )

@dataclass(frozen=True)
class BoxMarker:

    def __str__(self):
        return "☐"


def is_tfl_formula(formula):
    match formula:
        case Pred(_, args):
            return not args
        case Bot():
            return True
        case Not(a):
            return is_tfl_formula(a)
        case And(a, b) | Or(a, b) | Imp(a, b) | Iff(a, b):
            return is_tfl_formula(a) and is_tfl_formula(b)
        case _:
            return False


def is_fol_formula(formula):
    match formula:
        case Bot() | Pred() | Eq():
            return True
        case Not(a) | Forall(_, a) | Exists(_, a):
            return is_fol_formula(a)
        case And(a, b) | Or(a, b) | Imp(a, b) | Iff(a, b):
            return is_fol_formula(a) and is_fol_formula(b)
        case _:
            return False


def is_fol_sentence(formula):
    return is_fol_formula(formula) and not free_vars(formula)


def is_ml_formula(formula):
    match formula:
        case Pred(_, args):
            return not args
        case Bot():
            return True
        case Not(a) | Box(a) | Dia(a):
            return is_ml_formula(a)
        case And(a, b) | Or(a, b) | Imp(a, b) | Iff(a, b):
            return is_ml_formula(a) and is_ml_formula(b)
        case _:
            return False


def atomic_terms(formula, free):
    match formula:
        case Bot():
            return set()
        case Not(a) | Box(a) | Dia(a):
            return atomic_terms(a, free)
        case And(a, b) | Or(a, b) | Imp(a, b) | Iff(a, b) | Eq(a, b):
            return atomic_terms(a, free) | atomic_terms(b, free)
        case Func(_, args) as f:
            if not args:
                return {f}
            return set().union(*(atomic_terms(t, free) for t in args))
        case Var() as v:
            return {v}
        case Pred(_, args):
            return set().union(*(atomic_terms(t, free) for t in args))
        case Forall(v, a) | Exists(v, a):
            return atomic_terms(a, free) - ({v} if free else set())
        case _:
            return set()


def constants(formula):
    all_terms = atomic_terms(formula, free=False)
    return {t for t in all_terms if isinstance(t, Func)}


def free_vars(formula):
    free_terms = atomic_terms(formula, free=True)
    return {t for t in free_terms if isinstance(t, Var)}


def sub_term(formula, term, gen, ignore=lambda v: False):
    match formula:
        case Bot():
            return formula
        case Not(a) | Box(a) | Dia(a):
            a = sub_term(a, term, gen, ignore)
            return type(formula)(a)
        case And(a, b) | Or(a, b) | Imp(a, b) | Iff(a, b) | Eq(a, b):
            a = sub_term(a, term, gen, ignore)
            b = sub_term(b, term, gen, ignore)
            return type(formula)(a, b)
        case Func(s, args) as f:
            if f == term:
                return gen()
            args = tuple(sub_term(t, term, gen, ignore) for t in args)
            return Func(s, args)
        case Var() as v:
            return gen() if v == term else v
        case Pred(s, args):
            args = tuple(sub_term(t, term, gen, ignore) for t in args)
            return Pred(s, args)
        case Forall(v, a) | Exists(v, a):
            if not (v == term or ignore(v)):
                a = sub_term(a, term, gen, ignore)
            return type(formula)(v, a)
        case _:
            return formula
