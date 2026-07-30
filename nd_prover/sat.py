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
    accessibility: list = None
    domain: list = None
    funcs: dict = field(default_factory=dict)
    preds: dict = field(default_factory=dict)

    def __str__(self):
        sections = []

        if self.worlds is not None:
            sections.append(f"Worlds : {', '.join(self.worlds)}")
            sections.append(f"Root world : {self.root_world}")
            if self.accessibility is not None:
                accessibility = self._format_relation(self.accessibility)
                sections.append(f"Accessibility : {accessibility}")

        if self.domain is not None:
            sections.append(f"Domain : {', '.join(self.domain)}")

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
                graph = self._format_relation(sorted(
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
                    interpretation = self._format_relation(interpretation)
                lines.append(f"{name} : {interpretation}")
            sections.append("\n".join(lines))

        return "\n".join(sections) or "Empty valuation"

    @staticmethod
    def _format_relation(relation):
        tuples = []
        for values in relation:
            if len(values) == 1:
                tuples.append(values[0])
            else:
                tuples.append(f"({','.join(values)})")
        return "{ " + ", ".join(tuples) + " }"


@dataclass
class ValidityResult:
    status: str
    countermodel: Countermodel = None


class _Translator:

    def __init__(self, logic, small, timeout):
        self.first_order = issubclass(logic, FOL)
        self.modal = issubclass(logic, MLK)
        self.reflexive = issubclass(logic, MLT)
        self.transitive = issubclass(logic, MLS4)
        self.s5 = issubclass(logic, MLS5)

        self.deadline = None
        if timeout is not None:
            self.deadline = time.monotonic() + timeout / 1000

        self.ctx = smt.Context()
        minimize_accessibility = small and self.modal and not self.s5
        solver_logic = "UFLIA" if minimize_accessibility else "UF"
        self.solver = smt.SolverFor(solver_logic, ctx=self.ctx)
        self.solver.setOption("produce-models", "true")

        if self.first_order or self.modal:
            self.solver.setOption("finite-model-find", "true")
            # "full" enforces minimal uninterpreted-sort models
            self.solver.setOption("uf-ss", "full" if small else "no-minimal")
        if minimize_accessibility:
            self.solver.setOption("incremental", "true")

        self.bool_sort = smt.BoolSort(ctx=self.ctx)
        self.individual_sort = None
        self.world_sort = None
        self.root = None
        self.access = None

        if self.first_order:
            self.individual_sort = smt.DeclareSort("__Individual", ctx=self.ctx)

        if self.modal:
            self.world_sort = smt.DeclareSort("__World", ctx=self.ctx)
            self.root = smt.Const("__root", self.world_sort)
            # The root equivalence class of an S5 frame is universal
            if not self.s5:
                self.access = smt.Function(
                    "__access", self.world_sort, self.world_sort, self.bool_sort
                )

        self.funcs = {}
        self.preds = {}
        self.var_count = 0

    def translate(self, formula, world=None, env=None):
        if env is None:
            env = {}

        match formula:
            case Pred(name, args):
                pred = self._pred(name, len(args))
                values = [world] if self.modal else []
                values.extend(self.term(t, env) for t in args)
                return pred(*values) if values else pred
            case Bot():
                return smt.BoolVal(False, ctx=self.ctx)
            case Not(a):
                return smt.Not(self.translate(a, world, env))
            case And(a, b):
                return smt.And(
                    self.translate(a, world, env),
                    self.translate(b, world, env)
                )
            case Or(a, b):
                return smt.Or(
                    self.translate(a, world, env),
                    self.translate(b, world, env)
                )
            case Imp(a, b):
                return smt.Implies(
                    self.translate(a, world, env),
                    self.translate(b, world, env)
                )
            case Iff(a, b):
                return (self.translate(a, world, env)
                        == self.translate(b, world, env))
            case Eq(a, b):
                return self.term(a, env) == self.term(b, env)
            case Forall(var, a):
                value = self._bound_var(var)
                new_env = env | {var: value}
                return smt.ForAll(
                    [value], self.translate(a, world, new_env)
                )
            case Exists(var, a):
                value = self._bound_var(var)
                new_env = env | {var: value}
                return smt.Exists(
                    [value], self.translate(a, world, new_env)
                )
            case Box(a):
                value = self._fresh("world", self.world_sort)
                inner = self.translate(a, value, env)
                if self.s5:
                    return smt.ForAll([value], inner)
                return smt.ForAll(
                    [value], smt.Implies(self.access(world, value), inner)
                )
            case Dia(a):
                value = self._fresh("world", self.world_sort)
                inner = self.translate(a, value, env)
                if self.s5:
                    return smt.Exists([value], inner)
                return smt.Exists(
                    [value], smt.And(self.access(world, value), inner)
                )

    def term(self, term, env):
        match term:
            case Var():
                return env[term]
            case Func(name, args):
                func = self._func(name, len(args))
                values = [self.term(t, env) for t in args]
                return func(*values) if values else func

    def frame_constraints(self):
        if not self.modal or self.s5:
            return []

        constraints = []
        if self.reflexive:
            w = self._fresh("world", self.world_sort)
            constraints.append(smt.ForAll([w], self.access(w, w)))

        if self.transitive:
            w = self._fresh("world", self.world_sort)
            v = self._fresh("world", self.world_sort)
            u = self._fresh("world", self.world_sort)
            constraints.append(smt.ForAll(
                [w, v, u], smt.Implies(
                    smt.And(self.access(w, v), self.access(v, u)),
                    self.access(w, u)
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

    def minimize_accessibility(self):
        best = self.extract()
        best_size = len(best.accessibility)

        world_count = len(self._sort_values(self.world_sort))

        domain_count = 0
        if self.first_order:
            domain_count = len(self._sort_values(self.individual_sort))

        worlds = self._fix_sort_size(self.world_sort, "w", world_count)
        if self.first_order:
            self._fix_sort_size(self.individual_sort, "d", domain_count)
        self.solver.add(self.root == worlds[0])

        result = self.check()
        if result != smt.sat:
            return best

        model = self.solver.model()
        candidate = self.extract()
        if len(candidate.accessibility) < best_size:
            best = candidate
            best_size = len(candidate.accessibility)

        edges = [self.access(w, v) for w in worlds for v in worlds]
        edge_count = smt.Sum([smt.If(e, 1, 0) for e in edges])

        lower = world_count if self.reflexive else 0
        upper = sum(self._true(model, e) for e in edges)

        while lower < upper:
            middle = (lower + upper) // 2
            self.solver.push()
            self.solver.add(edge_count <= middle)
            result = self.check()

            if result == smt.sat:
                model = self.solver.model()
                candidate = self.extract()
                if len(candidate.accessibility) < best_size:
                    best = candidate
                    best_size = len(candidate.accessibility)
                upper = sum(self._true(model, e) for e in edges)
            elif result == smt.unsat:
                lower = middle + 1
            else:
                self.solver.pop()
                return best

            self.solver.pop()

        return best

    def extract(self):
        model = self.solver.model()

        world_values, world_names = self._worlds(model)
        domain_values, domain_names = self._domain()

        if self.modal and not self.s5:
            world_values, world_names = self._reachable_worlds(
                model, world_values
            )

        worlds = None
        root_world = None
        accessibility = None

        if self.modal:
            worlds = [world_names[str(w)] for w in world_values]
            root_value = model.eval(self.root, model_completion=True)
            root_world = world_names[str(root_value)]
            if not self.s5:
                accessibility = sorted(
                    (world_names[str(w)], world_names[str(v)])
                    for w in world_values for v in world_values
                    if self._true(model, self.access(w, v))
                )

        domain = None
        if self.first_order:
            domain = [domain_names[str(d)] for d in domain_values]

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
        pred_worlds = world_values if self.modal else (None,)
        for (name, arity), pred in self.preds.items():
            if arity == 0 and not self.modal:
                preds[(name, arity)] = self._true(model, pred)
                continue

            extension = []
            for world in pred_worlds:
                for args in product(domain_values, repeat=arity):
                    values = (world,) + args if self.modal else args
                    if not self._true(model, pred(*values)):
                        continue

                    item = [world_names[str(world)]] if self.modal else []
                    item.extend(domain_names[str(t)] for t in args)
                    extension.append(item)

            preds[(name, arity)] = sorted(extension)

        return Countermodel(
            worlds, root_world, accessibility, domain, funcs, preds
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

        signature = [self.world_sort] if self.modal else []
        signature.extend([self.individual_sort] * arity)

        if not signature:
            pred = smt.Const(name, self.bool_sort)
        else:
            pred = smt.Function(name, *signature, self.bool_sort)
        self.preds[key] = pred
        return pred

    def _fix_sort_size(self, sort, name, size):
        values = [smt.Const(f"__{name}_{i}", sort) for i in range(size)]
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
        if not self.modal:
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
        worlds = {str(v): v for v in values}

        reachable = {str(root)}
        pending = [str(root)]

        while pending:
            source = pending.pop()
            for target, value in worlds.items():
                if target in reachable:
                    continue
                if self._true(model, self.access(worlds[source], value)):
                    reachable.add(target)
                    pending.append(target)

        reachable.discard(str(root))
        values = [root] + [v for v in values if str(v) in reachable]
        names = {str(v): f"w{i}" for i, v in enumerate(values)}
        return values, names

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


def check_validity(logic, premises, conclusion, small=False, timeout=10):
    if all(is_tfl_formula(p) for p in premises) and is_tfl_formula(conclusion):
        result = check_validity_tfl(premises, conclusion, 15)
        if result.status != "unknown":
            return result

    translator = _Translator(logic, small, timeout)
    world = translator.root if translator.modal else None

    formulas = [translator.translate(p, world) for p in premises]
    formulas.append(smt.Not(translator.translate(conclusion, world)))
    formulas.extend(translator.frame_constraints())
    translator.solver.add(*formulas)

    result = translator.check()
    if result == smt.sat:
        if small and translator.modal and not translator.s5:
            cm = translator.minimize_accessibility()
        else:
            cm = translator.extract()
        return ValidityResult("invalid", cm)

    if result == smt.unsat:
        return ValidityResult("valid")
    return ValidityResult("unknown")
