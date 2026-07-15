"""Scan a clean-chunk index for extraction damage before generation.

Damaged source chunks were only caught downstream: an empty chunk surfaced as a
contract error per book, and a chunk with dropped words (pte_chunk_053 --
"a reading text with  to five blanks", the number gone) surfaced as a
SOURCE_DAMAGED verdict in the per-chapter semantic audit, and only by luck. This
runs once over the whole index so the source can be fixed before any chapter is
generated on top of it.

Two signals, deliberately different in confidence:

- EMPTY (definitive): a chunk with no non-whitespace text. There is nothing to
  ground against. Reported as an error; the scan exits non-zero.

- SUSPECTED_GAP (heuristic): a run of two or more spaces between two short
  lowercase words, the fingerprint of a word dropped during extraction
  ("item  your", "with  to", "graph  the"). This is a REVIEW signal, not a
  verdict: it also catches benign wide spacing ("that  you"), so it is a warning
  and never fails the scan on its own. Precise garbled-text detection needs a
  language model; this only narrows 249 chunks to a handful worth a human's eye.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from clean_section_chunk_lookup import (
    CleanChunkLookupError,
    clean_chunk_node_id,
    load_clean_chunk_collection,
)

# 2+ spaces between two short lowercase alphabetic tokens. Short tokens keep the
# signal on the function-word joins where a dropped content word shows up, rather
# than every wide gap in justified text.
GAP_PATTERN = re.compile(r"\b[a-z]{1,6}\b {2,}\b[a-z]{1,6}\b")
GAP_CONTEXT_CHARS = 18


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flag empty or word-dropped clean chunks before generation."
    )
    parser.add_argument("--clean-chunks-file", required=True)
    parser.add_argument("--report", help="Optional path to write the text report.")
    parser.add_argument(
        "--json-out", help="Optional path to write the findings as JSON."
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=3,
        help="Gap snippets to show per chunk in the report (default 3).",
    )
    return parser.parse_args(argv)


def gap_snippets(text: str, *, limit: int) -> list[str]:
    snippets: list[str] = []
    for match in GAP_PATTERN.finditer(text):
        start = max(0, match.start() - GAP_CONTEXT_CHARS)
        end = min(len(text), match.end() + GAP_CONTEXT_CHARS)
        snippets.append(text[start:end].replace("\n", "\\n").strip())
        if len(snippets) >= limit:
            break
    return snippets


def scan_chunks(
    chunks: list[dict[str, Any]], *, max_examples: int = 3
) -> dict[str, Any]:
    empty: list[dict[str, Any]] = []
    suspected: list[dict[str, Any]] = []

    for index, chunk in enumerate(chunks):
        node_id = clean_chunk_node_id(chunk) or f"$[{index}]"
        text = chunk.get("text")

        if not isinstance(text, str) or not text.strip():
            empty.append({"node_id": node_id, "index": index})
            continue

        snippets = gap_snippets(text, limit=max_examples)
        if snippets:
            suspected.append(
                {
                    "node_id": node_id,
                    "index": index,
                    "gap_count": len(GAP_PATTERN.findall(text)),
                    "examples": snippets,
                }
            )

    return {
        "total_chunks": len(chunks),
        "empty": empty,
        "suspected_gap": suspected,
        "empty_count": len(empty),
        "suspected_gap_count": len(suspected),
    }


def format_report(result: dict[str, Any], clean_chunks_file: str) -> str:
    lines = [
        "CLEAN CHUNK DAMAGE SCAN",
        "=" * 72,
        f"Clean chunks file: {clean_chunks_file}",
        f"Total chunks: {result['total_chunks']}",
        f"Empty chunks: {result['empty_count']}",
        f"Suspected word-drop chunks: {result['suspected_gap_count']}",
        "",
        "EMPTY CHUNKS (no text to ground against; fix required)",
        "-" * 72,
    ]
    if result["empty"]:
        lines += [f"- {item['node_id']}" for item in result["empty"]]
    else:
        lines.append("- none")

    lines += [
        "",
        "SUSPECTED WORD DROPS (heuristic -- review, may include benign wide spacing)",
        "-" * 72,
    ]
    if result["suspected_gap"]:
        for item in result["suspected_gap"]:
            lines.append(f"- {item['node_id']} ({item['gap_count']} gap(s))")
            for example in item["examples"]:
                lines.append(f"    …{example}…")
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        chunks = load_clean_chunk_collection(args.clean_chunks_file)
    except CleanChunkLookupError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    result = scan_chunks(chunks, max_examples=args.max_examples)
    report = format_report(result, str(args.clean_chunks_file))
    print(report, end="")

    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )

    # Only definitive damage (empty chunks) fails the scan; the heuristic gap
    # signal is advisory and must not block a run on false positives.
    return 1 if result["empty_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
