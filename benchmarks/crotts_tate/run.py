import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from ..common import environment_metadata, file_hash, repair_jsonl
from ..worker import Worker, WorkerError, WorkerTimeout
from .corpus import SOURCE, load_problems, verify_source
from .proofs import empty_result, run_one
from .report import (
    DIRECTORY, audit_results, comparison_tables, load_results, print_summary,
    write_csv
)


def run_metadata(specs, settings):
    inputs = [asdict(spec) for spec in specs]
    return {
        "schema_version": 1, "suite": "Crotts-Tate 288",
        **environment_metadata("crotts_tate"), **settings,
        "source_sha256": file_hash(SOURCE),
        "input_sha256": hashlib.sha256(
            json.dumps(inputs, sort_keys=True).encode()
        ).hexdigest(),
        "indices": [spec.index for spec in specs], "problem_count": len(specs)
    }


def run_benchmark(specs, output, settings, resume=True):
    output = Path(output)
    metadata_path = output.with_suffix(".metadata.json")
    inputs_path = output.with_suffix(".inputs.json")
    summary_path = output.with_suffix(".summary.json")
    for path in (output, metadata_path, inputs_path, summary_path):
        _writable(path)
    metadata = run_metadata(specs, settings)
    output.parent.mkdir(parents=True, exist_ok=True)
    if resume and output.exists():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        if any(existing.get(key) != value for key, value in metadata.items()):
            raise ValueError("Code or settings changed. Choose another output path.")
        _verify_inputs(output, existing, specs)
        repair_jsonl(output)
        rows = load_results(output)
        audit_results(rows, existing, specs, complete=False)
    else:
        rows = []
        metadata["created_at"] = datetime.now(timezone.utc).isoformat()
        metadata_path.write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        inputs_path.write_text(
            json.dumps([asdict(spec) for spec in specs], indent=2) + "\n",
            encoding="utf-8"
        )
    done = {row["index"] for row in rows}
    worker = Worker(run_one)
    try:
        with output.open("a" if resume else "w", encoding="utf-8") as stream:
            for spec in specs:
                if spec.index in done:
                    continue
                print(f"[{spec.index}/288] START {spec.logic}", flush=True)
                try:
                    row = worker.run((spec, settings), settings["hard_timeout_ms"])
                except WorkerError as exc:
                    row = empty_result(spec)
                    row.update(
                        status="timeout" if isinstance(exc, WorkerTimeout) else "error",
                        hard_timeout=isinstance(exc, WorkerTimeout),
                        elapsed_ms=exc.elapsed_ms, cpu_ms=None, error=str(exc)
                    )
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                stream.flush()
                rows.append(row)
                print(
                    f'[{spec.index}/288] {row["status"]}: '
                    f'{row["proof_lines"]} lines, {row["elapsed_ms"] / 1000:.3f} s',
                    flush=True
                )
    except KeyboardInterrupt:
        print("Interrupted. Completed results are saved.", flush=True)
    finally:
        worker.close()
    complete = len(rows) == len(specs)
    groups = audit_results(rows, metadata, specs, complete=complete)
    summary_path.write_text(
        json.dumps(groups, indent=2) + "\n", encoding="utf-8"
    )
    print_summary(groups)
    return 130 if not complete else int(any(row["status"] == "error" for row in rows))


def _writable(path):
    path = Path(path).resolve()
    manifest = DIRECTORY / "results/manifest.json"
    if path.parent == manifest.parent and manifest.exists():
        names = json.loads(manifest.read_text())["files"]
        protected = {manifest.parent / name for name in names}
        if path in protected or path == manifest:
            raise ValueError("Recorded results are read-only. Choose another path.")


def main():
    parser = argparse.ArgumentParser(description="Crotts-Tate proof benchmark.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Generate proofs for the source problems.")
    run.add_argument(
        "--output", help=(
            "JSONL output path; defaults to "
            "results/local/crotts-tate-<seconds>s.jsonl."
        )
    )
    run.add_argument(
        "--mode", choices=("staged", "exhaustive", "fast"), default="staged"
    )
    run.add_argument("--timeout-ms", type=_positive_int, default=5000)
    run.add_argument("--hard-timeout-ms", type=_positive_int)
    run.add_argument(
        "--derived-rules", action=argparse.BooleanOptionalAction, default=True
    )
    run.add_argument("--start", type=_positive_int, default=1)
    run.add_argument("--end", type=_positive_int, default=288)
    run.add_argument("--no-resume", action="store_true")
    for name in ("report", "audit"):
        command = commands.add_parser(name)
        command.add_argument(
            "results", nargs="?", default=str(DIRECTORY / "results/crotts-tate-5s.jsonl")
        )
        if name == "report":
            command.add_argument("--csv")
            command.add_argument("--tables")
    args = parser.parse_args()
    try:
        verify_source()
        specs = load_problems(SOURCE)
        if len(specs) != 288 or sum(s.logic == "TFL" for s in specs) != 203:
            raise ValueError("Expected 288 problems with the 203/85 partition.")
        if args.command == "run":
            if not 1 <= args.start <= args.end <= len(specs):
                raise ValueError("The problem range must lie between 1 and 288.")
            count = 2 if args.mode == "staged" else 1
            hard_timeout = args.hard_timeout_ms or count * args.timeout_ms + 2000
            if hard_timeout < count * args.timeout_ms:
                raise ValueError("The watchdog must cover all search stages.")
            output = args.output or DIRECTORY / (
                f"results/local/crotts-tate-{args.timeout_ms / 1000:g}s.jsonl"
            )
            return run_benchmark(
                specs[args.start - 1:args.end], output,
                {
                    "mode": args.mode, "timeout_ms": args.timeout_ms,
                    "hard_timeout_ms": hard_timeout, "derived_rules": args.derived_rules
                }, resume=not args.no_resume
            )
        path = Path(args.results)
        metadata = json.loads(path.with_suffix(".metadata.json").read_text(
            encoding="utf-8"
        ))
        rows = load_results(path)
        _verify_artifacts(path)
        _verify_inputs(path, metadata, specs)
        groups = audit_results(rows, metadata, specs, complete=args.command == "audit")
        if args.command == "audit":
            print(f"Verified {sum(row['success'] for row in rows)} saved proofs.")
        else:
            protected = {
                path.resolve(), path.with_suffix(".metadata.json").resolve(),
                path.with_suffix(".inputs.json").resolve(),
                path.with_suffix(".summary.json").resolve()
            }
            for destination in (args.csv, args.tables):
                if destination:
                    _writable(destination)
                    if Path(destination).resolve() in protected:
                        raise ValueError("Exports must differ from the result artifacts.")
            if args.csv:
                write_csv(rows, args.csv)
            if args.tables:
                write_csv(comparison_tables(groups), args.tables)
        print_summary(groups)
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def _verify_artifacts(path):
    manifest = path.parent / "manifest.json"
    if manifest.exists():
        files = json.loads(manifest.read_text())["files"]
        for name, expected in files.items():
            if file_hash(path.parent / name) != expected:
                raise ValueError(f"Changed result artifact: {name}.")


def _verify_inputs(path, metadata, specs):
    by_index = {spec.index: spec for spec in specs}
    expected = [asdict(by_index[index]) for index in metadata["indices"]]
    inputs = json.loads(path.with_suffix(".inputs.json").read_text(encoding="utf-8"))
    if inputs != expected:
        raise ValueError("Saved translated inputs differ from the source problems.")


def _positive_int(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer.")
    return result


if __name__ == "__main__":
    sys.exit(main())

