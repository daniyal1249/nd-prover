from dataclasses import dataclass
from pathlib import Path
import re
import sys

from nd_prover import *


class TPTPError(Exception):
    pass


class UnsupportedTPTPFeature(TPTPError):

    def __init__(self, feature, message):
        super().__init__(message)
        self.feature = feature


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    pos: int


@dataclass(frozen=True)
class AnnotatedFormula:
    name: str
    role: str
    formula: object
    language: str


@dataclass(frozen=True)
class Include:
    path: str
    names: tuple = None


@dataclass
class ParsedFile:
    path: Path
    formulas: list
    includes: list
    text: str


_MULTI_OPS = ("<=>", "<~>", "=>", "<=", "!=", "~&", "~|")
_SINGLE = set("()[],:.!?~&|=")
_NUMBER = re.compile(r"[+-]?(?:\d+/\d+|\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)")
_WORD = re.compile(r"(?:\$\$?|#)?[A-Za-z_][A-Za-z0-9_]*")
_PARSE_RECURSION_LIMIT = 50_000


def tokenize(text):
    tokens = []
    i = 0

    while i < len(text):
        if text[i].isspace():
            i += 1
            continue

        if text[i] == "%":
            newline = text.find("\n", i)
            i = len(text) if newline == -1 else newline + 1
            continue

        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                raise TPTPError(
                    f"Unterminated block comment at character {i}."
                )
            i = end + 2
            continue

        if text[i] in "'\"":
            quote = text[i]
            start = i
            i += 1
            value = []
            while i < len(text):
                if text[i] == "\\" and i + 1 < len(text):
                    value.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                value.append(text[i])
                i += 1
            else:
                raise TPTPError(f"Unterminated quoted token at character {start}.")
            kind = "DISTINCT" if quote == '"' else "QUOTED"
            tokens.append(Token(kind, "".join(value), start))
            continue

        matched = False
        for op in _MULTI_OPS:
            if text.startswith(op, i):
                tokens.append(Token("SYMBOL", op, i))
                i += len(op)
                matched = True
                break
        if matched:
            continue

        if text[i] in _SINGLE:
            tokens.append(Token("SYMBOL", text[i], i))
            i += 1
            continue

        m = _NUMBER.match(text, i)
        if m:
            tokens.append(Token("NUMBER", m.group(0), i))
            i = m.end()
            continue

        m = _WORD.match(text, i)
        if m:
            tokens.append(Token("WORD", m.group(0), i))
            i = m.end()
            continue

        # Annotation punctuation is skipped; unknown formula tokens still fail.
        tokens.append(Token("OTHER", text[i], i))
        i += 1

    tokens.append(Token("EOF", "", len(text)))
    return tokens


def _encoded_name(kind, name):
    encoded = name.encode("utf-8").hex()
    return f"tptp_{kind}_{encoded}"


def _make_and(formulas):
    formulas = list(formulas)
    if not formulas:
        return Not(Bot())
    result = formulas[0]
    for formula in formulas[1:]:
        result = And(result, formula)
    return result


def _distinct(args):
    pairs = []
    for i, left in enumerate(args):
        for right in args[i + 1:]:
            pairs.append(Not(Eq(left, right)))
    return _make_and(pairs)


def _balance_associative(formula):
    """Balance And/Or chains before nd_prover's recursive validation."""
    rebuilt = {}
    stack = [(formula, False)]
    operands = {}

    while stack:
        current, visited = stack.pop()
        key = id(current)
        if visited:
            match current:
                case Bot() | Pred() | Eq():
                    result = current
                case Not(inner):
                    result = Not(rebuilt[id(inner)])
                case And() | Or():
                    result = _balanced_binary(
                        type(current),
                        [rebuilt[id(item)] for item in operands[key]]
                    )
                case Imp(left, right):
                    result = Imp(rebuilt[id(left)], rebuilt[id(right)])
                case Iff(left, right):
                    result = Iff(rebuilt[id(left)], rebuilt[id(right)])
                case Forall(var, inner):
                    result = Forall(var, rebuilt[id(inner)])
                case Exists(var, inner):
                    result = Exists(var, rebuilt[id(inner)])
                case Box(inner):
                    result = Box(rebuilt[id(inner)])
                case Dia(inner):
                    result = Dia(rebuilt[id(inner)])
                case _:
                    result = current
            rebuilt[key] = result
            continue

        if key in rebuilt:
            continue
        stack.append((current, True))
        match current:
            case And() | Or():
                items, pending = [], [current]
                while pending:
                    item = pending.pop()
                    if isinstance(item, type(current)):
                        pending.extend((item.right, item.left))
                    else:
                        items.append(item)
                operands[key] = items
                stack.extend((item, False) for item in reversed(items))
            case Not(inner) | Forall(_, inner) | Exists(_, inner) | Box(
                inner
            ) | Dia(inner):
                stack.append((inner, False))
            case And(left, right) | Or(left, right) | Imp(
                left, right
            ) | Iff(left, right):
                stack.append((right, False))
                stack.append((left, False))

    return rebuilt[id(formula)]


def _balanced_binary(cls, operands):
    while len(operands) > 1:
        combined = []
        for idx in range(0, len(operands), 2):
            if idx + 1 == len(operands):
                combined.append(operands[idx])
            else:
                combined.append(cls(operands[idx], operands[idx + 1]))
        operands = combined
    return operands[0]


class Parser:

    _precedence = {
        "<=>": 10,
        "<~>": 10,
        "=>": 20,
        "<=": 20,
        "|": 30,
        "~|": 30,
        "&": 40,
        "~&": 40
    }

    def __init__(self, text):
        self.text = text
        self.tokens = tokenize(text)
        self.idx = 0
        self.anon_count = 0

    @property
    def token(self):
        return self.tokens[self.idx]

    def parse_file(self, path):
        formulas, includes = [], []

        while self.token.kind != "EOF":
            word = self._expect_atom()
            if word == "include":
                includes.append(self._parse_include())
            elif word in {"fof", "qmf"}:
                formulas.append(self._parse_annotated(word))
            elif word == "tpi":
                raise UnsupportedTPTPFeature(
                    "PROCESS_INSTRUCTION", "TPTP process instructions are unsupported."
                )
            else:
                raise self._error(
                    f'Unsupported top-level statement "{word}".'
                )

        return ParsedFile(
            Path(path), formulas, includes, self.text
        )

    def parse_formula(self):
        return self._parse_binary(0)

    def _parse_include(self):
        self._expect("(")
        path = self._expect_atom()
        names = None
        if self._accept(","):
            self._expect("[")
            items = []
            if not self._accept("]"):
                while True:
                    items.append(self._expect_atom())
                    if self._accept("]"):
                        break
                    self._expect(",")
            names = tuple(items)
        self._expect(")")
        self._expect(".")
        return Include(path, names)

    def _parse_annotated(self, language):
        self._expect("(")
        name = self._expect_atom()
        self._expect(",")
        role = self._expect_atom()
        self._expect(",")
        formula = _balance_associative(self.parse_formula())

        if self._accept(","):
            self._skip_until_closing_paren()
        else:
            self._expect(")")
        self._expect(".")
        return AnnotatedFormula(name, role, formula, language)

    def _parse_binary(self, min_precedence):
        left = self._parse_prefix()

        while True:
            op = self.token.value
            precedence = self._precedence.get(op)
            if precedence is None or precedence < min_precedence:
                break

            self.idx += 1
            next_precedence = precedence
            if op in {"&", "|", "~&", "~|"}:
                next_precedence += 1
            right = self._parse_binary(next_precedence)
            left = self._binary(op, left, right)

        return left

    def _parse_prefix(self):
        if self._accept("~"):
            return Not(self._parse_prefix())

        if self.token.value in {"!", "?"}:
            quantifier = self.token.value
            self.idx += 1
            self._expect("[")
            variables = []
            while True:
                variables.append(self._variable())
                if self._accept("]"):
                    break
                self._expect(",")
            self._expect(":")
            inner = self._parse_prefix()
            cls = Forall if quantifier == "!" else Exists
            for var in reversed(variables):
                inner = cls(var, inner)
            return inner

        if self.token.value in {"#box", "#dia"}:
            operator = self.token.value
            self.idx += 1
            if self._accept("("):
                index = self._expect_atom()
                self._expect(")")
                raise UnsupportedTPTPFeature(
                    "MULTIMODAL",
                    f"Indexed modality {operator}({index}) is unsupported."
                )
            self._expect(":")
            inner = self._parse_prefix()
            return Box(inner) if operator == "#box" else Dia(inner)

        if self._accept("("):
            formula = self._parse_binary(0)
            self._expect(")")
            return formula

        if self.token.value == "$true":
            self.idx += 1
            return Not(Bot())
        if self.token.value == "$false":
            self.idx += 1
            return Bot()

        return self._parse_atomic()

    def _parse_atomic(self):
        token = self.token
        if token.kind == "WORD" and token.value.startswith("$"):
            if token.value == "$distinct":
                self.idx += 1
                args = self._parse_term_args()
                return _distinct(args)
            if token.value == "$equal":
                self.idx += 1
                args = self._parse_term_args()
                if len(args) != 2:
                    raise self._error("$equal requires exactly two arguments.")
                return Eq(*args)

        if self.token.kind == "WORD" and self.token.value.startswith("$"):
            raise UnsupportedTPTPFeature(
                "DEFINED_PREDICATE",
                f'Defined predicate "{self.token.value}" is unsupported.'
            )

        term = self._parse_term()
        if self._accept("="):
            return Eq(term, self._parse_term())
        if self._accept("!="):
            return Not(Eq(term, self._parse_term()))

        if isinstance(term, Var):
            raise self._error("A variable cannot be used as an atomic formula.")
        return Pred(
            _encoded_name("pred", self._source_name(term.name)), term.args
        )

    def _parse_term(self):
        token = self.token
        if token.kind == "WORD" and self._is_variable_token(token):
            self.idx += 1
            if token.value == "_":
                self.anon_count += 1
                name = f"anonymous_{self.anon_count}"
            else:
                name = token.value
            return Var(_encoded_name("var", name))

        if token.kind not in {"WORD", "QUOTED", "DISTINCT", "NUMBER"}:
            raise self._error(f'Expected a term, found "{token.value}".')
        if token.kind == "WORD" and token.value.startswith("$"):
            raise UnsupportedTPTPFeature(
                "DEFINED_TERM",
                f'Defined term "{token.value}" is unsupported.'
            )
        if token.kind == "DISTINCT":
            raise UnsupportedTPTPFeature(
                "DISTINCT_OBJECT",
                "TPTP distinct objects are unsupported."
            )
        if token.kind == "NUMBER":
            raise UnsupportedTPTPFeature(
                "NUMERIC_TERM", "Interpreted numeric terms are unsupported."
            )

        self.idx += 1
        source_name = token.value
        args = ()
        if self.token.value == "(":
            args = self._parse_term_args()
        return Func(_encoded_name("func", source_name), args)

    def _parse_term_args(self):
        self._expect("(")
        args = []
        if self._accept(")"):
            return tuple(args)
        while True:
            args.append(self._parse_term())
            if self._accept(")"):
                break
            self._expect(",")
        return tuple(args)

    def _variable(self):
        token = self.token
        if not (token.kind == "WORD" and self._is_variable_token(token)):
            raise self._error(f'Expected a variable, found "{token.value}".')
        self.idx += 1
        name = token.value
        if name == "_":
            self.anon_count += 1
            name = f"anonymous_{self.anon_count}"
        return Var(_encoded_name("var", name))

    @staticmethod
    def _is_variable_token(token):
        value = token.value
        return value == "_" or (value and value[0].isupper())

    @staticmethod
    def _source_name(name):
        prefix = "tptp_func_"
        if not name.startswith(prefix):
            return name
        encoded = name[len(prefix):]
        try:
            return bytes.fromhex(encoded).decode("utf-8")
        except ValueError:
            return name

    @staticmethod
    def _binary(op, left, right):
        if op == "<=>":
            return Iff(left, right)
        if op == "<~>":
            return Not(Iff(left, right))
        if op == "=>":
            return Imp(left, right)
        if op == "<=":
            return Imp(right, left)
        if op == "|":
            return Or(left, right)
        if op == "~|":
            return Not(Or(left, right))
        if op == "&":
            return And(left, right)
        if op == "~&":
            return Not(And(left, right))
        raise AssertionError(op)

    def _skip_until_closing_paren(self):
        depth = 0
        while self.token.kind != "EOF":
            if self.token.value in {"(", "[", "{"}:
                depth += 1
            elif self.token.value in {")", "]", "}"}:
                if self.token.value == ")" and depth == 0:
                    self.idx += 1
                    return
                depth -= 1
            self.idx += 1
        raise self._error("Unterminated annotated formula.")

    def _expect_atom(self):
        token = self.token
        if token.kind not in {"WORD", "QUOTED", "DISTINCT", "NUMBER"}:
            raise self._error(f'Expected an atom, found "{token.value}".')
        self.idx += 1
        return token.value

    def _accept(self, value):
        if self.token.value != value:
            return False
        self.idx += 1
        return True

    def _expect(self, value):
        if not self._accept(value):
            raise self._error(f'Expected "{value}", found "{self.token.value}".')

    def _error(self, message):
        return TPTPError(f"{message} (character {self.token.pos})")


def parse_text(text, path="<string>"):
    # Deep source parentheses need more recursion than the balanced AST.
    old_limit = sys.getrecursionlimit()
    if old_limit >= _PARSE_RECURSION_LIMIT:
        return Parser(text).parse_file(path)

    try:
        sys.setrecursionlimit(_PARSE_RECURSION_LIMIT)
        return Parser(text).parse_file(path)
    finally:
        sys.setrecursionlimit(old_limit)


def parse_file(path):
    path = Path(path)
    return parse_text(path.read_text(encoding="utf-8", errors="replace"), path)


def universal_close(formula):
    variables = sorted(free_vars(formula), key=lambda var: var.name)
    for var in reversed(variables):
        formula = Forall(var, formula)
    return formula


def resolve_file(path, library_root=None, cache=None, stack=()):
    path = Path(path).resolve()
    root = Path(library_root).resolve() if library_root else path.parent
    cache = {} if cache is None else cache

    if path in stack:
        chain = " -> ".join(str(p) for p in stack + (path,))
        raise TPTPError(f"Cyclic include chain: {chain}")

    parsed = cache.get(path)
    if parsed is None:
        parsed = parse_file(path)
        cache[path] = parsed

    formulas = []
    next_stack = stack + (path,)
    for include in parsed.includes:
        include_path = _resolve_include(path, root, include.path)
        included = resolve_file(include_path, root, cache, next_stack)
        if include.names is not None:
            names = set(include.names)
            missing = names - {f.name for f in included}
            if missing:
                raise TPTPError(f"Unknown include selection: {sorted(missing)}")
            included = [f for f in included if f.name in names]
        formulas.extend(included)
    formulas.extend(parsed.formulas)
    return formulas


def _resolve_include(source_path, root, include_path):
    include = Path(include_path)
    candidates = []

    current = source_path.parent
    while True:
        candidates.append(current / include)
        if current == root or current.parent == current:
            break
        current = current.parent

    candidates.append(root / include)
    if include.parts and include.parts[0] == "$TPTP":
        candidates.append(root.joinpath(*include.parts[1:]))

    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate

    raise TPTPError(
        f'Could not resolve include "{include_path}" from "{source_path}".'
    )

