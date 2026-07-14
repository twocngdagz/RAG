import argparse
import subprocess
import sys
from pathlib import Path

from pdf_artifact_paths import get_clean_section_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare cleaned section chunks and a clean section PDF index "
            "for a document slug."
        )
    )
    parser.add_argument(
        "--section-chunks",
        required=True,
        help="Path to <slug>.section_chunks.json",
    )
    parser.add_argument(
        "--structure-resolution",
        help="Optional override for <slug>.structure_resolution.json",
    )
    parser.add_argument(
        "--clean-output",
        help="Optional override for <slug>.section_clean_chunks.json",
    )
    parser.add_argument(
        "--clean-report",
        help="Optional override for <slug>.section_clean_chunks.txt",
    )
    parser.add_argument(
        "--storage-dir",
        help="Optional override for clean index storage directory",
    )
    parser.add_argument(
        "--index-id",
        help="Optional override for clean index ID",
    )
    parser.add_argument(
        "--overwrite-index",
        action="store_true",
        help="Overwrite an existing clean index storage directory.",
    )
    parser.add_argument(
        "--skip-clean",
        action="store_true",
        help="Skip cleaning and reuse an existing clean chunks file.",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Skip building the clean section index.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved plan without writing files.",
    )
    return parser.parse_args()


def resolve_plan(args: argparse.Namespace) -> dict[str, object]:
    section_chunks_path = Path(args.section_chunks)
    artifacts = get_clean_section_artifacts(section_chunks_path)

    structure_resolution = Path(
        args.structure_resolution or artifacts["structure_resolution_path"]
    )
    clean_output = Path(args.clean_output or artifacts["clean_chunks_path"])
    clean_report = Path(args.clean_report or artifacts["clean_report_path"])
    storage_dir = Path(args.storage_dir or artifacts["clean_storage_dir"])
    index_id = args.index_id or artifacts["clean_index_id"]

    return {
        "document_slug": artifacts["document_slug"],
        "section_chunks": section_chunks_path,
        "structure_resolution": structure_resolution,
        "clean_chunks": clean_output,
        "clean_report": clean_report,
        "clean_index_id": index_id,
        "clean_storage_dir": storage_dir,
        "overwrite_index": bool(args.overwrite_index),
        "skip_clean": bool(args.skip_clean),
        "skip_index": bool(args.skip_index),
        "dry_run": bool(args.dry_run),
    }


def print_plan(plan: dict[str, object]) -> None:
    lines = [
        "Clean section index preparation plan",
        f"Document slug: {plan['document_slug']}",
        f"Section chunks: {plan['section_chunks']}",
        f"Structure resolution: {plan['structure_resolution']}",
        f"Clean chunks: {plan['clean_chunks']}",
        f"Clean report: {plan['clean_report']}",
        f"Clean index ID: {plan['clean_index_id']}",
        f"Clean storage dir: {plan['clean_storage_dir']}",
        f"Skip clean: {plan['skip_clean']}",
        f"Skip index: {plan['skip_index']}",
        f"Overwrite index: {plan['overwrite_index']}",
        f"Dry run: {plan['dry_run']}",
    ]
    print("\n".join(lines), flush=True)


def run_command(command: list[str]) -> None:
    print("", flush=True)
    print("Running:", " ".join(command), flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def validate_inputs(plan: dict[str, object]) -> None:
    section_chunks = Path(plan["section_chunks"])
    structure_resolution = Path(plan["structure_resolution"])

    if not section_chunks.exists():
        raise SystemExit(f"Section chunks file does not exist: {section_chunks}")

    if not structure_resolution.exists():
        raise SystemExit(
            f"Structure resolution file does not exist: {structure_resolution}"
        )


def run_clean(plan: dict[str, object]) -> None:
    command = [
        sys.executable,
        "clean_pdf_section_boundaries.py",
        str(plan["section_chunks"]),
        str(plan["structure_resolution"]),
        "--output",
        str(plan["clean_chunks"]),
        "--report",
        str(plan["clean_report"]),
    ]
    run_command(command)


def run_index(plan: dict[str, object]) -> None:
    command = [
        sys.executable,
        "build_clean_section_pdf_index.py",
        str(plan["clean_chunks"]),
        "--storage-dir",
        str(plan["clean_storage_dir"]),
        "--index-id",
        str(plan["clean_index_id"]),
    ]

    if plan["overwrite_index"]:
        command.append("--overwrite")

    run_command(command)


def print_summary(plan: dict[str, object]) -> None:
    lines = [
        "",
        "Clean section index preparation completed.",
        f"Document slug: {plan['document_slug']}",
        f"Clean chunks: {plan['clean_chunks']}",
        f"Clean report: {plan['clean_report']}",
        f"Clean index ID: {plan['clean_index_id']}",
        f"Clean storage dir: {plan['clean_storage_dir']}",
        f"Skip clean: {plan['skip_clean']}",
        f"Skip index: {plan['skip_index']}",
    ]
    print("\n".join(lines), flush=True)


def main() -> None:
    args = parse_args()
    plan = resolve_plan(args)
    print_plan(plan)

    if plan["dry_run"]:
        print("")
        print("No files written.")
        return

    validate_inputs(plan)

    if not plan["skip_clean"]:
        run_clean(plan)
    else:
        print("")
        print(f"Skipping clean. Reusing: {plan['clean_chunks']}")

    if not plan["skip_index"]:
        run_index(plan)
    else:
        print("")
        print("Skipping index build.")

    print_summary(plan)


if __name__ == "__main__":
    main()
