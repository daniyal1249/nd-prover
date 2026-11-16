import hashlib
import json
from pathlib import Path
import platform
import subprocess

import cvc5

from nd_prover import __version__


ROOT = Path(__file__).resolve().parents[1]


def source_paths(suite):
    return sorted([
        *ROOT.joinpath("nd_prover").glob("*.py"),
        *ROOT.joinpath("benchmarks").glob("*.py"),
        *ROOT.joinpath("benchmarks", suite).glob("*.py")
    ])


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def implementation_hash(suite):
    digest = hashlib.sha256()
    paths = source_paths(suite)
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_text(encoding="utf-8").encode())
    return digest.hexdigest()


def environment_metadata(suite):
    return {
        "ndprover_version": __version__,
        "cvc5_version": cvc5.__version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "git_commit": _git_commit(),
        "implementation_sha256": implementation_hash(suite)
    }


def _git_commit():
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=2, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def repair_jsonl(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return

    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    if not lines:
        return

    last = lines[-1]
    if not last.strip():
        return

    try:
        json.loads(last.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        if last.endswith((b"\n", b"\r")):
            raise ValueError("Invalid complete JSONL record at end of results.")
        path.write_bytes(b"".join(lines[:-1]))
        return

    if not data.endswith((b"\n", b"\r")):
        path.write_bytes(data + b"\n")

