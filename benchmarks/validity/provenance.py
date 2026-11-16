from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from nd_prover import *

from ..common import environment_metadata, file_hash


SCHEMA_VERSION = 2


def case_set_hash(case_ids):
    return hashlib.sha256("\n".join(sorted(case_ids)).encode()).hexdigest()


def input_hash(cases):
    digest = hashlib.sha256()
    cache = {}
    for case in sorted(cases, key=lambda item: item.case_id):
        problem = case.problem
        data = {
            "case_id": case.case_id,
            "version": case.version,
            "domain_semantics": problem.domain_semantics,
            "equality_semantics": problem.equality_semantics,
            "source_status": case.source_status,
            "source_rating": case.source_rating,
            "metadata": case.metadata,
            "formulas": [
                _syntax_hash(f, cache)
                for f in problem.premises + [problem.conclusion]
            ]
        }
        digest.update(json.dumps(data, sort_keys=True).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _syntax_hash(root, cache):
    key = id(root)
    if key in cache:
        return cache[key]
    digest = hashlib.sha256()
    stack = [root]
    while stack:
        item = stack.pop()
        if is_dataclass(item):
            digest.update(type(item).__name__.encode() + b":")
            stack.append(")")
            stack.extend(
                getattr(item, field.name) for field in reversed(fields(item))
            )
        elif isinstance(item, tuple):
            digest.update(b"[")
            stack.append("]")
            stack.extend(reversed(item))
        else:
            digest.update(json.dumps(item, ensure_ascii=True).encode() + b";")
    cache[key] = digest.hexdigest()
    return cache[key]


def run_metadata(timeout_ms, extra=None):
    translator = Translator(IPL, produce_models=False, small=False)
    produce_models = translator.solver.solver.getOption("produce-models")
    metadata = {
        "schema_version": SCHEMA_VERSION,
        **environment_metadata("validity"),
        "timeout_ms": timeout_ms,
        "small": False,
        "countermodel": False,
        "produce_models": produce_models == "true"
    }
    if extra:
        metadata.update(extra)
    return metadata


def write_run_metadata(path, timeout_ms, extra=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = run_metadata(timeout_ms, extra)
    metadata["created_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8"
    )


def validate_run_metadata(path, timeout_ms, extra=None):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Cannot resume: metadata file "{path}" is missing.')
    existing = json.loads(path.read_text(encoding="utf-8"))
    expected = run_metadata(timeout_ms, extra)
    mismatches = [key for key, value in expected.items() if existing.get(key) != value]
    if mismatches:
        raise ValueError(
            "Cannot resume with different run settings: "
            + ", ".join(mismatches)
            + ". Use another output path or --no-resume."
        )

