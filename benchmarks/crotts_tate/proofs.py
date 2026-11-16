import time

from nd_prover import *

from ..proofs import (
    make_problem, proof_lines, count_proof, serialize_proof, restore_proof
)
from .corpus import SOURCE_ISSUES


def empty_result(spec):
    return {
        "index": spec.index, "logic": spec.logic, "raw_problem": spec.raw,
        "premises": spec.premises, "conclusion": spec.conclusion,
        "source_issue": SOURCE_ISSUES.get(spec.index),
        "status": "failure", "success": False,
        "elapsed_ms": 0.0, "cpu_ms": 0.0,
        "proof_lines": 0, "generated_lines": 0, "assumptions": 0,
        "distinct_rules": 0, "distinct_rules_with_assumptions": 0,
        "rules": [], "stages": [], "error": None,
        "proof": None, "proof_text": "", "hard_timeout": False
    }


def run_one(spec, settings):
    row = empty_result(spec)
    start, cpu_start = time.perf_counter(), time.process_time()
    result = None
    try:
        problem = make_problem(spec, settings["derived_rules"])
    except (InferenceError, ParsingError) as exc:
        row.update(status="input_error", error=f"{type(exc).__name__}: {exc}")
    else:
        modes = {
            "exhaustive": (True,), "fast": (False,), "staged": (True, False)
        }
        try:
            for exhaustive in modes[settings["mode"]]:
                stage_start = time.perf_counter()
                result = prove(
                    problem.logic, problem.premises, problem.conclusion,
                    derived_rules=settings["derived_rules"],
                    exhaustive=exhaustive, timeout=settings["timeout_ms"]
                )
                row["stages"].append({
                    "mode": "exhaustive" if exhaustive else "fast",
                    "status": result.status,
                    "elapsed_ms": (time.perf_counter() - stage_start) * 1000
                })
                if result.status == "success":
                    break
            row["status"] = result.status
        except Exception as exc:
            row.update(status="error", error=f"{type(exc).__name__}: {exc}")
    row["elapsed_ms"] = (time.perf_counter() - start) * 1000
    row["cpu_ms"] = (time.process_time() - cpu_start) * 1000
    if row["status"] == "success":
        row.update(count_proof(result.problem))
        row.update(
            success=True, proof=serialize_proof(result.problem.proof),
            proof_text=result.problem.to_plain_text()
        )
    return row

