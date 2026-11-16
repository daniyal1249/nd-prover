import time

from nd_prover import *

from ..proofs import count_proof, make_problem, proof_shape, serialize_proof


def empty_result(spec):
    return {
        "index": spec.index, "case_id": spec.case_id, "logic": spec.logic,
        "premises": spec.premises, "conclusion": spec.conclusion,
        "exercise": spec.exercise, "chapter": spec.chapter,
        "status": "failure", "success": False, "elapsed_ms": 0.0,
        "cpu_ms": 0.0, "hard_timeout": False, "error": None,
        "stages": [], "proof": None, "proof_text": "", "metrics": None,
        "reference_metrics": spec.reference["metrics"],
        "reference_index": spec.reference_index,
        "reference_validated": spec.reference["validated"],
        "reference_constraints": spec.reference_constraints,
        "task_kind": spec.task_kind
    }


def run_one(spec, settings):
    row = empty_result(spec)
    wall, cpu = time.perf_counter(), time.process_time()
    try:
        problem = make_problem(spec, settings["derived_rules"])
    except (InferenceError, ParsingError) as exc:
        row.update(status="input_error", error=f"{type(exc).__name__}: {exc}")
    else:
        modes = {"staged": (True, False), "exhaustive": (True,), "fast": (False,)}
        try:
            for exhaustive in modes[settings["mode"]]:
                start = time.perf_counter()
                result = prove(
                    problem.logic, problem.premises, problem.conclusion,
                    derived_rules=settings["derived_rules"],
                    exhaustive=exhaustive, timeout=settings["timeout_ms"]
                )
                row["stages"].append({
                    "mode": "exhaustive" if exhaustive else "fast",
                    "status": result.status,
                    "elapsed_ms": (time.perf_counter() - start) * 1000
                })
                row["status"] = result.status
                if result.status == "success":
                    break
        except Exception as exc:
            row.update(status="error", error=f"{type(exc).__name__}: {exc}")
    row["elapsed_ms"] = (time.perf_counter() - wall) * 1000
    row["cpu_ms"] = (time.process_time() - cpu) * 1000
    if row["status"] == "success":
        row.update(
            success=True, metrics={**count_proof(result.problem), **proof_shape(result.problem)},
            proof=serialize_proof(result.problem.proof), proof_text=result.problem.to_plain_text()
        )
    return row

