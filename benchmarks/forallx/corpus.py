from dataclasses import dataclass, field
import hashlib
from itertools import permutations
import json
from pathlib import Path
import re

from nd_prover import *

from ..common import file_hash
from ..proofs import restore_proof, serialize_proof
from .latex import group, parse_derivation, proof_payload, uncomment
from .statements import problem_statement


DIRECTORY = Path(__file__).resolve().parent
SOURCE = DIRECTORY / "problems.json"
SOURCE_MANIFEST = DIRECTORY / "source.json"
DEFAULT_SOURCE = DIRECTORY.parents[1] / "benchmark_data/forallx"
REPOSITORY = "https://github.com/rzach/forallx-yyc.git"
COMMIT = "bb86fe926ec3cd5d64255070c8f92ace8bf5cb7d"
EDITION = "Fall 2025 with official corrections through 2026-10-22"


@dataclass
class BenchmarkProblem:
    index: int
    case_id: str
    logic: str
    premises: list[str]
    conclusion: str
    chapter: str
    exercise: str
    references: list
    reference_index: int
    reference_constraints: list = field(default_factory=list)
    task_kind: str = "deduction"

    @property
    def reference(self):
        return self.references[self.reference_index]


def load_problems():
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    for filename, expected in manifest["artifacts"].items():
        if file_hash(DIRECTORY / filename) != expected:
            raise ValueError(f"Changed forall x: Calgary corpus artifact: {filename}.")
    specs = [BenchmarkProblem(**row) for row in json.loads(SOURCE.read_text(encoding="utf-8"))]
    for spec in specs:
        if uses_identity(spec.premises, spec.conclusion):
            raise ValueError(f"{spec.case_id}: identity is not supported by the proof generator.")
        if not spec.references or not all(ref["validated"] for ref in spec.references):
            raise ValueError(f"{spec.case_id}: no usable official reference.")
        if not 0 <= spec.reference_index < len(spec.references):
            raise ValueError(f"{spec.case_id}: invalid reference selection.")
    return specs


def uses_identity(premises, conclusion):
    return any("=" in text for text in [*premises, conclusion])


def verify_source(root):
    root = Path(root)
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        if text_hash(root / name) != expected:
            raise ValueError(f"Source checksum mismatch: {name}.")


def text_hash(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode()).hexdigest()


def reference_metrics(parsed):
    lines = parsed["lines"]
    rules = sorted({line["rule"] for line in lines} - {"PR", "AS", "?"})
    return {
        "proof_lines": len(lines),
        "generated_lines": sum(line["rule"] != "PR" for line in lines),
        "assumptions": sum(line["rule"] == "AS" for line in lines),
        "distinct_rules": len(rules), "rules": rules,
        "max_subproof_depth": parsed["max_subproof_depth"],
        "subproof_count": parsed["subproof_count"]
    }


def build_corpus(root):
    root = Path(root)
    main = uncomment((root / "solutions/forallxyyc-solutions.tex").read_text(encoding="utf-8"))
    includes = re.findall(r"\\include\{([^}]+)\}", main)
    files = ["solutions/forallxyyc-solutions.tex", "forallxyyc.sty", "fitch.sty", "LICENSE.md"]
    cases, coverage, chapter_number = [], [], 0
    current = None
    known_blocks = []
    for included in includes:
        relative = "solutions/" + included + ".tex"
        files.append(relative)
        raw_text = (root / relative).read_text(encoding="utf-8")
        text = uncomment(raw_text)
        events = re.compile(
            r"\\chapter\{|\\stepcounter\{chapter\}|\\problempart\b|\\begin\{fitchproof\}")
        position, part, title, proof_number, previous_end = 0, 0, "", 0, 0
        statement_context = ""
        for event in events.finditer(text):
            if event.start() < position:
                continue
            token = event[0]
            if token in {"\\chapter{", "\\problempart"} and current is not None and not current["context"]:
                current["context"] = text[current["_start"]:event.start()].strip()
            if token == "\\stepcounter{chapter}":
                chapter_number += 1
            elif token == "\\chapter{":
                chapter_number += 1
                title, _ = group(text, event.end() - 1)
                part, current = 0, None
            elif token == "\\problempart":
                part += 1
                exercise = f"{chapter_number}{chr(64 + part)}"
                current = {
                    "exercise": exercise, "chapter": title, "source_file": relative,
                    "source_line": text.count("\n", 0, event.start()) + 1,
                    "proofs": [], "context": "", "_start": event.end(),
                    "scope": "natural_deduction" if included.endswith(("prooftfl", "prooffol")) or title == "Natural deduction for ML" else "other"
                }
                coverage.append(current)
                previous_end = event.end()
                statement_context = ""
            else:
                end = text.find("\\end{fitchproof}", event.end())
                if end < 0 or current is None:
                    raise ValueError(f"Unassigned or unclosed proof in {relative}.")
                proof_number += 1
                position = end + len("\\end{fitchproof}")
                start = event.end()
                if start < len(text) and text[start] == "[":
                    _, start = group(text, start, "[", "]")
                raw = raw_text[start:end]
                context = text[previous_end:event.start()]
                if "\\item" in context or not statement_context:
                    statement_context = context
                if "\\item" in statement_context and current["exercise"] not in {"39B", "39C", "39D"}:
                    statement_context = statement_context[statement_context.rfind("\\item"):]
                if not current["context"]:
                    current["context"] = context.strip()
                previous_end = position
                location = {
                    "source_file": relative,
                    "source_line": text.count("\n", 0, event.start()) + 1,
                    "source_proof": proof_number, "exercise": current["exercise"]
                }
                entry = {**location, "status": "included"}
                current["proofs"].append(entry)
                if part == 1 and title in {"Basic rules for TFL", "Basic rules for FOL"}:
                    entry.update(status="excluded",
                                 reason="Intentionally incorrect proof for diagnosis.")
                    continue
                if included.endswith("prooftfl") and "\\have[m]" in raw and title == "Proof-theoretic concepts":
                    entry.update(
                        status="excluded", reason="Metatheoretic sketch with unspecified intermediate derivations.")
                    continue
                if included.endswith("ml"):
                    logic = {1: "K", 2: "K", 3: "K", 4: "T", 5: "S4", 6: "S5"}[part]
                else:
                    logic = "FOL" if included.endswith("prooffol") else "TFL"
                ref = make_reference(raw, statement_context, location, logic, title)
                ref["reference_constraints"] = [
                    "no_modal_conversion"] if logic == "K" and part == 2 else []
                if title == "Derived rules":
                    ref["reference_constraints"].append("no_DeM" if logic == "TFL" else "no_CQ")
                ref["task_kind"] = "derived_rule_justification" if title == "Derived rules" else "deduction"
                known_blocks.append((relative, proof_number, raw, context, location, logic, title))
                add_reference(cases, ref, title, entry)
        if current is not None and not current["context"]:
            current["context"] = text[current["_start"]:].strip()
    add_recipes(cases, coverage, known_blocks, root)
    for part in coverage:
        part.pop("_start")
        part["context"] = part["context"][:350]
        if not part["proofs"]:
            part["status"] = "no_formal_reference" if part["scope"] == "natural_deduction" else "outside_scope"
        else:
            part["status"] = "inventoried"
    by_id = {case["case_id"]: case for case in cases}
    for part in coverage:
        for entry in part["proofs"]:
            if "case_id" not in entry:
                continue
            case = by_id[entry["case_id"]]
            ref = next(ref for ref in case["references"] if (
                ref["source_proof"] == entry.get("source_proof", entry.get("base_source_proof"))
                and ref.get("recipe", {}).get("name") == entry.get("name")))
            identity = uses_identity(case["premises"], case["conclusion"])
            if identity:
                entry["unsupported_features"] = ["identity"]
            if not ref["validated"]:
                entry.update(status="excluded", reason="Unresolved official reference.", reference=ref)
            elif identity:
                entry.update(status="excluded", reason="Identity is not supported by the proof generator.", reference=ref)
    cases = [{**case, "references": [ref for ref in case["references"] if ref["validated"]]}
             for case in cases if not uses_identity(case["premises"], case["conclusion"])
             and any(ref["validated"] for ref in case["references"])]
    for index, case in enumerate(cases, 1):
        case["index"] = index
        case["reference_index"] = min(range(len(case["references"])), key=lambda i: (
            case["references"][i]["metrics"]["proof_lines"],
            case["references"][i]["metrics"]["max_subproof_depth"]
        ))
    manifest = {
        "repository": REPOSITORY, "commit": COMMIT,
        "edition": EDITION, "license": "CC BY 4.0",
        "corrections_commit": "bdd076cb13ebac1aaa3a5e9ac14c90f6e1b02d0c",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "hash_format": "SHA-256 of UTF-8 source with LF line endings",
        "files": {name: text_hash(root / name) for name in sorted(files)}
    }
    return json.loads(json.dumps(cases)), json.loads(json.dumps(coverage)), manifest


def make_reference(raw, context, location, logic, chapter):
    parsed = parse_derivation(raw)
    lines = parsed["lines"]
    proof_premises = [line["formula"] for line in lines if line["rule"] == "PR"]
    premises, goal, basis, statement = problem_statement(
        context, location["exercise"], proof_premises, lines[-1]["formula"])
    if not goal or any(p is None for p in premises):
        raise ValueError(f"Unparseable problem statement at {location}.")
    errors = list(parsed["parse_errors"])
    if proof_premises != premises:
        errors.append("The official root premises differ from the stated premises.")
    payload = proof_payload(lines, len(premises))
    spec = BenchmarkProblem(0, "", logic, premises, goal, chapter, location["exercise"], [], 0)
    if not errors:
        try:
            problem = restore_proof(spec, payload, True, validate=False)
            normalize_citations(problem.proof)
            errors.extend(problem.errors())
            if not problem.conclusion_reached():
                errors.append("The official final line differs from the stated conclusion.")
            payload = serialize_proof(problem.proof)
        except (ValueError, InferenceError, ParsingError, KeyError, TypeError) as exc:
            errors.append(f"Proof check: {type(exc).__name__}: {exc}")
    return {
        **location, "logic": logic, "premises": premises, "conclusion": goal,
        "source_tex": raw, "lines": lines, "proof": payload,
        "metrics": reference_metrics(parsed), "validated": not errors,
        "validation_errors": errors, "schematic": "\\metav" in raw,
        "statement_basis": basis, "statement_tex": statement
    }


def normalize_citations(proof):
    for line in proof.seq:
        if not line.is_line():
            normalize_citations(line)
            continue
        rule = line.justification.rule
        if rule is Rules.AS:
            continue
        citations = line.justification.citations
        if rule.name == "∧I" and len(citations) == 1:
            citations = citations * 2
        for candidate in permutations(citations):
            try:
                full_scope = proof.strict_context is None or rule.name in Rules.strict
                premises = proof.retrieve_cited_at(candidate, line.idx, full_scope)
                scope = proof.partition_scope_at(candidate, line.idx)
                if proof.match_schemas(line.formula, rule(premises, conclusion=line.formula, scope=scope)):
                    line.justification = Justification(rule, candidate)
                    break
            except InferenceError:
                pass


def add_reference(cases, ref, chapter, entry):
    key = (ref["exercise"], ref["logic"], ref["premises"], ref["conclusion"])
    case = next((case for case in cases if (
        case["exercise"], case["logic"], case["premises"], case["conclusion"]
    ) == key), None)
    if case is None:
        number = 1 + sum(case["exercise"] == ref["exercise"] for case in cases)
        case = {
            "index": 0, "case_id": f'forallx:{ref["exercise"]}:{number}',
            "logic": ref["logic"], "premises": ref["premises"],
            "conclusion": ref["conclusion"], "chapter": chapter,
            "exercise": ref["exercise"], "references": [], "reference_index": 0,
            "reference_constraints": ref.get("reference_constraints", []),
            "task_kind": ref.get("task_kind", "deduction")
        }
        cases.append(case)
    case["references"].append(ref)
    entry["case_id"] = case["case_id"]


def add_recipes(cases, coverage, blocks, root):
    recipes = [
        ("Celerant", "Barbara", r"\atom{F}", r"\enot \atom{F}"),
        ("Darii", "Ferio", r"\enot \atom{F}", r"\atom{F}"),
        ("Celaront", "Barbari", r"\atom{F}", r"\enot \atom{F}"),
        ("Darapti", "Felapton", r"\enot \atom{F}", r"\atom{F}")
    ]
    for name, base, old, new in recipes:
        source = next(block for block in blocks if re.search(
            r"\\textbf\{" + base + r"\.?\}", block[3]))
        relative, number, raw, context, location, logic, chapter = source
        text = (root / relative).read_text(encoding="utf-8")
        instruction = re.search(r"\\textbf\{" + name + r"\.?\}", text)
        if instruction is None:
            raise ValueError(f"Missing substitution instruction for {name}.")
        source_line = text.count("\n", 0, instruction.start()) + 1
        expanded = raw.replace(old, new)
        if name in {"Celaront", "Darapti"}:
            end = text.find("\\item", instruction.end())
            recipe_context = text[instruction.start():end if end != -1 else len(text)]
            recipe_context = "\\item " + recipe_context
        else:
            recipe_context = ""
        ref = make_reference(expanded, recipe_context, location, logic, chapter)
        ref["recipe"] = {
            "name": name, "base": base, "replace": old, "with": new,
            "source_file": relative, "source_line": source_line
        }
        entry = {
            "status": "included_recipe", "name": name,
            "base_source_proof": number, "source_line": source_line
        }
        part = next(part for part in coverage if part["exercise"] == location["exercise"])
        part["proofs"].append(entry)
        add_reference(cases, ref, chapter, entry)


def write_corpus(root, destination=DIRECTORY):
    cases, coverage, manifest = build_corpus(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in (("problems.json", cases), ("coverage.json", coverage)):
        (destination / name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    manifest["artifacts"] = {
        name: file_hash(destination / name) for name in ("problems.json", "coverage.json")
    }
    (destination / "source.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return cases, coverage

