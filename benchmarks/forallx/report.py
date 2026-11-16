import csv
import json
import math
from pathlib import Path
import statistics

from ..proofs import count_proof, proof_shape, restore_proof


METRICS = ("proof_lines", "generated_lines", "assumptions", "distinct_rules",
           "max_subproof_depth", "subproof_count")


def load_results(path):
    rows = [json.loads(line) for line in Path(path).read_text(
        encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Expected one result object per JSONL line.")
    return rows


def audit_results(rows, metadata, specs, complete=True):
    by_id = {spec.case_id: spec for spec in specs}
    expected = metadata["case_ids"]
    ids = [row["case_id"] for row in rows]
    if len(set(ids)) != len(ids) or not set(ids) <= set(expected):
        raise ValueError("Duplicate or unexpected cases in results.")
    if not set(expected) <= set(by_id) or len(set(expected)) != len(expected):
        raise ValueError("Unknown or duplicate cases in run metadata.")
    if complete and set(ids) != set(expected):
        raise ValueError("The benchmark run is incomplete.")
    modes = {"staged": ["exhaustive", "fast"], "exhaustive": [
        "exhaustive"], "fast": ["fast"]}[metadata["mode"]]
    for row in rows:
        spec = by_id[row["case_id"]]
        for key in ("index", "logic", "premises", "conclusion", "exercise", "chapter", "task_kind", "reference_constraints"):
            if row[key] != getattr(spec, key):
                raise ValueError(f'{spec.case_id}: saved {key} differs from the corpus.')
        if not spec.reference["validated"] or row["reference_validated"] is not True:
            raise ValueError(f"{spec.case_id}: no checked official reference.")
        if row["reference_metrics"] != spec.reference["metrics"] or row["reference_index"] != spec.reference_index:
            raise ValueError(f"{spec.case_id}: official reference differs.")
        if row["status"] not in {"success", "failure", "timeout", "input_error", "error"}:
            raise ValueError("Unknown result status.")
        if row["success"] is not (row["status"] == "success"):
            raise ValueError("Inconsistent success flag.")
        if not isinstance(row["hard_timeout"], bool) or (row["hard_timeout"] and row["status"] != "timeout"):
            raise ValueError("Inconsistent watchdog timeout.")
        for key in ("elapsed_ms", "cpu_ms"):
            if key == "cpu_ms" and row[key] is None and (row["hard_timeout"] or row["status"] == "error"):
                continue
            if not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError("Invalid timing measurement.")
        if bool(row["error"]) != (row["status"] in {"input_error", "error"} or row["hard_timeout"]):
            raise ValueError("Inconsistent error diagnostic.")
        stages = row["stages"]
        if [stage["mode"] for stage in stages] != modes[:len(stages)]:
            raise ValueError("Incorrect search-stage order.")
        if any(stage["status"] not in {"success", "failure", "timeout"} or not math.isfinite(stage["elapsed_ms"]) or stage["elapsed_ms"] < 0 for stage in stages):
            raise ValueError("Invalid search-stage measurement.")
        if any(stage["status"] == "success" for stage in stages[:-1]):
            raise ValueError("Search continued after success.")
        if sum(stage["elapsed_ms"] for stage in stages) > row["elapsed_ms"] + .001:
            raise ValueError("Stage times exceed the case time.")
        if stages and (row["hard_timeout"] or row["status"] == "input_error"):
            raise ValueError("Unexpected stages for a pre-search error or watchdog timeout.")
        if row["status"] in {"success", "failure", "timeout"} and not row["hard_timeout"]:
            if not stages or stages[-1]["status"] != row["status"]:
                raise ValueError("Missing or inconsistent final stage.")
            if not row["success"] and len(stages) != len(modes):
                raise ValueError("Missing fallback stage.")
        if row["success"]:
            problem = restore_proof(spec, row["proof"], metadata["derived_rules"])
            if row["metrics"] != {**count_proof(problem), **proof_shape(problem)}:
                raise ValueError("Saved proof metrics differ from its derivation.")
            if row["proof_text"] != problem.to_plain_text():
                raise ValueError("Saved proof text differs.")
        elif row["proof"] is not None or row["proof_text"] or row["metrics"] is not None:
            raise ValueError("An unsuccessful case has a proof.")
    return summarize(rows)


def meets_rule_constraints(row):
    if not row["success"]:
        return None
    used = set(row["metrics"]["rules"])
    restrictions = {"no_modal_conversion": "MC", "no_DeM": "DeM", "no_CQ": "CQ"}
    forbidden = {restrictions[name] for name in row["reference_constraints"]}
    return not used & forbidden


def summarize(rows):
    groups = []
    for logic in ["all", *sorted({row["logic"] for row in rows})]:
        selected = [row for row in rows if logic == "all" or row["logic"] == logic]
        if not selected:
            continue
        solved = [row for row in selected if row["success"]]

        def mean(values):
            return statistics.fmean(values) if values else None

        comparison = {"pairs": len(solved)}
        for field in METRICS:
            differences = [row["metrics"][field] - row["reference_metrics"][field]
                           for row in solved]
            comparison[field] = {
                "generated_mean": mean([row["metrics"][field] for row in solved]),
                "official_mean": mean([row["reference_metrics"][field] for row in solved]),
                "mean_difference": mean(differences),
                "lower": sum(difference < 0 for difference in differences),
                "equal": sum(difference == 0 for difference in differences),
                "higher": sum(difference > 0 for difference in differences)
            }
        comparison["median_line_ratio"] = statistics.median([
            row["metrics"]["proof_lines"] / row["reference_metrics"]["proof_lines"] for row in solved
        ]) if solved else None
        groups.append({
            "group": logic, "cases": len(selected), "solved": len(solved),
            "success_percent": 100 * len(solved) / len(selected),
            "total_case_seconds": sum(row["elapsed_ms"] for row in selected) / 1000,
            "failures": sum(row["status"] == "failure" for row in selected),
            "timeouts": sum(row["status"] == "timeout" for row in selected),
            "input_errors": sum(row["status"] == "input_error" for row in selected),
            "errors": sum(row["status"] == "error" for row in selected),
            "rule_constraints_met_solved": sum(meets_rule_constraints(row) is True for row in solved),
            "comparison": comparison
        })
    return groups


def print_summary(groups):
    for group in groups:
        pairs = group["comparison"]
        lines = pairs["proof_lines"]
        depth = pairs["max_subproof_depth"]
        print(
            f'{group["group"]}: {group["solved"]}/{group["cases"]} '
            f'({group["success_percent"]:.2f}%), {group["total_case_seconds"]:.3f} s'
        )
        if pairs["pairs"]:
            print(
                f'  Reference pairs: {pairs["pairs"]}; mean lines generated/official: '
                f'{lines["generated_mean"]:.2f}/{lines["official_mean"]:.2f}; '
                f'mean depth: {depth["generated_mean"]:.2f}/{depth["official_mean"]:.2f}'
            )


def write_csv(rows, path):
    output = []
    for row in rows:
        entry = {key: row[key] for key in (
            "case_id", "exercise", "chapter", "logic", "status", "elapsed_ms",
            "cpu_ms", "reference_index", "task_kind"
        )}
        entry["reference_rule_constraints_met"] = meets_rule_constraints(row)
        for field in METRICS:
            entry["official_" + field] = row["reference_metrics"][field]
            entry["generated_" + field] = row["metrics"][field] if row["success"] else None
            entry[field + "_difference"] = row["metrics"][field] - \
                row["reference_metrics"][field] if row["success"] else None
        output.append(entry)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0]) if output else ["case_id"])
        writer.writeheader()
        writer.writerows(output)

