import argparse
import json
from pathlib import Path
import sys

from .audit import DIRECTORY, audit_run, verify_data
from .iltp import load_cases as load_iltp
from .qmltp import load_cases as load_qmltp
from .report import load_results, print_summary, summarize, write_csv
from .provenance import (
    case_set_hash, input_hash, validate_run_metadata, write_run_metadata
)
from .runner import run_cases, write_skips


def main():
    try:
        return _main()
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def _main():
    parser = _parser()
    args = parser.parse_args()

    if args.command == "iltp":
        cases, skipped = load_iltp(args.roots, args.stats)
        return _run(args, cases, skipped, "ILTP")
    elif args.command == "qmltp":
        cases, skipped = load_qmltp(
            args.root, include_classical=args.include_classical
        )
        return _run(args, cases, skipped, "QMLTP")
    elif args.command == "validate-iltp":
        cases, skipped = load_iltp(args.roots, args.stats)
        _validation_summary(cases, skipped)
        return int(_unexpected_skips(skipped))
    elif args.command == "validate-qmltp":
        cases, skipped = load_qmltp(
            args.root, include_classical=args.include_classical
        )
        _validation_summary(cases, skipped)
        return int(_unexpected_skips(skipped))
    elif args.command == "report":
        records = load_results(args.results)
        _print_reports(records)
        if args.csv:
            _check_output_path(args.csv)
            source = Path(args.results)
            protected = {
                path.resolve() for path in (
                    source, source.with_suffix(".metadata.json"),
                    source.with_suffix(".skips.jsonl")
                )
            }
            if Path(args.csv).resolve() in protected:
                raise ValueError("CSV output must differ from the run artifact paths.")
            write_csv(records, args.csv)
    elif args.command == "audit":
        imported = {}
        if args.data_root:
            root = Path(args.data_root)
            print("Verifying corpus checksums...", flush=True)
            verify_data(root)
            print("Importing ILTP...", flush=True)
            imported["ILTP"] = load_iltp([
                root / "ILTP-v1.1.2-firstorder",
                root / "ILTP-v1.1.2-propositional"
            ], [
                root / "ILTP-v1.1.2-fof-statistics.txt",
                root / "ILTP-v1.1.2-prop-statistics.txt"
            ])
            print("Importing QMLTP...", flush=True)
            imported["QMLTP"] = load_qmltp(root / "QMLTP-v1.1")
        paths = args.results or sorted((DIRECTORY / "results").glob("*.jsonl"))
        paths = [Path(p) for p in paths if not str(p).endswith(".skips.jsonl")]
        if not paths:
            raise ValueError("No result files selected.")
        for path in paths:
            metadata = json.loads(path.with_suffix(".metadata.json").read_text())
            cases, skipped = imported.get(metadata["library"], (None, None))
            summary = audit_run(path, cases, skipped)
            print(path.name)
            print_summary([summary], ())
            for warning in summary["warnings"]:
                print(f"  Note: {warning}")
    return 0


def _run(args, cases, skipped, library):
    cases = _select_cases(cases, args.case_id, args.case_list)
    output = Path(args.output)
    metadata = output.with_suffix(".metadata.json")
    skips = output.with_suffix(".skips.jsonl")
    for path in (output, metadata, skips):
        _check_output_path(path)
    if args.csv:
        _check_output_path(args.csv)
        if Path(args.csv).resolve() in {p.resolve() for p in (output, metadata, skips)}:
            raise ValueError("CSV output must differ from the run artifact paths.")

    _validation_summary(cases, skipped)
    if _unexpected_skips(skipped):
        raise ValueError("Corpus import failed. Resolve the reported skips first.")
    if not cases:
        raise ValueError("No benchmark cases selected.")
    hard_timeout = args.hard_timeout_ms or args.timeout_ms + 2000
    if hard_timeout < args.timeout_ms:
        raise ValueError("--hard-timeout-ms must be at least --timeout-ms.")
    run_info = {
        "library": library,
        "library_versions": sorted({case.version for case in cases}),
        "case_count": len(cases),
        "case_set_sha256": case_set_hash(c.case_id for c in cases),
        "input_sha256": input_hash(cases),
        "hard_timeout_ms": hard_timeout,
        "skipped_problem_count": len(skipped)
    }
    resume = not args.no_resume
    if resume and output.exists():
        validate_run_metadata(metadata, args.timeout_ms, run_info)
    else:
        write_run_metadata(metadata, args.timeout_ms, run_info)
    write_skips(skips, skipped)
    complete = run_cases(
        cases,
        output,
        args.timeout_ms,
        resume=resume,
        hard_timeout_ms=hard_timeout
    )

    records = load_results(output)
    _print_reports(records)
    if args.csv:
        write_csv(records, args.csv)
    return 0 if complete else 130

def _select_cases(cases, case_ids=None, case_list=None):
    selected = set(case_ids or [])
    if case_list:
        for line in Path(case_list).read_text(encoding="utf-8").splitlines():
            case_id = line.strip().lstrip("\ufeff")
            if case_id and not case_id.startswith("#"):
                selected.add(case_id)

    if not selected:
        if case_list:
            raise ValueError("The case list is empty.")
        return cases

    available = {case.case_id for case in cases}
    missing = sorted(selected - available)
    if missing:
        preview = ", ".join(missing[:10])
        if len(missing) > 10:
            preview += f", ... and {len(missing) - 10} more"
        raise ValueError(f"Unknown benchmark case ID(s): {preview}")

    return [case for case in cases if case.case_id in selected]


def _print_reports(records):
    default_group = ("library", "logic", "source_domain")
    status_group = ("library", "source_status")

    print("Results by logic/semantics:")
    print_summary(summarize(records, default_group), default_group)
    print("Results by source status:")
    print_summary(summarize(records, status_group), status_group)


def _unexpected_skips(skipped):
    return any(s.reason not in {"MULTIMODAL", "CLASSICAL_ONLY"} for s in skipped)


def _check_output_path(path):
    path = Path(path).resolve()
    if path.parent == (DIRECTORY / "results").resolve():
        archive = json.loads((DIRECTORY / "results/manifest.json").read_text())
        protected = {DIRECTORY / "results" / name for name in archive["files"]}
        if path in protected or path.name == "manifest.json":
            raise ValueError("Archived runs are read-only. Choose another output path.")


def _validation_summary(cases, skipped):
    reasons = {}
    for item in skipped:
        reasons[item.reason] = reasons.get(item.reason, 0) + 1

    problems = len({case.problem_id for case in cases})
    print(f"Loaded {len(cases)} case(s) from {problems} problem(s).")
    print(f"Skipped {len(skipped)} problem(s).")
    for reason, count in sorted(reasons.items()):
        print(f"  {reason}: {count}")

    errors = [item for item in skipped if item.reason == "LOAD_ERROR"]
    if errors:
        print("Load errors:")
        for item in errors[:20]:
            print(f"  {item.problem_id}: {item.detail}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")


def _parser():
    parser = argparse.ArgumentParser(
        description="Benchmark semantic validity on ILTP and QMLTP."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    iltp = subparsers.add_parser("iltp", help="Run the ILTP benchmark.")
    _iltp_args(iltp)
    _run_args(iltp)

    qmltp = subparsers.add_parser("qmltp", help="Run the QMLTP benchmark.")
    _qmltp_args(qmltp)
    _run_args(qmltp)

    validate_iltp = subparsers.add_parser(
        "validate-iltp", help="Parse and validate ILTP without solving."
    )
    _iltp_args(validate_iltp)

    validate_qmltp = subparsers.add_parser(
        "validate-qmltp", help="Parse and validate QMLTP without solving."
    )
    _qmltp_args(validate_qmltp)

    report = subparsers.add_parser(
        "report", help="Summarize an existing JSONL benchmark run."
    )
    report.add_argument("results")
    report.add_argument("--csv")

    audit = subparsers.add_parser("audit", help="Verify saved runs and corpus inputs.")
    audit.add_argument("results", nargs="*", help="Defaults to the four archived runs.")
    audit.add_argument(
        "--data-root", help="Also verify and reimport the official data."
    )
    return parser


def _iltp_args(parser):
    parser.add_argument(
        "roots", nargs="+",
        help="Extracted ILTP first-order/propositional library root(s)."
    )
    parser.add_argument(
        "--stats", action="append",
        help=(
            "Optional ILTP statistics file. Repeat for both first-order and "
            "propositional statistics. Header metadata is a fallback."
        )
    )


def _qmltp_args(parser):
    parser.add_argument("root", help="Extracted QMLTP v1.1 library root.")
    parser.add_argument(
        "--include-classical", action="store_true",
        help="Include the NLP/SET problems that contain no modal operators."
    )


def _run_args(parser):
    parser.add_argument("--output", required=True)
    parser.add_argument("--csv")
    parser.add_argument("--timeout-ms", type=_positive_int, default=10000)
    parser.add_argument(
        "--hard-timeout-ms", type=_positive_int,
        help=(
            "Wall-clock watchdog for the whole case. Defaults to "
            "--timeout-ms + 2000. This can terminate native cvc5 calls "
            "that do not return promptly after the solver timeout."
        )
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Overwrite output rather than skipping completed case IDs."
    )
    parser.add_argument(
        "--case-id", action="append",
        help="Run only this exact benchmark case ID. Repeat as needed."
    )
    parser.add_argument(
        "--case-list",
        help="Run only case IDs listed in this UTF-8 text file."
    )


def _positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer.")
    return number


if __name__ == "__main__":
    sys.exit(main())

