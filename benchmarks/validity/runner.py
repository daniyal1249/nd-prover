import json
from pathlib import Path
import time

from nd_prover import *

from ..common import repair_jsonl as _remove_partial_tail
from ..worker import Worker, WorkerError, WorkerTimeout

from .metrics import problem_metrics
from .report import load_results, validate_record


_HARD_TIMEOUT_GRACE_MS = 2000


def run_cases(
    cases,
    output_path,
    timeout_ms,
    resume=True,
    progress=True,
    hard_timeout_ms=None
):
    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be positive.")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if resume:
        _remove_partial_tail(output_path)
    completed = _completed_cases(output_path, timeout_ms) if resume else set()
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Duplicate case IDs in benchmark inputs.")
    if completed - set(case_ids):
        raise ValueError("Results contain cases outside the requested case set.")

    if hard_timeout_ms is None:
        hard_timeout_ms = timeout_ms + _HARD_TIMEOUT_GRACE_MS
    if hard_timeout_ms < timeout_ms:
        raise ValueError("hard_timeout_ms must be at least timeout_ms.")

    total = len(cases)
    mode = "a" if resume else "w"
    worker = _CaseWorker()
    finished = set(completed)
    try:
        with output_path.open(mode, encoding="utf-8") as output:
            for idx, case in enumerate(cases, 1):
                if case.case_id in completed:
                    continue

                if progress:
                    print(
                        f"[{idx}/{total}] START {case.case_id}",
                        flush=True
                    )

                result = worker.run(case, timeout_ms, hard_timeout_ms)
                output.write(json.dumps(result, sort_keys=True) + "\n")
                output.flush()
                finished.add(case.case_id)

                if progress:
                    status = result["status"]
                    elapsed = result["elapsed_ms"]
                    suffix = " [hard timeout]" if result.get(
                        "hard_timeout"
                    ) else ""
                    print(
                        f"[{idx}/{total}] DONE  {case.case_id}: "
                        f"{status} ({elapsed:.1f} ms){suffix}",
                        flush=True
                    )
    except KeyboardInterrupt:
        print(
            "\nInterrupted. Completed JSONL records are safely saved.",
            flush=True
        )
    finally:
        worker.close()
    return len(finished) == total


def run_case(case, timeout_ms):
    record = _base_record(case, timeout_ms)

    start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        problem = case.problem
        result = check_validity(
            problem.logic,
            problem.premises,
            problem.conclusion,
            problem.domain_semantics,
            problem.equality_semantics,
            countermodel=False,
            small=False,
            timeout=timeout_ms
        )
        record["status"] = result.status
        record["error"] = None
    except Exception as exc:
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["elapsed_ms"] = (time.perf_counter() - start) * 1000
    record["cpu_ms"] = (time.process_time() - cpu_start) * 1000
    record["hard_timeout"] = False

    _set_expected_match(record)
    return record


class _CaseWorker(Worker):

    def __init__(self):
        super().__init__(run_case)

    def run(self, case, timeout_ms, hard_timeout_ms):
        try:
            return super().run((case, timeout_ms), hard_timeout_ms)
        except WorkerTimeout as exc:
            return _hard_timeout_record(
                case, timeout_ms, hard_timeout_ms, exc.elapsed_ms
            )
        except WorkerError as exc:
            return _worker_error_record(case, timeout_ms, str(exc), exc.elapsed_ms)


def _base_record(case, timeout_ms):
    problem = case.problem
    return {
        "case_id": case.case_id,
        "library": case.library,
        "library_version": case.version,
        "problem_id": case.problem_id,
        "source_path": str(case.source_path),
        "logic": problem.logic.__name__,
        "domain_semantics": problem.domain_semantics,
        "equality_semantics": problem.equality_semantics,
        "source_logic": case.source_logic,
        "source_domain": case.source_domain,
        "source_status": case.source_status,
        "source_rating": case.source_rating,
        "expected_status": case.expected_status,
        "timeout_ms": timeout_ms,
        **case.metadata,
        **problem_metrics(problem)
    }


def _hard_timeout_record(case, timeout_ms, hard_timeout_ms, elapsed_ms):
    record = _base_record(case, timeout_ms)
    record.update({
        "status": "unknown",
        "error": None,
        "elapsed_ms": elapsed_ms,
        "hard_timeout": True,
        "hard_timeout_ms": hard_timeout_ms,
        "matches_expected": None
    })
    return record


def _worker_error_record(case, timeout_ms, detail, elapsed_ms):
    record = _base_record(case, timeout_ms)
    record.update({
        "status": "error",
        "error": f"WorkerError: {detail}",
        "elapsed_ms": elapsed_ms,
        "hard_timeout": False,
        "matches_expected": None
    })
    return record


def _set_expected_match(record):
    expected = record["expected_status"]
    if expected is None or record["status"] not in {"valid", "invalid"}:
        record["matches_expected"] = None
    else:
        record["matches_expected"] = record["status"] == expected


def write_skips(path, skipped):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for skip in skipped:
            record = {
                "library": skip.library,
                "problem_id": skip.problem_id,
                "source_path": str(skip.source_path),
                "reason": skip.reason,
                "detail": skip.detail
            }
            output.write(json.dumps(record, sort_keys=True) + "\n")


def _completed_cases(path, timeout_ms=None):
    path = Path(path)
    if not path.exists():
        return set()

    records = load_results(path)
    for record in records:
        metadata = {"timeout_ms": timeout_ms} if timeout_ms is not None else None
        validate_record(record, metadata)
    case_ids = [record["case_id"] for record in records]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Duplicate case IDs in saved results.")
    return set(case_ids)

