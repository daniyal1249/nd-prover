import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from ..common import environment_metadata, file_hash, repair_jsonl
from ..proofs import count_proof, proof_shape, restore_proof
from ..worker import Worker, WorkerError, WorkerTimeout
from .corpus import (
    COMMIT, DEFAULT_SOURCE, DIRECTORY, EDITION, REPOSITORY, SOURCE,
    SOURCE_MANIFEST, build_corpus, load_problems, make_reference, reference_metrics,
    uses_identity, verify_source, write_corpus
)
from .latex import parse_derivation
from .proofs import empty_result, run_one
from .report import audit_results, load_results, print_summary, write_csv


def git(source, *args):
    return subprocess.run([
        "git", "-c", f"safe.directory={Path(source).resolve().as_posix()}",
        "-C", str(source), *args
    ], check=True, text=True, capture_output=True).stdout.strip()


def setup_source(source):
    source = Path(source)
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(source)], check=True)
        git(source, "remote", "add", "origin", REPOSITORY)
    if git(source, "remote", "get-url", "origin") != REPOSITORY:
        raise ValueError("The source directory belongs to another repository.")
    try:
        head = git(source, "rev-parse", "--verify", "HEAD")
    except subprocess.CalledProcessError:
        head = None
    if head != COMMIT:
        if git(source, "status", "--porcelain"):
            raise ValueError("The source checkout has local changes.")
        git(source, "fetch", "--depth", "1", "--filter=blob:none", "origin", COMMIT)
        git(source, "sparse-checkout", "set", "--no-cone",
            "/solutions/", "/*.tex", "/*.sty", "/LICENSE.md")
        git(source, "checkout", "--detach", COMMIT)
    if git(source, "rev-parse", "HEAD") != COMMIT:
        raise ValueError(f"Expected the pinned source commit {COMMIT}.")
    verify_source(source)
    print(f"Verified source {COMMIT[:7]} at {source}.")


def inputs(specs):
    return [{key: getattr(spec, key) for key in ("case_id", "logic", "premises", "conclusion")} for spec in specs]


def metadata_for(specs, settings):
    return {
        "schema_version": 1, "suite": "forall x: Calgary",
        **environment_metadata("forallx"), **settings,
        "edition": EDITION, "source_commit": COMMIT,
        "source_manifest_sha256": file_hash(SOURCE_MANIFEST),
        "corpus_sha256": file_hash(SOURCE),
        "input_sha256": hashlib.sha256(json.dumps(inputs(specs), sort_keys=True).encode()).hexdigest(),
        "case_ids": [spec.case_id for spec in specs]
    }


def artifact_paths(path):
    path = Path(path)
    return [path, *(path.with_suffix(suffix) for suffix in (".metadata.json", ".inputs.json", ".summary.json"))]


def writable(path):
    path = Path(path).resolve()
    corpus_files = {DIRECTORY / name for name in ("problems.json", "coverage.json", "source.json")}
    protected = {file.resolve() for file in corpus_files}
    manifest = DIRECTORY / "results/manifest.json"
    if manifest.exists():
        protected |= {(manifest.parent / name).resolve()
                      for name in json.loads(manifest.read_text())["files"]}
    protected.add(manifest.resolve())
    if path in protected:
        raise ValueError("Recorded artifacts are read-only. Choose another output path.")


def run_benchmark(specs, output, settings, resume=True):
    if not specs or any(not spec.reference["validated"] for spec in specs):
        raise ValueError("Each benchmark problem must have a checked official reference.")
    if any(uses_identity(spec.premises, spec.conclusion) for spec in specs):
        raise ValueError("Identity is not supported by the proof generator.")
    output, metadata_path, inputs_path, summary_path = artifact_paths(output)
    if output.suffix != ".jsonl":
        raise ValueError("Use a .jsonl result filename.")
    for path in artifact_paths(output):
        writable(path)
    metadata = metadata_for(specs, settings)
    output.parent.mkdir(parents=True, exist_ok=True)
    if resume and output.exists():
        saved = json.loads(metadata_path.read_text(encoding="utf-8"))
        if any(saved.get(key) != value for key, value in metadata.items()):
            raise ValueError("Code, inputs, or settings changed. Choose another output path.")
        if json.loads(inputs_path.read_text(encoding="utf-8")) != inputs(specs):
            raise ValueError("Saved inputs differ from the corpus.")
        repair_jsonl(output)
        rows = load_results(output)
        audit_results(rows, saved, specs, complete=False)
    else:
        rows = []
        metadata["created_at"] = datetime.now(timezone.utc).isoformat()
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        inputs_path.write_text(json.dumps(inputs(specs), indent=2) + "\n", encoding="utf-8")
    done = {row["case_id"] for row in rows}
    worker = Worker(run_one)
    try:
        with output.open("a" if resume else "w", encoding="utf-8") as stream:
            for spec in specs:
                if spec.case_id in done:
                    continue
                print(f"[{spec.index}] START {spec.case_id} ({spec.logic})", flush=True)
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
                    f'[{spec.index}] {row["status"]}: '
                    f'{row["elapsed_ms"] / 1000:.3f} s', flush=True
                )
    except KeyboardInterrupt:
        print("Interrupted. Completed results are saved.", flush=True)
    finally:
        worker.close()
    complete = len(rows) == len(specs)
    groups = audit_results(rows, metadata, specs, complete=complete)
    summary_path.write_text(json.dumps(groups, indent=2) + "\n", encoding="utf-8")
    print_summary(groups)
    return 130 if not complete else int(any(row["status"] == "error" for row in rows))


def audit_corpus(source=None):
    specs = load_problems()
    if [spec.index for spec in specs] != list(range(1, len(specs) + 1)):
        raise ValueError("Corpus indices are not consecutive.")
    if len({spec.case_id for spec in specs}) != len(specs):
        raise ValueError("Duplicate corpus case IDs.")
    if source is not None:
        verify_source(source)
        regenerated, coverage, _ = build_corpus(source)
        if regenerated != [asdict(spec) for spec in specs] or coverage != json.loads((DIRECTORY / "coverage.json").read_text(encoding="utf-8")):
            raise ValueError("Imported corpus differs from the checked-in artifacts.")
    for spec in specs:
        for reference in spec.references:
            if any(reference[key] != getattr(spec, key) for key in ("logic", "exercise", "premises", "conclusion")):
                raise ValueError(f"{spec.case_id}: official reference has a different statement.")
            location = {key: reference[key] for key in ("source_file", "source_line", "source_proof", "exercise")}
            rebuilt = make_reference(
                reference["source_tex"], reference["statement_tex"], location, spec.logic, spec.chapter)
            if any(value != reference[key] for key, value in json.loads(json.dumps(rebuilt)).items()):
                raise ValueError(f"{spec.case_id}: reference import differs.")
            if reference_metrics(parse_derivation(reference["source_tex"])) != reference["metrics"]:
                raise ValueError(f"{spec.case_id}: official proof metrics differ.")
            problem = restore_proof(spec, reference["proof"], True)
            counts = {**count_proof(problem), **proof_shape(problem)}
            if any(counts[key] != value for key, value in reference["metrics"].items()):
                raise ValueError(f"{spec.case_id}: reconstructed official metrics differ.")
    references = [reference for spec in specs for reference in spec.references]
    print(f"Verified {len(specs)} problems and {len(references)} official reference derivations.")
    print("Every benchmark problem has a checked official reference; exclusions are in coverage.json.")


def load_run(path, specs, complete):
    path = Path(path)
    manifest = path.parent / "manifest.json"
    if manifest.exists():
        for name, expected in json.loads(manifest.read_text())["files"].items():
            if file_hash(path.parent / name) != expected:
                raise ValueError(f"Changed result artifact: {name}.")
    metadata = json.loads(path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    by_id = {spec.case_id: spec for spec in specs}
    selected = [by_id[case_id] for case_id in metadata["case_ids"]]
    expected = metadata_for(selected, {key: metadata[key] for key in (
        "mode", "timeout_ms", "hard_timeout_ms", "derived_rules")})
    for key in ("corpus_sha256", "source_manifest_sha256", "input_sha256", "source_commit"):
        if metadata[key] != expected[key]:
            raise ValueError(f"Run metadata differs from the corpus: {key}.")
    if json.loads(path.with_suffix(".inputs.json").read_text(encoding="utf-8")) != inputs(selected):
        raise ValueError("Saved inputs differ from the corpus.")
    rows = load_results(path)
    return rows, audit_results(rows, metadata, specs, complete=complete)


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer.")
    return number


def main():
    parser = argparse.ArgumentParser(
        description="Proof generation on the forall x: Calgary solutions.")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("setup", help="Clone and verify the pinned textbook source.")
    setup.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    corpus = commands.add_parser(
        "audit-corpus", help="Check reference proofs and optionally reimport source.")
    corpus.add_argument("--source-dir", type=Path)
    importer = commands.add_parser("import", help="Rebuild the corpus in a separate directory.")
    importer.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    importer.add_argument("--output-dir", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--output", type=Path)
    run.add_argument("--timeout-ms", type=positive, default=5000)
    run.add_argument("--hard-timeout-ms", type=positive)
    run.add_argument("--mode", choices=("staged", "exhaustive", "fast"), default="staged")
    run.add_argument("--derived-rules", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--start", type=positive, default=1)
    run.add_argument("--end", type=positive)
    run.add_argument("--case-id", action="append")
    run.add_argument("--no-resume", action="store_true")
    for name in ("audit", "report"):
        command = commands.add_parser(name)
        command.add_argument(
            "results", type=Path, nargs="?", default=DIRECTORY / "results/forallx-5s.jsonl"
        )
        if name == "report":
            command.add_argument("--csv", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "setup":
            setup_source(args.source_dir)
            return 0
        if args.command == "audit-corpus":
            audit_corpus(args.source_dir)
            return 0
        if args.command == "import":
            verify_source(args.source_dir)
            if args.output_dir.resolve() == DIRECTORY:
                raise ValueError(
                    "Rebuild into a separate directory to preserve the recorded corpus.")
            if git(args.source_dir, "rev-parse", "HEAD") != COMMIT:
                raise ValueError("The source checkout is not the pinned revision.")
            write_corpus(args.source_dir, args.output_dir)
            print(f"Rebuilt corpus in {args.output_dir}.")
            return 0
        specs = load_problems()
        if args.command == "run":
            end = args.end or len(specs)
            if not 1 <= args.start <= end <= len(specs):
                raise ValueError(f"The range must lie within 1-{len(specs)}.")
            selected = specs[args.start - 1:end]
            if args.case_id:
                wanted = set(args.case_id)
                selected = [spec for spec in selected if spec.case_id in wanted]
                if {spec.case_id for spec in selected} != wanted:
                    raise ValueError("Unknown case ID or case outside the selected range.")
            stages = 2 if args.mode == "staged" else 1
            hard = args.hard_timeout_ms or stages * args.timeout_ms + 2000
            if hard < stages * args.timeout_ms:
                raise ValueError("The watchdog must cover all search stages.")
            output = args.output or DIRECTORY / \
                f"results/local/forallx-{args.timeout_ms / 1000:g}s.jsonl"
            return run_benchmark(selected, output, {
                "mode": args.mode, "timeout_ms": args.timeout_ms,
                "hard_timeout_ms": hard, "derived_rules": args.derived_rules
            }, resume=not args.no_resume)
        rows, groups = load_run(args.results, specs, complete=args.command == "audit")
        if args.command == "audit":
            print(f'Verified {sum(row["success"] for row in rows)} saved proofs.')
        elif args.csv:
            writable(args.csv)
            if args.csv.resolve() in {path.resolve() for path in artifact_paths(args.results)}:
                raise ValueError("CSV output must differ from result artifacts.")
            write_csv(rows, args.csv)
        print_summary(groups)
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

