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

from itertools import product
import time

import cvc5.pythonic as smt

from .checker import *


@dataclass
class Countermodel:
    worlds: list = None
    root_world: str = None
    order: list = None
    accessibility: list = None
    domain: list = None
    domains: dict = None
    equality: dict = None
    funcs: dict = field(default_factory=dict)
    preds: dict = field(default_factory=dict)

    def __str__(self):
        sections = []

        if self.worlds is not None:
            worlds = self._format_set(self.worlds, relation=False)
            sections.append(f"Worlds : {worlds}")
            sections.append(f"Root world : {self.root_world}")

            if self.order is not None:
                order = self._format_set(self.order)
                sections.append(f"Order : {order}")

            if self.accessibility is not None:
                accessibility = self._format_set(self.accessibility)
                sections.append(f"Accessibility : {accessibility}")

        if self.domain is not None:
            domain = self._format_set(self.domain, relation=False)
            sections.append(f"Domain : {domain}")

        if self.domains is not None:
            lines = ["Domains:"]
            for world, domain in self.domains.items():
                domain = self._format_set(domain, relation=False)
                lines.append(f"  {world} : {domain}")
            sections.append("\n".join(lines))

        if self.equality is not None:
            lines = ["Equality:"]
            for world, classes in self.equality.items():
                classes = ["{" + ",".join(cls) + "}" for cls in classes]
                classes = self._format_set(classes, relation=False)
                lines.append(f"  {world} : {classes}")
            sections.append("\n".join(lines))

        if self.funcs:
            lines = []
            funcs = sorted(
                self.funcs.items(),
                key=lambda item: (item[0][1] != 0, item[0])
            )
            for (name, arity), interpretation in funcs:
                if arity == 0:
                    lines.append(f"{name} : {interpretation}")
                    continue
                graph = self._format_set(sorted(
                    args + (value,)
                    for args, value in interpretation.items()
                ))
                lines.append(f"{name}^{arity} : {graph}")
            sections.append("\n".join(lines))

        if self.preds:
            lines = []
            preds = sorted(
                self.preds.items(),
                key=lambda item: (item[0][1] != 0, item[0])
            )
            for (name, arity), interpretation in preds:
                if arity != 0:
                    name = f"{name}^{arity}"
                if not (arity == 0 and self.worlds is None):
                    interpretation = self._format_set(interpretation)
                lines.append(f"{name} : {interpretation}")
            sections.append("\n".join(lines))

        return "\n".join(sections) or "Empty valuation"

    @staticmethod
    def _format_set(set, relation=True):
        if not set:
            return "{ }"
        if not relation:
            return "{ " + ", ".join(set) + " }"

        tuples = []
        for values in set:
            if len(values) == 1:
                tuples.append(values[0])
            else:
                tuples.append(f"({','.join(values)})")
        return "{ " + ", ".join(tuples) + " }"


@dataclass
class ValidityResult:
    status: str
    countermodel: Countermodel = None


class Translator:

    def __init__(
        self,
        logic,
        domain_semantics=None,
        equality_semantics=None,
        small=False,
        deadline=None
    ):
        self.intuitionistic = intuitionistic(logic)
        self.first_order = first_order(logic)
        self.modal = modal(logic)
        self.reflexive = reflexive(logic)
        self.transitive = transitive(logic)
        self.s5 = s5(logic)

        self.worlded = self.intuitionistic or self.modal
        self.domain_semantics, self.equality_semantics = resolve_semantics(
            logic, domain_semantics, equality_semantics
        )

        self.constant_domains = self.domain_semantics == "constant"
        self.expanding_domains = self.domain_semantics == "expanding"
        self.genuine_equality = self.equality_semantics == "identity"
        self.equivalence_equality = self.equality_semantics == "equivalence"

        self.deadline = deadline

        self.ctx = smt.Context()
        self.solver = smt.SolverFor("UFLIA" if small else "UF", ctx=self.ctx)
        self.solver.setOption("produce-models", "true")

        if self.first_order or self.worlded:
            self.solver.setOption("finite-model-find", "true")
            # "full" enforces minimal uninterpreted-sort models
            self.solver.setOption("uf-ss", "full" if small else "no-minimal")
        if small:
            self.solver.setOption("incremental", "true")

        self.bool_sort = smt.BoolSort(ctx=self.ctx)
        self.individual_sort = None
        self.world_sort = None
        self.root = None
        self.order = None
        self.access = None
        self.exists_at = None
        self.equal = None

        if self.first_order:
            self.individual_sort = smt.DeclareSort("__Individual", ctx=self.ctx)

        if self.worlded:
            self.world_sort = smt.DeclareSort("__World", ctx=self.ctx)
            self.root = smt.Const("__root", self.world_sort)

        if self.intuitionistic:
            self.order = smt.Function(
                "__order", self.world_sort, self.world_sort, self.bool_sort
            )

        if self.modal and not (self.s5 and not self.intuitionistic):
            self.access = smt.Function(
                "__access", self.world_sort, self.world_sort, self.bool_sort
            )

        if self.expanding_domains:
            self.exists_at = smt.Function(
                "__exists",
                self.world_sort,
                self.individual_sort,
                self.bool_sort
            )

        if self.equivalence_equality:
            self.equal = smt.Function(
                "__equal",
                self.world_sort,
                self.individual_sort,
                self.individual_sort,
                self.bool_sort
            )

        self.funcs = {}
        self.preds = {}
        self.var_count = 0

    def translate(self, formula, world=None, env=None):
        if self.intuitionistic:
            return self._translate_intuitionistic(formula, world, env)
        return self._translate_classical(formula, world, env)

    def _translate_classical(self, formula, world=None, env=None):
        if env is None:
            env = {}

        match formula:
            case Pred(name, args):
                pred = self._pred(name, len(args))
                values = [world] if self.worlded else []
                values.extend(self.term(t, env) for t in args)
                return pred(*values) if values else pred
            case Bot():
                return smt.BoolVal(False, ctx=self.ctx)
            case Not(a):
                return smt.Not(self._translate_classical(a, world, env))
            case And(a, b):
                return smt.And(
                    self._translate_classical(a, world, env),
                    self._translate_classical(b, world, env)
                )
            case Or(a, b):
                return smt.Or(
                    self._translate_classical(a, world, env),
                    self._translate_classical(b, world, env)
                )
            case Imp(a, b):
                return smt.Implies(
                    self._translate_classical(a, world, env),
                    self._translate_classical(b, world, env)
                )
            case Iff(a, b):
                return (self._translate_classical(a, world, env)
                        == self._translate_classical(b, world, env))
            case Eq(a, b):
                return self.term(a, env) == self.term(b, env)
            case Forall(var, a):
                value = self._bound_var(var)
                new_env = env | {var: value}
                inner = self._translate_classical(a, world, new_env)
                if self.expanding_domains:
                    inner = smt.Implies(self.exists_at(world, value), inner)
                return smt.ForAll([value], inner)
            case Exists(var, a):
                value = self._bound_var(var)
                new_env = env | {var: value}
                inner = self._translate_classical(a, world, new_env)
                if self.expanding_domains:
                    inner = smt.And(self.exists_at(world, value), inner)
                return smt.Exists([value], inner)
            case Box(a):
                value = self._fresh("world", self.world_sort)
                inner = self._translate_classical(a, value, env)
                if self.s5:
                    return smt.ForAll([value], inner)
                return smt.ForAll(
                    [value], smt.Implies(self.access(world, value), inner)
                )
            case Dia(a):
                value = self._fresh("world", self.world_sort)
                inner = self._translate_classical(a, value, env)
                if self.s5:
                    return smt.Exists([value], inner)
                return smt.Exists(
                    [value], smt.And(self.access(world, value), inner)
                )

    def _translate_intuitionistic(self, formula, world=None, env=None):
        if env is None:
            env = {}

        match formula:
            case Pred(name, args):
                pred = self._pred(name, len(args))
                values = [world]
                values.extend(self.term(t, env) for t in args)
                return pred(*values)
            case Bot():
                return smt.BoolVal(False, ctx=self.ctx)
            case Not(a):
                future = self._fresh("world", self.world_sort)
                inner = self._translate_intuitionistic(a, future, env)
                return smt.ForAll(
                    [future],
                    smt.Implies(self.order(world, future), smt.Not(inner))
                )
            case And(a, b):
                return smt.And(
                    self._translate_intuitionistic(a, world, env),
                    self._translate_intuitionistic(b, world, env)
                )
            case Or(a, b):
                return smt.Or(
                    self._translate_intuitionistic(a, world, env),
                    self._translate_intuitionistic(b, world, env)
                )
            case Imp(a, b):
                future = self._fresh("world", self.world_sort)
                left = self._translate_intuitionistic(a, future, env)
                right = self._translate_intuitionistic(b, future, env)
                return smt.ForAll(
                    [future], smt.Implies(
                        self.order(world, future),
                        smt.Implies(left, right)
                    )
                )
            case Iff(a, b):
                left = self._translate_intuitionistic(Imp(a, b), world, env)
                right = self._translate_intuitionistic(Imp(b, a), world, env)
                return smt.And(left, right)
            case Eq(a, b):
                left = self.term(a, env)
                right = self.term(b, env)
                if self.genuine_equality:
                    return left == right
                return self.equal(world, left, right)
            case Forall(var, a):
                future = self._fresh("world", self.world_sort)
                value = self._bound_var(var)
                new_env = env | {var: value}
                inner = self._translate_intuitionistic(a, future, new_env)
                antecedent = self.order(world, future)
                if self.expanding_domains:
                    antecedent = smt.And(
                        antecedent, self.exists_at(future, value)
                    )
                return smt.ForAll(
                    [future, value], smt.Implies(antecedent, inner)
                )
            case Exists(var, a):
                value = self._bound_var(var)
                new_env = env | {var: value}
                inner = self._translate_intuitionistic(a, world, new_env)
                if self.expanding_domains:
                    inner = smt.And(self.exists_at(world, value), inner)
                return smt.Exists([value], inner)
            case Box(a):
                future = self._fresh("world", self.world_sort)
                target = self._fresh("world", self.world_sort)
                inner = self._translate_intuitionistic(a, target, env)
                return smt.ForAll(
                    [future, target], smt.Implies(
                        smt.And(
                            self.order(world, future),
                            self.access(future, target)
                        ),
                        inner
                    )
                )
            case Dia(a):
                target = self._fresh("world", self.world_sort)
                inner = self._translate_intuitionistic(a, target, env)
                return smt.Exists(
                    [target], smt.And(self.access(world, target), inner)
                )

    def term(self, term, env):
        match term:
            case Var():
                return env[term]
            case Func(name, args):
                func = self._func(name, len(args))
                values = [self.term(t, env) for t in args]
                return func(*values) if values else func

    def semantic_constraints(self):
        constraints = []
        constraints.extend(self.frame_constraints())
        constraints.extend(self.domain_constraints())
        constraints.extend(self.predicate_constraints())
        constraints.extend(self.equality_constraints())
        return constraints

    def frame_constraints(self):
        def reflexivity(relation):
            w = self._fresh("world", self.world_sort)
            return smt.ForAll([w], relation(w, w))

        def transitivity(relation):
            w = self._fresh("world", self.world_sort)
            v = self._fresh("world", self.world_sort)
            u = self._fresh("world", self.world_sort)
            return smt.ForAll(
                [w, v, u], smt.Implies(
                    smt.And(relation(w, v), relation(v, u)),
                    relation(w, u)
                )
            )

        constraints = []

        if self.intuitionistic:
            constraints.append(reflexivity(self.order))
            constraints.append(transitivity(self.order))

            # Antisymmetry
            w = self._fresh("world", self.world_sort)
            v = self._fresh("world", self.world_sort)
            constraints.append(smt.ForAll(
                [w, v], smt.Implies(
                    smt.And(self.order(w, v), self.order(v, w)),
                    w == v
                )
            ))

        if self.modal and self.access is not None:
            if self.reflexive:
                constraints.append(reflexivity(self.access))

            if self.transitive:
                constraints.append(transitivity(self.access))

            if self.s5:
                # Symmetry
                w = self._fresh("world", self.world_sort)
                v = self._fresh("world", self.world_sort)
                constraints.append(smt.ForAll(
                    [w, v], smt.Implies(
                        self.access(w, v), self.access(v, w)
                    )
                ))

        if self.intuitionistic and self.modal:
            # Fischer-Servi source refinement
            w = self._fresh("world", self.world_sort)
            source = self._fresh("world", self.world_sort)
            target = self._fresh("world", self.world_sort)
            refined = self._fresh("world", self.world_sort)
            constraints.append(smt.ForAll(
                [w, source, target], smt.Implies(
                    smt.And(
                        self.order(w, source),
                        self.access(w, target)
                    ),
                    smt.Exists(
                        [refined], smt.And(
                            self.access(source, refined),
                            self.order(target, refined)
                        )
                    )
                )
            ))

            # Fischer-Servi target refinement
            source = self._fresh("world", self.world_sort)
            target = self._fresh("world", self.world_sort)
            refined_target = self._fresh("world", self.world_sort)
            refined_source = self._fresh("world", self.world_sort)
            constraints.append(smt.ForAll(
                [source, target, refined_target], smt.Implies(
                    smt.And(
                        self.access(source, target),
                        self.order(target, refined_target)
                    ),
                    smt.Exists(
                        [refined_source], smt.And(
                            self.order(source, refined_source),
                            self.access(refined_source, refined_target)
                        )
                    )
                )
            ))

        return constraints

    def domain_constraints(self):
        if not self.expanding_domains:
            return []

        def expansion(relation):
            source = self._fresh("world", self.world_sort)
            target = self._fresh("world", self.world_sort)
            value = self._fresh("individual", self.individual_sort)
            return smt.ForAll(
                [source, target, value], smt.Implies(
                    smt.And(
                        relation(source, target),
                        self.exists_at(source, value)
                    ),
                    self.exists_at(target, value)
                )
            )

        constraints = []

        # Nonempty domains
        world = self._fresh("world", self.world_sort)
        value = self._fresh("individual", self.individual_sort)
        constraints.append(smt.ForAll(
            [world], smt.Exists([value], self.exists_at(world, value))
        ))

        # Every individual exists at some world
        value = self._fresh("individual", self.individual_sort)
        world = self._fresh("world", self.world_sort)
        constraints.append(smt.ForAll(
            [value], smt.Exists([world], self.exists_at(world, value))
        ))

        if self.intuitionistic:
            # Domains expand along the intuitionistic order
            constraints.append(expansion(self.order))

        if self.modal and self.access is not None:
            # Domains expand along modal accessibility
            constraints.append(expansion(self.access))

        for (_, arity), func in self.funcs.items():
            if arity == 0:
                # Constants exist at every world
                world = self._fresh("world", self.world_sort)
                constraints.append(
                    smt.ForAll([world], self.exists_at(world, func))
                )
                continue

            # Functions preserve existence
            world = self._fresh("world", self.world_sort)
            values = [
                self._fresh("individual", self.individual_sort)
                for _ in range(arity)
            ]
            existing = [self.exists_at(world, value) for value in values]
            constraints.append(smt.ForAll(
                [world] + values, smt.Implies(
                    self._and(existing),
                    self.exists_at(world, func(*values))
                )
            ))

        return constraints

    def predicate_constraints(self):
        if not self.worlded:
            return []

        constraints = []

        for (_, arity), pred in self.preds.items():
            values = [
                self._fresh("individual", self.individual_sort)
                for _ in range(arity)
            ]

            if self.intuitionistic:
                # Persistence of predicates
                source = self._fresh("world", self.world_sort)
                target = self._fresh("world", self.world_sort)
                constraints.append(smt.ForAll(
                    [source, target] + values, smt.Implies(
                        smt.And(
                            self.order(source, target),
                            pred(source, *values)
                        ),
                        pred(target, *values)
                    )
                ))

            if self.expanding_domains and arity != 0:
                # Predicate arguments must exist
                world = self._fresh("world", self.world_sort)
                existing = [self.exists_at(world, value) for value in values]
                constraints.append(smt.ForAll(
                    [world] + values, smt.Implies(
                        pred(world, *values),
                        self._and(existing)
                    )
                ))

        return constraints

    def equality_constraints(self):
        if not self.equivalence_equality:
            return []

        def equality_args(arity):
            world = self._fresh("world", self.world_sort)
            lefts = [
                self._fresh("individual", self.individual_sort)
                for _ in range(arity)
            ]
            rights = [
                self._fresh("individual", self.individual_sort)
                for _ in range(arity)
            ]
            equalities = [
                self.equal(world, left, right)
                for left, right in zip(lefts, rights)
            ]
            return world, lefts, rights, equalities

        constraints = []

        world = self._fresh("world", self.world_sort)
        left = self._fresh("individual", self.individual_sort)
        right = self._fresh("individual", self.individual_sort)

        if self.expanding_domains:
            # Equal individuals must exist
            constraints.append(smt.ForAll(
                [world, left, right], smt.Implies(
                    self.equal(world, left, right),
                    smt.And(
                        self.exists_at(world, left),
                        self.exists_at(world, right)
                    )
                )
            ))

            # Reflexivity over existing individuals
            constraints.append(smt.ForAll(
                [world, left], smt.Implies(
                    self.exists_at(world, left),
                    self.equal(world, left, left)
                )
            ))
        else:
            # Reflexivity
            constraints.append(
                smt.ForAll([world, left], self.equal(world, left, left))
            )

        # Symmetry
        constraints.append(smt.ForAll(
            [world, left, right], smt.Implies(
                self.equal(world, left, right),
                self.equal(world, right, left)
            )
        ))

        # Transitivity
        third = self._fresh("individual", self.individual_sort)
        constraints.append(smt.ForAll(
            [world, left, right, third], smt.Implies(
                smt.And(
                    self.equal(world, left, right),
                    self.equal(world, right, third)
                ),
                self.equal(world, left, third)
            )
        ))

        # Persistence of equality
        source = self._fresh("world", self.world_sort)
        target = self._fresh("world", self.world_sort)
        left = self._fresh("individual", self.individual_sort)
        right = self._fresh("individual", self.individual_sort)
        constraints.append(smt.ForAll(
            [source, target, left, right], smt.Implies(
                smt.And(
                    self.order(source, target),
                    self.equal(source, left, right)
                ),
                self.equal(target, left, right)
            )
        ))

        for (_, arity), pred in self.preds.items():
            if arity == 0:
                continue

            # Predicates respect equality
            world, lefts, rights, equalities = equality_args(arity)

            constraints.append(smt.ForAll(
                [world] + lefts + rights, smt.Implies(
                    smt.And(self._and(equalities), pred(world, *lefts)),
                    pred(world, *rights)
                )
            ))

        for (_, arity), func in self.funcs.items():
            if arity == 0:
                continue

            # Functions respect equality
            world, lefts, rights, equalities = equality_args(arity)

            constraints.append(smt.ForAll(
                [world] + lefts + rights, smt.Implies(
                    self._and(equalities),
                    self.equal(world, func(*lefts), func(*rights))
                )
            ))

        return constraints

    def check(self):
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.solver.setOption(
                "tlimit-per", str(max(1, int(remaining * 1000)))
            )
        return self.solver.check()

    def minimize(self):
        best = self.extract()

        worlds = None
        individuals = None

        if self.worlded:
            worlds, best = self._minimize_sort(
                self.world_sort, "world", best
            )
            if worlds is None:
                return best

            self.solver.add(self.root == worlds[0])
            result = self.check()
            if result != smt.sat:
                return best
            best = self.extract()

        if self.first_order:
            individuals, best = self._minimize_sort(
                self.individual_sort, "individual", best
            )
            if individuals is None:
                return best

        if self.expanding_domains:
            memberships = [
                self.exists_at(world, value)
                for world in worlds for value in individuals
            ]
            best, complete = self._minimize_boolean_count(memberships, best)
            if not complete:
                return best

        if self.intuitionistic:
            order = [
                self.order(source, target)
                for source in worlds for target in worlds
            ]
            best, complete = self._minimize_boolean_count(order, best)
            if not complete:
                return best

        if self.access is not None:
            accessibility = [
                self.access(source, target)
                for source in worlds for target in worlds
            ]
            best, complete = self._minimize_boolean_count(accessibility, best)
            if not complete:
                return best

        return best

    def _minimize_sort(self, sort, name, best):
        lower = 1
        upper = len(self._sort_values(sort))

        while lower < upper:
            middle = (lower + upper) // 2
            self.solver.push()
            self._at_most_sort_size(sort, name, middle)
            result = self.check()

            if result == smt.sat:
                best = self.extract()
                upper = min(middle, len(self._sort_values(sort)))
            elif result == smt.unsat:
                lower = middle + 1
            else:
                self.solver.pop()
                return None, best

            self.solver.pop()

        values = self._fix_sort_size(sort, name, lower)
        result = self.check()
        if result != smt.sat:
            return None, best
        return values, self.extract()

    def _minimize_boolean_count(self, formulas, best):
        model = self.solver.model()
        lower = 0
        upper = sum(self._true(model, f) for f in formulas)
        count = smt.Sum([smt.If(f, 1, 0) for f in formulas])

        while lower < upper:
            middle = (lower + upper) // 2
            self.solver.push()
            self.solver.add(count <= middle)
            result = self.check()

            if result == smt.sat:
                model = self.solver.model()
                best = self.extract()
                upper = sum(self._true(model, f) for f in formulas)
            elif result == smt.unsat:
                lower = middle + 1
            else:
                self.solver.pop()
                return best, False

            self.solver.pop()

        self.solver.add(count <= upper)
        result = self.check()
        if result != smt.sat:
            return best, False
        return self.extract(), True

    def extract(self):
        model = self.solver.model()

        world_values, world_names = self._worlds(model)
        domain_values, domain_names = self._domain()

        worlds = None
        root_world = None
        order = None
        accessibility = None

        if self.worlded:
            world_values, world_names = self._reachable_worlds(
                model, world_values
            )
            worlds = [world_names[str(w)] for w in world_values]
            root_value = model.eval(self.root, model_completion=True)
            root_world = world_names[str(root_value)]

            if self.intuitionistic:
                order = sorted(
                    (world_names[str(w)], world_names[str(v)])
                    for w in world_values for v in world_values
                    if self._true(model, self.order(w, v))
                )

            if self.access is not None:
                accessibility = sorted(
                    (world_names[str(w)], world_names[str(v)])
                    for w in world_values for v in world_values
                    if self._true(model, self.access(w, v))
                )

        domain = None
        domains = None

        if self.first_order:
            if self.constant_domains:
                domain = [domain_names[str(d)] for d in domain_values]
            else:
                domains = {}
                for world in world_values:
                    name = world_names[str(world)]
                    domains[name] = [
                        domain_names[str(d)] for d in domain_values
                        if self._true(model, self.exists_at(world, d))
                    ]

        equality = None
        if self.equivalence_equality:
            equality = {}
            for world in world_values:
                name = world_names[str(world)]
                values = domain_values
                if self.expanding_domains:
                    values = [
                        d for d in domain_values
                        if self._true(model, self.exists_at(world, d))
                    ]
                equality[name] = self._equality_classes(
                    model, world, values, domain_names
                )

        funcs = {}
        for (name, arity), func in self.funcs.items():
            if arity == 0:
                value = model.eval(func, model_completion=True)
                funcs[(name, arity)] = domain_names[str(value)]
                continue

            graph = {}
            for args in product(domain_values, repeat=arity):
                key = tuple(domain_names[str(t)] for t in args)
                value = model.eval(func(*args), model_completion=True)
                graph[key] = domain_names[str(value)]
            funcs[(name, arity)] = graph

        preds = {}
        pred_worlds = world_values if self.worlded else (None,)
        for (name, arity), pred in self.preds.items():
            if arity == 0 and not self.worlded:
                preds[(name, arity)] = self._true(model, pred)
                continue

            extension = []
            for world in pred_worlds:
                values = domain_values
                if self.expanding_domains:
                    values = [
                        d for d in domain_values
                        if self._true(model, self.exists_at(world, d))
                    ]

                for args in product(values, repeat=arity):
                    pred_args = (world,) + args if self.worlded else args
                    if not self._true(model, pred(*pred_args)):
                        continue

                    item = [world_names[str(world)]] if self.worlded else []
                    item.extend(domain_names[str(t)] for t in args)
                    extension.append(item)

            preds[(name, arity)] = sorted(extension)

        return Countermodel(
            worlds,
            root_world,
            order,
            accessibility,
            domain,
            domains,
            equality,
            funcs,
            preds
        )

    def _func(self, name, arity):
        key = (name, arity)
        func = self.funcs.get(key)
        if func is not None:
            return func

        signature = [self.individual_sort] * arity

        if not signature:
            func = smt.Const(name, self.individual_sort)
        else:
            func = smt.Function(name, *signature, self.individual_sort)
        self.funcs[key] = func
        return func

    def _pred(self, name, arity):
        key = (name, arity)
        pred = self.preds.get(key)
        if pred is not None:
            return pred

        signature = [self.world_sort] if self.worlded else []
        signature.extend([self.individual_sort] * arity)

        if not signature:
            pred = smt.Const(name, self.bool_sort)
        else:
            pred = smt.Function(name, *signature, self.bool_sort)
        self.preds[key] = pred
        return pred

    def _at_most_sort_size(self, sort, name, size):
        values = [self._fresh(f"{name}_max", sort) for _ in range(size)]
        value = self._fresh(f"{name}_value", sort)
        choices = [value == v for v in values]
        coverage = choices[0] if size == 1 else smt.Or(choices)
        self.solver.add(smt.ForAll([value], coverage))
        return values

    def _fix_sort_size(self, sort, name, size):
        values = [self._fresh(f"{name}_fixed", sort) for _ in range(size)]
        if size > 1:
            self.solver.add(smt.Distinct(*values))

        value = self._fresh(f"{name}_value", sort)
        choices = [value == v for v in values]
        coverage = choices[0] if size == 1 else smt.Or(choices)
        self.solver.add(smt.ForAll([value], coverage))
        return values

    def _bound_var(self, var):
        return self._fresh(var.name, self.individual_sort)

    def _fresh(self, name, sort):
        self.var_count += 1
        return smt.Const(f"__{name}_{self.var_count}", sort)

    def _worlds(self, model):
        if not self.worlded:
            return [], {}

        root = model.eval(self.root, model_completion=True)
        values = self._sort_values(self.world_sort)
        values = [root] + [v for v in values if str(v) != str(root)]
        names = {str(v): f"w{i}" for i, v in enumerate(values)}
        return values, names

    def _domain(self):
        if not self.first_order:
            return [], {}

        values = self._sort_values(self.individual_sort)
        names = {str(v): f"d{i}" for i, v in enumerate(values)}
        return values, names

    def _sort_values(self, sort):
        values = self.solver.solver.getModelDomainElements(sort.ast)
        values = [smt.ExprRef(v, self.ctx) for v in values]
        return sorted(values, key=str)

    def _reachable_worlds(self, model, values):
        root = model.eval(self.root, model_completion=True)

        if self.s5 and not self.intuitionistic:
            values = [root] + [v for v in values if str(v) != str(root)]
            names = {str(v): f"w{i}" for i, v in enumerate(values)}
            return values, names

        worlds = {str(v): v for v in values}
        reachable = {str(root)}
        pending = [str(root)]

        while pending:
            source = pending.pop()
            source_value = worlds[source]
            for target, target_value in worlds.items():
                if target in reachable:
                    continue

                related = False
                if self.intuitionistic:
                    related = self._true(
                        model, self.order(source_value, target_value)
                    )
                if not related and self.access is not None:
                    related = self._true(
                        model, self.access(source_value, target_value)
                    )

                if related:
                    reachable.add(target)
                    pending.append(target)

        reachable.discard(str(root))
        values = [root] + [v for v in values if str(v) in reachable]
        names = {str(v): f"w{i}" for i, v in enumerate(values)}
        return values, names

    def _equality_classes(self, model, world, values, names):
        parent = {str(v): str(v) for v in values}

        def find(value):
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left, right):
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for left in values:
            for right in values:
                if self._true(model, self.equal(world, left, right)):
                    union(str(left), str(right))

        classes = {}
        for value in values:
            root = find(str(value))
            classes.setdefault(root, []).append(names[str(value)])

        return sorted(
            (sorted(cls) for cls in classes.values()),
            key=lambda cls: (cls[0], len(cls), cls)
        )

    @staticmethod
    def _and(formulas):
        if len(formulas) == 1:
            return formulas[0]
        return smt.And(formulas)

    @staticmethod
    def _true(model, formula):
        return smt.is_true(model.eval(formula, model_completion=True))


def prop_vars(formula):
    match formula:
        case Pred(name, args):
            return set() if args else {name}
        case Bot():
            return set()
        case Not(a):
            return prop_vars(a)
        case And(a, b) | Or(a, b) | Imp(a, b) | Iff(a, b):
            return prop_vars(a) | prop_vars(b)
        case _:
            return set()


def evaluate(formula, model):
    match formula:
        case Pred(name, args):
            return not args and model[(name, 0)]
        case Bot():
            return False
        case Not(a):
            return not evaluate(a, model)
        case And(a, b):
            return evaluate(a, model) and evaluate(b, model)
        case Or(a, b):
            return evaluate(a, model) or evaluate(b, model)
        case Imp(a, b):
            return not evaluate(a, model) or evaluate(b, model)
        case Iff(a, b):
            return evaluate(a, model) is evaluate(b, model)
        case _:
            return False


def check_validity_tfl(premises, conclusion, max_vars):
    all_vars = set()
    for premise in premises:
        all_vars.update(prop_vars(premise))
    all_vars.update(prop_vars(conclusion))

    n = len(all_vars)
    if n > max_vars:
        return ValidityResult("unknown")
    sorted_vars = sorted(all_vars)

    for i in range(2 ** n):
        model = {
            (var, 0): bool(i & (1 << (n - 1 - j)))
            for j, var in enumerate(sorted_vars)
        }

        if all(evaluate(p, model) for p in premises):
            if not evaluate(conclusion, model):
                cm = Countermodel(preds=model)
                return ValidityResult("invalid", cm)

    return ValidityResult("valid")


def check_validity(
    logic,
    premises,
    conclusion,
    domain_semantics=None,
    equality_semantics=None,
    small=False,
    timeout=100
):
    if not intuitionistic(logic):
        if all(is_tfl_formula(p) for p in premises):
            if is_tfl_formula(conclusion):
                result = check_validity_tfl(premises, conclusion, 15)
                if result.status != "unknown":
                    return result

    deadline = None
    if timeout is not None:
        deadline = time.monotonic() + timeout / 1000

    translator = Translator(
        logic, domain_semantics, equality_semantics, small, deadline
    )

    world = translator.root if translator.worlded else None
    formulas = [translator.translate(p, world) for p in premises]
    formulas.append(smt.Not(translator.translate(conclusion, world)))
    formulas.extend(translator.semantic_constraints())
    translator.solver.add(*formulas)

    result = translator.check()
    if result == smt.sat:
        cm = translator.minimize() if small else translator.extract()
        return ValidityResult("invalid", cm)

    if result == smt.unsat:
        return ValidityResult("valid")
    return ValidityResult("unknown")
