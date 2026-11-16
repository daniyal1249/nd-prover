import csv
import json
import math
from pathlib import Path
import statistics


def load_results(path):
    records = []
    for line_no, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"Expected a JSON object at line {line_no} of {path}.")
            records.append(record)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSONL record at line {line_no} of {path}."
            ) from exc
    return records


def write_csv(records, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return

    fields = sorted(set().union(*(record.keys() for record in records)))
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def summarize(records, group_by=("library", "logic", "source_domain")):
    groups = {}
    for record in records:
        key = tuple(record.get(field) for field in group_by)
        groups.setdefault(key, []).append(record)

    summaries = []
    for key, group in sorted(groups.items(), key=lambda item: str(item[0])):
        elapsed = [r["elapsed_ms"] for r in group if "elapsed_ms" in r]
        cpu = [r["cpu_ms"] for r in group if "cpu_ms" in r]
        solved = [r for r in group if r.get("status") in {"valid", "invalid"}]
        solved_elapsed = [r["elapsed_ms"] for r in solved]
        solved_cpu = [r["cpu_ms"] for r in solved if "cpu_ms" in r]
        expected = [r for r in group if r.get("expected_status") is not None]
        expected_solved = [
            r for r in expected if r.get("status") in {"valid", "invalid"}
        ]
        correct = [r for r in expected_solved if r["status"] == r["expected_status"]]
        mismatches = [
            r for r in expected_solved if r["status"] != r["expected_status"]
        ]
        summary = {
            field: value for field, value in zip(group_by, key)
        }
        summary.update({
            "cases": len(group),
            "solved": len(solved),
            "valid": _count(group, "valid"),
            "invalid": _count(group, "invalid"),
            "unknown": _count(group, "unknown"),
            "error": _count(group, "error"),
            "hard_timeouts": sum(bool(r.get("hard_timeout")) for r in group),
            "unlabeled_solved": len(solved) - len(expected_solved),
            "expected_cases": len(expected),
            "expected_solved": len(expected_solved),
            "expected_matches": len(correct),
            "expected_mismatches": len(mismatches),
            "mean_ms": _mean(elapsed),
            "median_ms": _median(elapsed),
            "p95_ms": _percentile(elapsed, 0.95),
            "mean_cpu_ms": _mean(cpu),
            "median_cpu_ms": _median(cpu),
            "p95_cpu_ms": _percentile(cpu, 0.95),
            "solved_mean_ms": _mean(solved_elapsed),
            "solved_median_ms": _median(solved_elapsed),
            "solved_p95_ms": _percentile(solved_elapsed, 0.95),
            "solved_mean_cpu_ms": _mean(solved_cpu)
        })
        summaries.append(summary)
    return summaries


def print_summary(summaries, group_by=("library", "logic", "source_domain")):
    for summary in summaries:
        label = ", ".join(
            f"{key}={summary.get(key)}"
            for key in group_by
            if summary.get(key) is not None
        )
        print(label or "all")
        print(
            f"  cases={summary['cases']} solved={summary['solved']} "
            f"valid={summary['valid']} invalid={summary['invalid']} "
            f"unknown={summary['unknown']} error={summary['error']}"
        )
        print(f"  watchdog timeouts={summary['hard_timeouts']}")
        print(
            f"  gold={summary['expected_cases']} "
            f"solved={summary['expected_solved']} "
            f"correct={summary['expected_matches']} "
            f"disagreements={summary['expected_mismatches']} "
            f"unlabeled solved={summary['unlabeled_solved']}"
        )
        print(
            f"  gold solve rate="
            f"{_ratio(summary['expected_solved'], summary['expected_cases'])} "
            f"answered correctness="
            f"{_ratio(summary['expected_matches'], summary['expected_solved'])}"
        )
        print(
            f"  solved wall mean={_fmt(summary['solved_mean_ms'])} ms "
            f"median={_fmt(summary['solved_median_ms'])} ms "
            f"p95={_fmt(summary['solved_p95_ms'])} ms "
            f"cpu mean={_fmt(summary['solved_mean_cpu_ms'])} ms"
        )
        print(
            f"  all wall mean={_fmt(summary['mean_ms'])} ms "
            f"median={_fmt(summary['median_ms'])} ms "
            f"p95={_fmt(summary['p95_ms'])} ms"
        )


def _count(records, status):
    return sum(record.get("status") == status for record in records)


def _mean(values):
    return statistics.fmean(values) if values else None


def _median(values):
    return statistics.median(values) if values else None


def _percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    idx = max(0, min(len(values) - 1, math.ceil(len(values) * fraction) - 1))
    return values[idx]


def _ratio(numerator, denominator):
    if not denominator:
        return "-"
    return f"{100 * numerator / denominator:.1f}%"


def _fmt(value):
    return "-" if value is None else f"{value:.1f}"

def validate_record(record, metadata=None):
    required = {
        "case_id", "problem_id", "logic", "library", "library_version",
        "status", "timeout_ms",
        "elapsed_ms", "source_status", "expected_status", "matches_expected"
    }
    if not required <= record.keys():
        raise ValueError(f"Missing result fields: {sorted(required - record.keys())}.")
    case_id = record["case_id"]
    metadata = metadata or {}
    if "library" in metadata and record["library"] != metadata["library"]:
        raise ValueError(f"{case_id}: library differs from metadata.")
    if "library_versions" in metadata and (
        record["library_version"] not in metadata["library_versions"]
    ):
        raise ValueError(f"{case_id}: library version differs from metadata.")
    if record["status"] not in {"valid", "invalid", "unknown", "error"}:
        raise ValueError(f"{case_id}: unknown result status.")
    if "timeout_ms" in metadata and record["timeout_ms"] != metadata["timeout_ms"]:
        raise ValueError(f"{case_id}: timeout differs from metadata.")
    for field in ("elapsed_ms", "cpu_ms"):
        if field in record and (
            not math.isfinite(record[field]) or record[field] < 0
        ):
            raise ValueError(f"{case_id}: invalid {field}.")
    if record.get("hard_timeout") and record["status"] != "unknown":
        raise ValueError(f"{case_id}: watchdog result must be unknown.")
    if record.get("hard_timeout"):
        if "cpu_ms" in record:
            raise ValueError(f"{case_id}: watchdog result cannot measure CPU time.")
        if metadata.get("hard_timeout_ms", record.get("hard_timeout_ms")) != record.get(
            "hard_timeout_ms"
        ):
            raise ValueError(f"{case_id}: watchdog budget differs from metadata.")
    if (record["status"] == "error") != bool(record.get("error")):
        raise ValueError(f"{case_id}: inconsistent error field.")
    expected = None if record.get("exclude_from_gold") else {
        "Theorem": "valid", "Non-Theorem": "invalid"
    }.get(record["source_status"])
    if record["expected_status"] != expected:
        raise ValueError(f"{case_id}: incorrect gold label.")
    match = None
    if expected is not None and record["status"] in {"valid", "invalid"}:
        match = record["status"] == expected
    if record["matches_expected"] is not match:
        raise ValueError(f"{case_id}: incorrect gold comparison.")

