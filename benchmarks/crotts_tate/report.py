import csv
import json
import hashlib
import math
from dataclasses import asdict
from pathlib import Path
import statistics

from ..common import file_hash
from .corpus import SOURCE, load_problems
from .proofs import count_proof, restore_proof


DIRECTORY = Path(__file__).resolve().parent
GROUPS = {"all": None, "propositional": "TFL", "first_order": "FOL"}


def load_results(path):
    rows = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, 1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid result at line {number}.") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Expected an object at line {number}.")
            rows.append(row)
    return rows


def summarize(rows):
    groups = []
    for name, logic in GROUPS.items():
        group = [r for r in rows if logic is None or r["logic"] == logic]
        if not group:
            continue
        solved = [r for r in group if r["success"]]

        def mean(field, selected):
            return statistics.fmean(r[field] for r in selected) if selected else None

        groups.append({
            "group": name, "cases": len(group), "solved": len(solved),
            "success_percent": 100 * len(solved) / len(group),
            "mean_lines_all": mean("proof_lines", group),
            "mean_rules_all": mean("distinct_rules", group),
            "mean_lines_solved": mean("proof_lines", solved),
            "mean_rules_solved": mean("distinct_rules", solved),
            "mean_generated_lines_solved": mean("generated_lines", solved),
            "mean_ms_all": mean("elapsed_ms", group),
            "failures": sum(r["status"] == "failure" for r in group),
            "timeouts": sum(r["status"] == "timeout" for r in group),
            "input_errors": sum(r["status"] == "input_error" for r in group),
            "errors": sum(r["status"] == "error" for r in group)
        })
    return groups


def print_summary(groups):
    for group in groups:
        print(
            f'{group["group"]}: {group["solved"]}/{group["cases"]} '
            f'({group["success_percent"]:.2f}%), '
            f'mean lines={group["mean_lines_all"]:.2f}, '
            f'mean rules={group["mean_rules_all"]:.2f}'
        )


def write_csv(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(set().union(*(row.keys() for row in rows)))
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows({
            k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
            for k, v in row.items()
        } for row in rows)


def comparison_tables(groups):
    published = json.loads((DIRECTORY / "published_results.json").read_text())
    lookup = {group["group"]: group for group in groups}
    keys = ("all", "propositional", "first_order", "all")
    rows = []
    for (table, references), key in zip(published["tables"].items(), keys):
        for system, success, lines, rules in references:
            rows.append({
                "table": table, "system": system, "success_percent": success,
                "mean_lines": lines, "mean_distinct_rules": rules
            })
        group = lookup.get(key)
        if group is None:
            continue
        solved_only = table.startswith("Table 6")
        rows.append({
            "table": table, "system": "ND-Prover",
            "success_percent": (
                None if solved_only else round(group["success_percent"], 2)
            ),
            "mean_lines": group[
                "mean_lines_solved" if solved_only else "mean_lines_all"
            ],
            "mean_distinct_rules": group[
                "mean_rules_solved" if solved_only else "mean_rules_all"
            ]
        })
    return rows


def audit_results(rows, metadata, specs=None, complete=True):
    specs = load_problems(DIRECTORY / "problems.txt") if specs is None else specs
    by_index = {spec.index: spec for spec in specs}
    expected = set(metadata["indices"])
    selected = [by_index[index] for index in metadata["indices"]]
    digest = hashlib.sha256(json.dumps(
        [asdict(spec) for spec in selected], sort_keys=True
    ).encode()).hexdigest()
    if metadata["source_sha256"] != file_hash(SOURCE) or (
        metadata["input_sha256"] != digest
    ):
        raise ValueError("Source or translated inputs differ from run metadata.")
    if metadata["problem_count"] != len(expected) or len(selected) != len(expected):
        raise ValueError("Metadata problem counts are inconsistent.")
    indices = [row["index"] for row in rows]
    if len(indices) != len(set(indices)) or not set(indices) <= expected:
        raise ValueError("Duplicate or unexpected problem indices in results.")
    if complete and set(indices) != expected:
        raise ValueError("The proof benchmark run is incomplete.")
    for row in rows:
        spec = by_index[row["index"]]
        if (row["logic"], row["raw_problem"], row["premises"], row["conclusion"]) != (
            spec.logic, spec.raw, spec.premises, spec.conclusion
        ):
            raise ValueError(f'Problem {spec.index}: saved inputs differ.')
        if row["status"] not in {
            "success", "failure", "timeout", "input_error", "error"
        }:
            raise ValueError(f'Problem {spec.index}: invalid result status.')
        if row["success"] is not (row["status"] == "success"):
            raise ValueError(f'Problem {spec.index}: inconsistent success flag.')
        for field in ("elapsed_ms", "cpu_ms"):
            if field == "cpu_ms" and row[field] is None and (
                row["hard_timeout"] or row["status"] == "error"
            ):
                continue
            if not math.isfinite(row[field]) or row[field] < 0:
                raise ValueError(f'Problem {spec.index}: invalid timing measurement.')
        has_error = row["status"] in {"input_error", "error"} or row["hard_timeout"]
        if bool(row["error"]) != has_error:
            raise ValueError(f'Problem {spec.index}: inconsistent diagnostic field.')
        modes = {
            "staged": ["exhaustive", "fast"], "exhaustive": ["exhaustive"],
            "fast": ["fast"]
        }[metadata["mode"]]
        stages = row["stages"]
        if [s["mode"] for s in stages] != modes[:len(stages)]:
            raise ValueError(f'Problem {spec.index}: incorrect search stage order.')
        if any(
            s["status"] not in {"success", "failure", "timeout"}
            or not math.isfinite(s["elapsed_ms"]) or s["elapsed_ms"] < 0
            for s in stages
        ):
            raise ValueError(f'Problem {spec.index}: invalid search stage measurement.')
        if any(s["status"] == "success" for s in stages[:-1]):
            raise ValueError(f'Problem {spec.index}: search continued after success.')
        if sum(s["elapsed_ms"] for s in stages) > row["elapsed_ms"] + 0.001:
            raise ValueError(f'Problem {spec.index}: search stages exceed the case time.')
        if stages and (row["status"] == "input_error" or row["hard_timeout"]):
            raise ValueError(f'Problem {spec.index}: unexpected recorded search stages.')
        if row["status"] in {"success", "failure", "timeout"} and not (
            row["hard_timeout"]
        ):
            if not stages or stages[-1]["status"] != row["status"]:
                raise ValueError(f'Problem {spec.index}: final stage status differs.')
            if row["status"] != "success" and len(stages) != len(modes):
                raise ValueError(f'Problem {spec.index}: missing final search stage.')
        if row["success"]:
            problem = restore_proof(spec, row["proof"], metadata["derived_rules"])
            counts = count_proof(problem)
            if any(row[key] != value for key, value in counts.items()):
                raise ValueError(f'Problem {spec.index}: proof metrics do not match.')
            if row["proof_text"] != problem.to_plain_text():
                raise ValueError(f'Problem {spec.index}: saved proof text differs.')
        elif row["proof"] is not None or row["proof_text"] or row["rules"] or any(
            row[field] for field in (
                "proof_lines", "generated_lines", "assumptions", "distinct_rules",
                "distinct_rules_with_assumptions"
            )
        ):
            raise ValueError(f'Problem {spec.index}: unsuccessful result has a proof.')
    return summarize(rows)

