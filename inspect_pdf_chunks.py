import argparse
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


EXTRACTED_DIR = Path("extracted")
PREVIEW_CHAR_LIMIT = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect PDF chunks and detect possible structure candidates."
    )
    parser.add_argument("chunks_path", help="Path to a PDF chunk JSON file.")
    return parser.parse_args()


def load_chunks(chunks_path: Path) -> list[dict]:
    if not chunks_path.exists():
        raise SystemExit(f"Chunk JSON file does not exist: {chunks_path}")

    if not chunks_path.is_file():
        raise SystemExit(f"Chunk JSON path is not a file: {chunks_path}")

    with chunks_path.open("r", encoding="utf-8") as file:
        chunks = json.load(file)

    if not isinstance(chunks, list):
        raise SystemExit("Chunk JSON must contain a top-level JSON array.")

    return chunks


def mostly_uppercase_short_line(line: str) -> bool:
    letters = [character for character in line if character.isalpha()]
    if not letters:
        return False

    uppercase_count = sum(1 for character in letters if character.isupper())
    return len(line) <= 80 and uppercase_count / len(letters) >= 0.8


def title_like_short_line(line: str) -> bool:
    if not line or len(line) >= 100:
        return False

    if line.endswith((".", ",", ";", ":")):
        return False

    words = line.split()
    if not 1 <= len(words) <= 12:
        return False

    title_like_words = 0
    for word in words:
        clean_word = word.strip("\"'()[]{}")
        if not clean_word:
            continue
        if clean_word[0].isupper() or clean_word.isdigit():
            title_like_words += 1

    return title_like_words >= max(1, len(words) // 2)


def match_heading_rule(line: str) -> str | None:
    stripped_line = line.strip()

    if not stripped_line:
        return None

    checks = [
        ("starts_with_chapter", r"^Chapter\b"),
        ("starts_with_unit", r"^Unit\b"),
        ("starts_with_module", r"^Module\b"),
        ("starts_with_lesson", r"^Lesson\b"),
        ("starts_with_section", r"^Section\b"),
        ("numbered_heading", r"^\d+(?:\.\d+)*\.?\s+\S+"),
    ]

    for rule, pattern in checks:
        if re.match(pattern, stripped_line):
            return rule

    if mostly_uppercase_short_line(stripped_line):
        return "mostly_uppercase_short_line"

    if title_like_short_line(stripped_line):
        return "short_title_like_line"

    return None


def build_preview(lines: list[str], line_index: int) -> str:
    start = max(0, line_index - 2)
    end = min(len(lines), line_index + 3)
    preview = " ".join(line.strip() for line in lines[start:end] if line.strip())
    return preview[:PREVIEW_CHAR_LIMIT]


def detect_candidates(chunks: list[dict]) -> list[dict]:
    candidates = []

    for chunk in chunks:
        text = str(chunk.get("text") or "")
        lines = text.splitlines()

        for line_index, line in enumerate(lines):
            stripped_line = line.strip()
            rule = match_heading_rule(stripped_line)

            if not rule:
                continue

            candidates.append(
                {
                    "chunk_id": chunk.get("id"),
                    "page_start": chunk.get("page_start"),
                    "page_end": chunk.get("page_end"),
                    "line": stripped_line,
                    "rule": rule,
                    "preview": build_preview(lines, line_index),
                }
            )

    return candidates


def summarize_metadata(chunks: list[dict]) -> list[dict]:
    metadata_values: dict[str, list[str]] = {}

    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue

        for key, value in metadata.items():
            serialized_value = json.dumps(value, ensure_ascii=False, default=str)
            metadata_values.setdefault(key, []).append(serialized_value)

    summaries = []
    for key, values in sorted(metadata_values.items()):
        value_counts = Counter(values)
        summaries.append(
            {
                "key": key,
                "chunk_count": len(values),
                "unique_value_count": len(value_counts),
                "sample_values": [
                    json.loads(value) for value, _ in value_counts.most_common(5)
                ],
            }
        )

    return summaries


def summarize_chunks(chunks_path: Path, chunks: list[dict], candidates: list[dict]) -> dict:
    lengths = [len(str(chunk.get("text") or "")) for chunk in chunks]
    rule_counts = Counter(candidate["rule"] for candidate in candidates)

    return {
        "source_chunks_file": str(chunks_path),
        "chunk_count": len(chunks),
        "total_characters": sum(lengths),
        "min_chunk_length": min(lengths) if lengths else 0,
        "max_chunk_length": max(lengths) if lengths else 0,
        "average_chunk_length": round(mean(lengths), 2) if lengths else 0,
        "empty_chunk_count": sum(1 for length in lengths if length == 0),
        "first_chunk_id": chunks[0].get("id") if chunks else None,
        "last_chunk_id": chunks[-1].get("id") if chunks else None,
        "candidate_count": len(candidates),
        "rule_counts": dict(sorted(rule_counts.items())),
        "metadata_candidates": summarize_metadata(chunks),
        "candidates": candidates,
    }


def output_stem(chunks_path: Path) -> str:
    if chunks_path.name.endswith(".chunks.json"):
        return chunks_path.name[: -len(".chunks.json")]

    return chunks_path.stem


def format_text_report(report: dict) -> str:
    lines = [
        "PDF Chunk Structure Candidate Report",
        "=" * 80,
        f"Source chunks file: {report['source_chunks_file']}",
        f"Chunk count: {report['chunk_count']}",
        f"Total characters: {report['total_characters']}",
        f"Minimum chunk length: {report['min_chunk_length']}",
        f"Maximum chunk length: {report['max_chunk_length']}",
        f"Average chunk length: {report['average_chunk_length']}",
        f"Empty chunk count: {report['empty_chunk_count']}",
        f"First chunk id: {report['first_chunk_id']}",
        f"Last chunk id: {report['last_chunk_id']}",
        f"Candidate count: {report['candidate_count']}",
        "",
        "Rule counts:",
    ]

    for rule, count in report["rule_counts"].items():
        lines.append(f"- {rule}: {count}")

    lines.extend(
        [
            "",
            "Metadata candidates:",
        ]
    )

    for metadata_candidate in report["metadata_candidates"]:
        sample_values = ", ".join(
            repr(value) for value in metadata_candidate["sample_values"]
        )
        lines.append(
            "- "
            f"{metadata_candidate['key']}: "
            f"{metadata_candidate['chunk_count']} chunks, "
            f"{metadata_candidate['unique_value_count']} unique values, "
            f"samples: {sample_values}"
        )

    lines.extend(
        [
            "",
            "Heading candidates:",
            "",
        ]
    )

    for position, candidate in enumerate(report["candidates"], start=1):
        lines.extend(
            [
                "=" * 80,
                f"Candidate #{position}",
                f"Chunk ID: {candidate['chunk_id']}",
                f"Pages: {candidate['page_start']}-{candidate['page_end']}",
                f"Rule: {candidate['rule']}",
                f"Line: {candidate['line']}",
                "",
                f"Preview: {candidate['preview']}",
                "",
            ]
        )

    return "\n".join(lines)


def write_report(chunks_path: Path, report: dict) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(chunks_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.structure_candidates.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.structure_candidates.txt"

    json_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_report(report), encoding="utf-8")

    return json_output_path, txt_output_path


def print_summary(report: dict, json_output_path: Path, txt_output_path: Path) -> None:
    print("PDF chunk inspection completed.")
    print(f"Source file: {report['source_chunks_file']}")
    print(f"Chunks: {report['chunk_count']}")
    print(f"Total characters: {report['total_characters']}")
    print(f"Minimum chunk length: {report['min_chunk_length']}")
    print(f"Maximum chunk length: {report['max_chunk_length']}")
    print(f"Average chunk length: {report['average_chunk_length']}")
    print(f"Empty chunk count: {report['empty_chunk_count']}")
    print(f"First chunk id: {report['first_chunk_id']}")
    print(f"Last chunk id: {report['last_chunk_id']}")
    print(f"Candidate count: {report['candidate_count']}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


def main() -> None:
    args = parse_args()
    chunks_path = Path(args.chunks_path)
    chunks = load_chunks(chunks_path)
    candidates = detect_candidates(chunks)
    report = summarize_chunks(chunks_path, chunks, candidates)
    json_output_path, txt_output_path = write_report(chunks_path, report)
    print_summary(report, json_output_path, txt_output_path)


if __name__ == "__main__":
    main()
