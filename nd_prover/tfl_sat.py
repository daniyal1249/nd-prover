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


def prop_vars(formula):
    match formula:
        case Pred(s, args):
            return set() if args else {s}
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
        case Pred(s, args):
            return not args and model[s]
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


def countermodel(premises, conclusion):
    all_vars = set()
    for premise in premises:
        all_vars |= prop_vars(premise)
    all_vars |= prop_vars(conclusion)

    sorted_vars = sorted(all_vars)
    n = len(sorted_vars)

    for i in range(2 ** n):
        model = {
            var: bool(i & (1 << (n - 1 - j))) 
            for j, var in enumerate(sorted_vars)
        }

        if all(evaluate(p, model) for p in premises):
            if not evaluate(conclusion, model):
                return model

    return None


def is_valid(premises, conclusion):
    return countermodel(premises, conclusion) is None
