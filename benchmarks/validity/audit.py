import hashlib
import json
from pathlib import Path

from .metrics import problem_metrics
from .provenance import case_set_hash, file_hash, input_hash
from .report import load_results, summarize, validate_record


DIRECTORY = Path(__file__).resolve().parent


def verify_data(root):
    root = Path(root)
    manifest = json.loads((DIRECTORY / "corpora.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = root / entry["name"]
        if path.suffix == ".gz" and not path.exists():
            continue
        if not path.is_file() or file_hash(path) != entry["sha256"]:
            raise ValueError(f'Corpus checksum mismatch: "{path}".')
    for entry in manifest["libraries"]:
        count, digest = tree_hash(root / entry["name"])
        if count != entry["file_count"] or digest != entry["sha256"]:
            raise ValueError(f'Corpus tree mismatch: "{entry["name"]}".')


def tree_hash(root):
    root = Path(root)
    digest = hashlib.sha256()
    paths = sorted(
        path for folder in ("Problems", "Axioms")
        for path in (root / folder).rglob("*") if path.is_file()
    )
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(file_hash(path).encode() + b"\n")
    return len(paths), digest.hexdigest()


def audit_run(path, cases=None, skipped=None):
    path = Path(path)
    records = load_results(path)
    metadata_path = path.with_suffix(".metadata.json")
    skips_path = path.with_suffix(".skips.jsonl")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    skips = load_results(skips_path)
    for record in records:
        validate_record(record, metadata)
    ids = [record["case_id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate case IDs: {path}.")
    if len(ids) != metadata["case_count"]:
        raise ValueError(f"Incomplete run: {path}.")
    if case_set_hash(ids) != metadata["case_set_sha256"]:
        raise ValueError(f"Case set mismatch: {path}.")
    if len(skips) != metadata["skipped_problem_count"]:
        raise ValueError(f"Skip count mismatch: {path}.")
    skip_ids = [(r["library"], r["problem_id"]) for r in skips]
    if len(skip_ids) != len(set(skip_ids)):
        raise ValueError(f"Duplicate skipped problems: {path}.")
    if {r["problem_id"] for r in records} & {r["problem_id"] for r in skips}:
        raise ValueError(f"Skipped problems also have results: {path}.")

    manifest_path = DIRECTORY / "results" / "manifest.json"
    archive = json.loads(manifest_path.read_text(encoding="utf-8"))
    archived = archive["files"].get(path.name)
    if archived:
        for candidate in (path, metadata_path, skips_path):
            if file_hash(candidate) != archive["files"][candidate.name]:
                raise ValueError(f"Archived artifact changed: {candidate}.")

    expected_cases = None if cases is None else {c.case_id: c for c in cases}
    if expected_cases is not None and metadata.get("schema_version") == 2:
        if not set(ids) <= set(expected_cases):
            raise ValueError(f"Results contain unknown imported cases: {path}.")
        selected = [expected_cases[case_id] for case_id in ids]
        if input_hash(selected) != metadata["input_sha256"]:
            raise ValueError(f"Parsed inputs differ from run metadata: {path}.")
        expected_cases = {c.case_id: c for c in selected}
    if expected_cases is not None and set(ids) != set(expected_cases):
        raise ValueError(f"Imported case set differs from saved results: {path}.")
    if skipped is not None:
        expected_skips = {(s.library, s.problem_id, s.reason) for s in skipped}
        actual_skips = {(s["library"], s["problem_id"], s["reason"]) for s in skips}
        if actual_skips != expected_skips:
            raise ValueError(f"Imported skip set differs from saved results: {path}.")

    for record in records:
        if expected_cases is not None:
            case = expected_cases[record["case_id"]]
            expected = {
                "logic": case.problem.logic.__name__,
                "domain_semantics": case.problem.domain_semantics,
                "equality_semantics": case.problem.equality_semantics,
                "source_logic": case.source_logic,
                "source_domain": case.source_domain,
                "source_status": case.source_status,
                "source_rating": case.source_rating,
                "expected_status": case.expected_status,
                **case.metadata,
                **problem_metrics(case.problem)
            }
            for key, value in expected.items():
                if record.get(key) != value:
                    raise ValueError(f'{record["case_id"]}: field "{key}" differs.')

    summary = summarize(records, ())[0]
    summary["path"] = str(path)
    summary["warnings"] = []
    if archived:
        summary["warnings"].append(
            "Legacy metadata: source hashes and the watchdog setting were not recorded."
        )
    for record in records:
        if record["matches_expected"] is False:
            note = (
                f'{record["case_id"]}: source={record["source_status"]}, '
                f'answer={record["status"]}.'
            )
            if record["case_id"] == "QMLTP:GSY374+1:QT:cumulative":
                note += " See the countermodel in benchmarks/validity/README.md."
            summary["warnings"].append(note)
    return summary

