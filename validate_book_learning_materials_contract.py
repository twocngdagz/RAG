import argparse
import sys
from pathlib import Path

from book_learning_materials_contract import (
    BookLearningMaterialsContractError,
    atomic_write_json,
    atomic_write_text,
    ensure_can_write,
    format_text_report,
    validate_book_contract,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a book_learning_materials.v2 artifact contract."
    )
    parser.add_argument("--book-file", required=True)
    parser.add_argument("--clean-chunks-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    report_path = Path(args.report) if args.report else None

    if not args.dry_run:
        ensure_can_write(
            [path for path in [output_path, report_path] if path is not None],
            args.overwrite,
        )

    audit = validate_book_contract(
        book_file=args.book_file,
        clean_chunks_file=args.clean_chunks_file,
    )
    summary = audit["summary"]

    print(f"Book file: {args.book_file}")
    print(f"Clean chunks file: {args.clean_chunks_file}")
    print(f"Status: {audit['status']}")
    print(f"Grounded content: {summary['grounded_content_count']}")
    print(f"Source grounded: {summary['source_grounded_count']}")
    print(f"Pedagogical generation: {summary['pedagogical_generation_count']}")
    print(
        "Insufficient source evidence: "
        f"{summary['insufficient_source_evidence_count']}"
    )
    print(f"High-risk claims: {summary['high_risk_claim_count']}")
    print(f"Verified evidence spans: {summary['verified_evidence_span_count']}")
    print(f"Errors: {len(audit['errors'])}")

    if args.dry_run:
        print(f"Output would be written: {output_path}")
        if report_path is not None:
            print(f"Report would be written: {report_path}")
        print("Dry run complete: no files written")
        return 0 if audit["status"] == "PASS" else 1

    atomic_write_json(output_path, audit)
    if report_path is not None:
        atomic_write_text(report_path, format_text_report(audit, output_path))
    print(f"Output written: {output_path}")
    if report_path is not None:
        print(f"Report written: {report_path}")

    return 0 if audit["status"] == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except BookLearningMaterialsContractError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
