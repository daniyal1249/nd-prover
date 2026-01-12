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

import re

from .checker import *


class ParsingError(Exception):
    pass


class Symbols:
    symbols = {
        "not": "¬",
        "~": "¬",
        "∼": "¬",
        "-": "¬",
        "−": "¬",
        "and": "∧",
        "^": "∧",
        "&": "∧",
        "&&": "∧",
        ".": "∧",
        "·": "∧",
        "*": "∧",
        "or": "∨",
        "|": "∨",
        "||": "∨",
        "+": "∨",
        "iff": "↔",
        "≡": "↔",
        "<->": "↔",
        "<=>": "↔",
        "imp": "→",
        "⇒": "→",
        "⊃": "→",
        "->": "→",
        "=>": "→",
        ">": "→",
        "forall": "∀",
        "⋀": "∀",
        "!": "∀",
        "exists": "∃",
        "⋁": "∃",
        "?": "∃",
        "bot": "⊥",
        "XX": "⊥",
        "#": "⊥",
        "_": "⊥",
        "box": "☐",
        "[]": "☐",
        "dia": "◇",
        "<>": "◇",
    }

    keys = sorted(symbols, key=len, reverse=True)
    patterns = [re.escape(k) for k in keys]
    patterns.append(r"A(?=[s-zIE])")  # Forall
    patterns.append(r"E(?=[s-zIE])")  # Exists
    pattern = "|".join(patterns)
    regex = re.compile(pattern)

    @classmethod
    def sub(cls, s):
        def repl(m):
            match = m.group(0)
            if match == "A":
                return "∀"
            if match == "E":
                return "∃"
            return cls.symbols[match]
        return cls.regex.sub(repl, s)


def split_line(line):
    parts = [s.strip() for s in line.split(";")]
    if len(parts) != 2:
        raise ParsingError('Must provide justification separated by ";".')
    return parts


def strip_parens(s):
    while s and s[0] == "(" and s[-1] == ")":
        depth = 0
        for i, c in enumerate(s):
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0 and i != len(s) - 1:
                    return s
        s = s[1:-1]
    return s


def find_main_connective(s, symbol):
    depth = 0
    for i in range(len(s)):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            depth -= 1
        elif depth == 0 and s[i] == symbol:
            return i
    return -1


def split_args(s):
    if not s:
        return []
    args, depth, start = [], 0, 0
    for i, c in enumerate(s):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            args.append(s[start:i].strip())
            start = i + 1
    args.append(s[start:].strip())
    return args


def parse_args_from_parens(s, start_idx, error_context):
    if s[start_idx] != "(":
        raise ParsingError(f'Missing "(" in {error_context} application: "{s}".')
    
    depth, i = 1, start_idx + 1
    while i < len(s) and depth > 0:
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
        i += 1
    
    if depth != 0:
        raise ParsingError(f'Missing ")" in {error_context} application: "{s}".')
    args_str = s[start_idx + 1:i - 1]
    return args_str, i


def parse_term(t):
    t = strip_parens(t)
    
    # Variables
    if len(t) == 1 and t in Var.names:
        return Var(t)
    
    # Functions
    if t and t[0] in Func.names:
        name = t[0]
        if len(t) == 1:
            return Func(name, ())

        args_str, end_idx = parse_args_from_parens(t, 1, "function")
        if end_idx != len(t):
            raise ParsingError(f'Unexpected trailing characters in "{t}".')
        args = ()
        if args_str.strip():
            args = tuple(parse_term(arg) for arg in split_args(args_str))
        return Func(name, args)
    
    raise ParsingError(f'Term "{t}" is not well-formed.')


def _parse_formula(f):
    f = strip_parens(f)
    
    # Bottom
    if f == "⊥":
        return Bot()

    # Binary connectives
    connectives = [("↔", Iff), ("→", Imp), ("∨", Or), ("∧", And)]

    for sym, cls in connectives:
        idx = find_main_connective(f, sym)
        if idx != -1:
            left = _parse_formula(f[:idx])
            right = _parse_formula(f[idx + 1:])
            return cls(left, right)

    # Negation
    if f.startswith("¬"):
        return Not(_parse_formula(f[1:]))
    
    # Quantifiers
    v1, v2 = Var.names[0], Var.names[-1]
    m = re.match(f"(∀|∃)([{v1}-{v2}])", f)
    if m:
        var = Var(m.group(2))
        inner = _parse_formula(f[2:])
        if m.group(1) == "∀":
            return Forall(var, inner)
        return Exists(var, inner)

    # Modal operators
    if f.startswith("☐"):
        return Box(_parse_formula(f[1:]))
    if f.startswith("◇"):
        return Dia(_parse_formula(f[1:]))

    # Equality
    idx = find_main_connective(f, "=")
    if idx != -1:
        left = parse_term(f[:idx])
        right = parse_term(f[idx + 1:])
        return Eq(left, right)

    # Predicates
    if f and f[0].isalpha() and f[0].isupper():
        name = f[0]
        if len(f) == 1:
            return Pred(name, ())

        args_str, end_idx = parse_args_from_parens(f, 1, "predicate")
        if end_idx != len(f):
            raise ParsingError(f'Unexpected trailing characters in "{f}".')
        args = ()
        if args_str.strip():
            args = tuple(parse_term(arg) for arg in split_args(args_str))
        return Pred(name, args)

    raise ParsingError(f'Formula "{f}" is not well-formed.')


def parse_formula(f):
    f = "".join(Symbols.sub(f).split())
    return _parse_formula(f)


def parse_assumption(a):
    a = "".join(Symbols.sub(a).split())
    if a == "☐":
        return BoxMarker()
    return _parse_formula(a)


def parse_rule(rule):
    rule = "".join(Symbols.sub(rule).split())
    r = Rules.rules.get(rule)
    if r is None:
        raise ParsingError(f'Rule of inference "{rule}" not recognized.')
    return r


def parse_citations(citations):
    citations = "".join(citations.split())

    c_list = []
    for c in citations.split(","):
        m = re.fullmatch(r"(\d+)-(\d+)", c)
        if m:
            pair = (int(m.group(1)), int(m.group(2)))
            c_list.append(pair)
            continue
        try:
            c_list.append(int(c))
        except ValueError:
            raise ParsingError(f'Invalid citations syntax: "{citations}".')
    return tuple(c_list)


def parse_justification(j):
    parts = j.split(",", maxsplit=1)
    r = parse_rule(parts[0])
    if len(parts) == 1:
        return Justification(r, ())
    c = parse_citations(parts[1])
    return Justification(r, c)


def parse_line(line):
    f, j = split_line(line)
    return parse_formula(f), parse_justification(j)
