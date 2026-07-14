import argparse
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.llms.openai_like import OpenAILike

import book_learning_materials_v2_generation as v2
from pdf_artifact_paths import get_book_learning_material_paths


load_dotenv()

DEFAULT_NVIDIA_BASE_URL = os.getenv(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
)
DEFAULT_NVIDIA_MODEL = os.getenv(
    "NVIDIA_MODEL", "mistralai/mistral-medium-3.5-128b"
)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
# A conforming v2 chapter package (multiple grounded objects, each with text,
# citations, and evidence quotes) far exceeds the old 1500-token cap and was
# silently truncating. 8000 gives comfortable headroom; override per-run with
# --model-max-tokens.
DEFAULT_MODEL_MAX_TOKENS = int(os.getenv("MODEL_MAX_TOKENS", "8000"))
DEFAULT_CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "sonnet")
DEFAULT_CODEX_MODEL = os.getenv("CODEX_MODEL", "gpt-5.5")
DEFAULT_CODEX_REASONING_EFFORT = os.getenv("CODEX_REASONING_EFFORT", "high")
PIPELINE_VERSION = "book_learning_materials.v1"
TEXT_PREVIEW_MAX_CHARS = 300
STRUCTURE_FALLBACK_SOURCE = "lesson_header_fallback"
STRUCTURE_FALLBACK_CONFIDENCE = "medium"


class BookLearningMaterialsError(RuntimeError):
    pass


class ModelCallError(BookLearningMaterialsError):
    def __init__(self, message: str, *, reason: str = "model_call_failed"):
        super().__init__(message)
        self.reason = reason


class ModelJSONError(BookLearningMaterialsError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate whole-book learning materials from a raw PDF."
    )
    parser.add_argument("pdf_path", help="Path to the source PDF.")
    parser.add_argument(
        "--schema-version",
        choices=[PIPELINE_VERSION, v2.BOOK_LEARNING_MATERIALS_V2_SCHEMA_VERSION],
        default=PIPELINE_VERSION,
        help=(
            "Output schema version. v1 remains the temporary default; "
            "v2 is targeted chapter-only in Step 34C.2."
        ),
    )
    parser.add_argument(
        "--chapter-number",
        type=int,
        action="append",
        default=[],
        help=(
            "Repeatable selected chapter number for targeted v2 generation. "
            "Required for --schema-version book_learning_materials.v2."
        ),
    )
    parser.add_argument(
        "--chapter-packages-output",
        help=(
            "Checkpoint path for targeted v2 chapter packages. "
            "Required for Step 34C.2 v2 generation."
        ),
    )
    parser.add_argument("--output", help="Output JSON path.")
    parser.add_argument("--report", help="Readable TXT report path.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the final generated output if it exists.",
    )
    parser.add_argument(
        "--rebuild-artifacts",
        action="store_true",
        help="Rerun PDF preparation steps even when output artifacts exist.",
    )
    parser.add_argument(
        "--skip-prepare",
        action="store_true",
        help="Assume preparation artifacts already exist.",
    )
    parser.add_argument(
        "--overwrite-index",
        action="store_true",
        help="Allow prepare_clean_section_index.py to overwrite the clean index.",
    )
    parser.add_argument(
        "--max-chapters",
        type=int,
        help="Generate only the first N detected chapters.",
    )
    parser.add_argument(
        "--chapter-context-chars",
        type=int,
        default=16000,
        help="Maximum cleaned chapter text characters sent per chapter.",
    )
    parser.add_argument(
        "--book-synthesis-context-chars",
        type=int,
        default=20000,
        help="Maximum chapter package context characters sent to book synthesis.",
    )
    parser.add_argument(
        "--nvidia-model",
        default=DEFAULT_NVIDIA_MODEL,
        help="NVIDIA/OpenAI-compatible model name.",
    )
    parser.add_argument(
        "--backend",
        choices=["nvidia", "claude-cli", "codex-cli"],
        default=os.getenv("MODEL_BACKEND", "nvidia"),
        help=(
            "Model backend for generation. 'nvidia' calls the OpenAI-compatible "
            "endpoint (default). 'claude-cli' shells out to the local Claude Code "
            "CLI (`claude -p`) under your subscription. 'codex-cli' shells out to "
            "the OpenAI Codex CLI (`codex exec`) under your ChatGPT subscription. "
            "Both CLI backends have no per-token API cost."
        ),
    )
    parser.add_argument(
        "--claude-model",
        default=DEFAULT_CLAUDE_MODEL,
        help="Model alias passed to `claude --model` when --backend claude-cli.",
    )
    parser.add_argument(
        "--codex-model",
        default=DEFAULT_CODEX_MODEL,
        help="Model passed to `codex exec -m` when --backend codex-cli.",
    )
    parser.add_argument(
        "--codex-reasoning-effort",
        default=DEFAULT_CODEX_REASONING_EFFORT,
        choices=["minimal", "low", "medium", "high", "xhigh"],
        help="Reasoning effort for codex-cli (model_reasoning_effort).",
    )
    parser.add_argument(
        "--model-max-tokens",
        type=int,
        default=DEFAULT_MODEL_MAX_TOKENS,
        help=(
            "Max output tokens per model call for the nvidia backend. Defaults to "
            f"{DEFAULT_MODEL_MAX_TOKENS}. Too-low values truncate v2 chapters."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan only. Do not write files or call NVIDIA.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Prepare artifacts and clean index only. Do not call NVIDIA.",
    )
    parser.add_argument(
        "--continue-on-chapter-error",
        action="store_true",
        help="Save partial output with chapter error records instead of failing.",
    )
    parser.add_argument(
        "--resume-chapter-packages",
        help=(
            "Load an existing output/<slug>.chapter_packages.generated.json file "
            "and run only final book synthesis."
        ),
    )
    parser.add_argument(
        "--resume-missing-chapters",
        action="store_true",
        help=(
            "When used with --resume-chapter-packages, generate only missing "
            "chapters before final book synthesis."
        ),
    )
    parser.add_argument(
        "--model-timeout-seconds",
        type=int,
        default=180,
        help="Timeout in seconds for each model call. Defaults to 180.",
    )
    parser.add_argument(
        "--model-max-retries",
        type=int,
        default=2,
        help="Maximum retries after a failed model call or invalid chapter JSON.",
    )
    parser.add_argument(
        "--model-retry-backoff-seconds",
        type=float,
        default=5,
        help="Seconds to wait between model retries. Defaults to 5.",
    )
    return parser.parse_args()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def text_preview(text: str, max_chars: int = TEXT_PREVIEW_MAX_CHARS) -> str:
    normalized = normalize_whitespace(text)
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


def chunk_node_id(chunk: dict[str, Any]) -> str:
    value = chunk.get("node_id") or chunk.get("id")
    return str(value).strip() if value is not None else ""


def natural_id_key(value: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", value)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    pdf_path = Path(args.pdf_path)
    paths = get_book_learning_material_paths(
        pdf_path,
        output=args.output,
        report=args.report,
    )

    return {
        "pdf_path": pdf_path,
        "slug": paths["slug"],
        "paths": paths,
        "output_json": Path(paths["output_json"]),
        "output_report": Path(paths["output_report"]),
        "chapter_packages_json": Path(paths["chapter_packages_json"]),
        "clean_index_id": paths["clean_index_id"],
        "clean_storage_dir": Path(paths["clean_storage_dir"]),
    }


def preparation_steps(plan: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    paths = plan["paths"]
    python = sys.executable
    steps: list[dict[str, Any]] = [
        {
            "name": "pdf_to_chunks",
            "command": [python, "pdf_to_chunks.py", str(plan["pdf_path"])],
            "outputs": [Path(paths["raw_chunks"])],
        },
        {
            "name": "inspect_pdf_chunks",
            "command": [python, "inspect_pdf_chunks.py", paths["raw_chunks"]],
            "outputs": [Path(paths["structure_candidates"])],
        },
        {
            "name": "build_pdf_outline",
            "command": [python, "build_pdf_outline.py", paths["structure_candidates"]],
            "outputs": [Path(paths["outline_candidates"])],
        },
        {
            "name": "build_pdf_body_outline",
            "command": [
                python,
                "build_pdf_body_outline.py",
                paths["outline_candidates"],
                paths["raw_chunks"],
            ],
            "outputs": [Path(paths["body_outline"])],
        },
        {
            "name": "assign_pdf_chapters",
            "command": [
                python,
                "assign_pdf_chapters.py",
                paths["raw_chunks"],
                paths["body_outline"],
            ],
            "outputs": [Path(paths["chapter_chunks"])],
        },
        {
            "name": "detect_pdf_sections_topics",
            "command": [python, "detect_pdf_sections_topics.py", paths["chapter_chunks"]],
            "outputs": [Path(paths["section_topic_candidates"])],
        },
        {
            "name": "build_pdf_section_outline",
            "command": [
                python,
                "build_pdf_section_outline.py",
                paths["section_topic_candidates"],
            ],
            "outputs": [Path(paths["section_outline"])],
        },
    ]

    if Path("build_pdf_strict_section_outline.py").exists():
        steps.append(
            {
                "name": "build_pdf_strict_section_outline",
                "command": [
                    python,
                    "build_pdf_strict_section_outline.py",
                    paths["section_topic_candidates"],
                ],
                "outputs": [Path(paths["strict_section_outline"])],
                "optional": True,
            }
        )

    resolve_command = [
        python,
        "resolve_document_structure.py",
        paths["chapter_chunks"],
        "--body-outline",
        paths["body_outline"],
        "--section-candidates",
        paths["section_topic_candidates"],
        "--section-outline",
        paths["section_outline"],
    ]
    if Path("build_pdf_strict_section_outline.py").exists():
        resolve_command.extend(
            ["--strict-section-outline", paths["strict_section_outline"]]
        )
    steps.extend(
        [
            {
                "name": "resolve_document_structure",
                "command": resolve_command,
                "outputs": [Path(paths["structure_resolution"])],
            },
            {
                "name": "assign_pdf_sections",
                "command": [
                    python,
                    "assign_pdf_sections.py",
                    paths["chapter_chunks"],
                    paths["structure_resolution"],
                ],
                "outputs": [Path(paths["section_chunks"])],
            },
        ]
    )

    prepare_command = [
        python,
        "prepare_clean_section_index.py",
        "--section-chunks",
        paths["section_chunks"],
        "--structure-resolution",
        paths["structure_resolution"],
        "--clean-output",
        paths["clean_chunks"],
        "--clean-report",
        paths["clean_report"],
        "--storage-dir",
        paths["clean_storage_dir"],
        "--index-id",
        paths["clean_index_id"],
    ]
    clean_exists = Path(paths["clean_chunks"]).exists()
    index_exists = Path(paths["clean_storage_dir"]).exists()
    if args.overwrite_index:
        prepare_command.append("--overwrite-index")
    elif args.rebuild_artifacts and index_exists:
        raise BookLearningMaterialsError(
            f"Clean index exists and --rebuild-artifacts was requested: {paths['clean_storage_dir']}\n"
            "Pass --overwrite-index to rebuild the index."
        )
    if clean_exists and not args.rebuild_artifacts:
        prepare_command.append("--skip-clean")
    if index_exists and not args.rebuild_artifacts:
        prepare_command.append("--skip-index")

    steps.append(
        {
            "name": "prepare_clean_section_index",
            "command": prepare_command,
            "outputs": [Path(paths["clean_chunks"]), Path(paths["clean_storage_dir"])],
        }
    )
    return steps


def output_exists(step: dict[str, Any]) -> bool:
    return all(path.exists() for path in step["outputs"])


def lesson_marker_from_text(text: str) -> str | None:
    for raw_line in text.splitlines()[:10]:
        line = normalize_whitespace(raw_line)
        if not line:
            continue
        match = re.match(r"^(recap\s+lesson|lesson)\s+(\d+)\b", line, re.IGNORECASE)
        if not match:
            continue
        prefix = "RECAP LESSON" if match.group(1).lower().startswith("recap") else "LESSON"
        return f"{prefix} {int(match.group(2))}"
    return None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_lesson_header_fallback_artifacts(plan: dict[str, Any]) -> dict[str, Any] | None:
    paths = plan["paths"]
    raw_chunks_path = Path(paths["raw_chunks"])
    if not raw_chunks_path.exists():
        return None

    raw_chunks = load_clean_chunks(raw_chunks_path)
    current_chapter: dict[str, Any] | None = None
    chapter_records: list[dict[str, Any]] = []
    enriched_chunks: list[dict[str, Any]] = []

    for chunk in raw_chunks:
        marker = lesson_marker_from_text(str(chunk.get("text") or ""))
        if marker and (current_chapter is None or marker != current_chapter["chapter"]):
            current_chapter = {
                "chapter_number": len(chapter_records) + 1,
                "chapter": marker,
                "page_start": chunk.get("page_start"),
                "source_chunk_id": chunk.get("id"),
            }
            chapter_records.append(current_chapter)

        enriched = dict(chunk)
        enriched.setdefault("source_type", "pdf")
        enriched.setdefault("domain", None)
        enriched.setdefault("grade", None)
        enriched.setdefault("metadata", {})

        if current_chapter is None:
            enriched["chapter"] = None
            enriched["chapter_number"] = None
            enriched["chapter_source_chunk_id"] = None
            enriched["chapter_source_page"] = None
            enriched["is_front_matter"] = True
            enriched["section"] = None
            enriched["section_page_start"] = None
            enriched["section_source"] = None
            enriched["section_confidence"] = None
            enriched["section_level"] = None
            enriched["topic"] = None
        else:
            enriched["chapter"] = current_chapter["chapter"]
            enriched["chapter_number"] = current_chapter["chapter_number"]
            enriched["chapter_source_chunk_id"] = current_chapter["source_chunk_id"]
            enriched["chapter_source_page"] = current_chapter["page_start"]
            enriched["is_front_matter"] = False
            enriched["section"] = current_chapter["chapter"]
            enriched["section_page_start"] = current_chapter["page_start"]
            enriched["section_source"] = STRUCTURE_FALLBACK_SOURCE
            enriched["section_confidence"] = STRUCTURE_FALLBACK_CONFIDENCE
            enriched["section_level"] = 1
            enriched["topic"] = current_chapter["chapter"]

        enriched_chunks.append(enriched)

    if not chapter_records:
        return None

    selected_chapters = [
        {
            "chapter_number": record["chapter_number"],
            "chapter_title": record["chapter"],
            "chapter": record["chapter"],
            "page_start": record["page_start"],
            "sections": [
                {
                    "section_title": record["chapter"],
                    "page_start": record["page_start"],
                    "level": 1,
                }
            ],
        }
        for record in chapter_records
    ]
    structure_resolution = {
        "source_chunks_file": paths["chapter_chunks"],
        "selected_source": STRUCTURE_FALLBACK_SOURCE,
        "selected_confidence": STRUCTURE_FALLBACK_CONFIDENCE,
        "selected_outline": {"chapters": selected_chapters},
        "fallback_reason": "No standard body chapter outline or section groups were available.",
    }

    write_json(Path(paths["chapter_chunks"]), enriched_chunks)
    write_json(Path(paths["structure_resolution"]), structure_resolution)
    write_json(Path(paths["section_chunks"]), enriched_chunks)

    front_matter_count = sum(1 for chunk in enriched_chunks if chunk.get("is_front_matter"))
    with_section_count = sum(1 for chunk in enriched_chunks if chunk.get("section"))
    report_lines = [
        "LESSON HEADER FALLBACK STRUCTURE",
        f"Source chunks: {raw_chunks_path}",
        f"Chunks loaded: {len(raw_chunks)}",
        f"Lesson groups detected: {len(chapter_records)}",
        f"Chunks with section: {with_section_count}",
        f"Front matter chunks: {front_matter_count}",
        "",
        "LESSON GROUPS",
    ]
    for record in chapter_records:
        report_lines.append(
            f"- {record['chapter_number']}: {record['chapter']} "
            f"(page {record['page_start']}, chunk {record['source_chunk_id']})"
        )

    report_text = "\n".join(report_lines) + "\n"
    for report_path in [
        Path(paths["chapter_chunks_report"]),
        Path(paths["structure_resolution_report"]),
        Path(paths["section_chunks_report"]),
    ]:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")

    return {
        "chapter_count": len(chapter_records),
        "front_matter_count": front_matter_count,
        "with_section_count": with_section_count,
    }


def run_preparation(
    plan: dict[str, Any],
    args: argparse.Namespace,
    *,
    run_subprocess: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[dict[str, Any]]:
    if args.skip_prepare:
        return [{"name": "prepare", "status": "skipped", "reason": "--skip-prepare"}]

    results: list[dict[str, Any]] = []
    using_lesson_fallback = False
    for step in preparation_steps(plan, args):
        if using_lesson_fallback and step["name"] in {
            "build_pdf_strict_section_outline",
            "resolve_document_structure",
            "assign_pdf_sections",
        }:
            print(f"Skipping {step['name']}: lesson header fallback artifacts already exist.")
            results.append(
                {
                    "name": step["name"],
                    "status": "skipped",
                    "reason": "lesson_header_fallback",
                }
            )
            continue

        if output_exists(step) and not args.rebuild_artifacts:
            print(f"Skipping {step['name']}: outputs already exist.")
            results.append({"name": step["name"], "status": "skipped"})
            continue

        print(f"Running {step['name']}: {' '.join(step['command'])}")
        completed = run_subprocess(step["command"], check=False)
        returncode = getattr(completed, "returncode", 0)
        if returncode != 0:
            if step["name"] == "build_pdf_section_outline":
                fallback_summary = build_lesson_header_fallback_artifacts(plan)
                if fallback_summary is not None:
                    using_lesson_fallback = True
                    print(
                        "Standard section outline failed; using lesson-header fallback "
                        f"with {fallback_summary['chapter_count']} lesson groups."
                    )
                    results.append(
                        {
                            "name": step["name"],
                            "status": "failed_fallback",
                            "reason": "standard_section_outline_unavailable",
                        }
                    )
                    results.append(
                        {
                            "name": "lesson_header_fallback_structure",
                            "status": "run",
                            "reason": (
                                f"{fallback_summary['chapter_count']} lesson groups; "
                                f"{fallback_summary['with_section_count']} chunks with section"
                            ),
                        }
                    )
                    continue
            if step.get("optional"):
                print(f"Optional step failed and was skipped: {step['name']}")
                results.append({"name": step["name"], "status": "failed_optional"})
                continue
            raise BookLearningMaterialsError(
                f"Preparation step failed ({step['name']}) with exit code {returncode}."
            )
        results.append({"name": step["name"], "status": "run"})
    return results


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BookLearningMaterialsError(f"Missing required file: {path}") from error
    except json.JSONDecodeError as error:
        raise BookLearningMaterialsError(f"Invalid JSON in {path}: {error}") from error


def load_clean_chunks(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, list):
        raise BookLearningMaterialsError(f"{path} must contain a top-level array.")
    return data


def group_chunks_by_chapter(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: "OrderedDict[int, dict[str, Any]]" = OrderedDict()

    for chunk in chunks:
        if chunk.get("is_front_matter"):
            continue
        chapter_number = chunk.get("chapter_number")
        if chapter_number is None:
            continue
        try:
            chapter_number = int(chapter_number)
        except (TypeError, ValueError):
            continue
        chapter = grouped.setdefault(
            chapter_number,
            {
                "chapter_number": chapter_number,
                "chapter": chunk.get("chapter") or f"Chapter {chapter_number}",
                "chunks": [],
            },
        )
        chapter["chunks"].append(chunk)

    for chapter in grouped.values():
        chapter["chunks"].sort(
            key=lambda chunk: (
                chunk.get("page_start") or 0,
                chunk.get("page_end") or 0,
                natural_id_key(chunk_node_id(chunk)),
            )
        )

    return [grouped[key] for key in sorted(grouped)]


def detected_section_count(chunks: list[dict[str, Any]]) -> int:
    sections = {
        (chunk.get("chapter_number"), chunk.get("section"))
        for chunk in chunks
        if chunk.get("section")
    }
    return len(sections)


def build_chapter_context(
    chapter: dict[str, Any],
    *,
    max_chars: int,
) -> tuple[str, list[dict[str, Any]]]:
    blocks: list[str] = []
    included: list[dict[str, Any]] = []
    used_chars = 0

    for chunk in chapter["chunks"]:
        node_id = chunk_node_id(chunk)
        if not node_id:
            continue
        header = (
            f"CHUNK ID: {node_id}\n"
            f"Chapter: {chunk.get('chapter')}\n"
            f"Chapter number: {chunk.get('chapter_number')}\n"
            f"Section: {chunk.get('section')}\n"
            f"Topic: {chunk.get('topic')}\n"
            f"Pages: {chunk.get('page_start')}-{chunk.get('page_end')}\n"
            "Text:\n"
        )
        text = str(chunk.get("text") or "").strip()
        remaining = max_chars - used_chars - len(header) - 8
        if remaining <= 200:
            break
        if len(text) > remaining:
            text = text[:remaining].rstrip()
        block = f"{header}{text}\n---"
        blocks.append(block)
        included.append(chunk)
        used_chars += len(block)
        if used_chars >= max_chars:
            break

    if not included:
        raise BookLearningMaterialsError(
            f"No usable cleaned chunks for chapter {chapter['chapter_number']}."
        )

    return "\n\n".join(blocks), included


def require_env() -> None:
    if not NVIDIA_API_KEY:
        raise BookLearningMaterialsError(
            "Missing NVIDIA_API_KEY. Create a real .env file from .env.example."
        )


@contextlib.contextmanager
def model_timeout(seconds: int):
    if seconds <= 0:
        yield
        return

    def timeout_handler(_signum, _frame):
        raise TimeoutError("model_call_timeout")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def classify_model_error(error: Exception) -> str:
    error_name = type(error).__name__.lower()
    error_text = str(error).lower()
    if isinstance(error, TimeoutError) or "timeout" in error_name or "timed out" in error_text:
        return "model_call_timeout"
    return "model_call_failed"


def sleep_before_retry(args: argparse.Namespace) -> None:
    backoff = float(getattr(args, "model_retry_backoff_seconds", 0) or 0)
    if backoff > 0:
        time.sleep(backoff)


def default_complete(prompt: str, *, model: str, timeout_seconds: int) -> str:
    require_env()
    Settings.llm = OpenAILike(
        model=model,
        api_base=DEFAULT_NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
        is_chat_model=True,
        context_window=262144,
        max_tokens=DEFAULT_MODEL_MAX_TOKENS,
        timeout=timeout_seconds,
    )
    return str(Settings.llm.complete(prompt))


def default_complete_direct_openai_like(
    prompt: str,
    *,
    model: str,
    timeout_seconds: int,
    max_tokens: int = DEFAULT_MODEL_MAX_TOKENS,
) -> str:
    from openai import OpenAI

    require_env()
    client = OpenAI(
        api_key=NVIDIA_API_KEY,
        base_url=DEFAULT_NVIDIA_BASE_URL,
        timeout=timeout_seconds,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    choice = response.choices[0]
    content = choice.message.content
    if content is None:
        raise ModelJSONError("Model returned an empty response.")
    # A conforming v2 chapter package is large; if the model stopped because it
    # hit the token ceiling the JSON is truncated and unparseable. Surface this
    # as a retryable ModelJSONError instead of letting the truncated text fail
    # deeper in parsing with a confusing message.
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason == "length":
        raise ModelJSONError(
            "Model response was truncated at the token limit "
            f"(max_tokens={max_tokens}, finish_reason='length'). "
            "Increase --model-max-tokens."
        )
    return content


def complete_via_claude_cli(
    prompt: str,
    *,
    model: str,
    timeout_seconds: int,
) -> str:
    """Drive the local Claude Code CLI as a single-shot completion backend.

    The prompt is fed on stdin so it can be tens of KB (past shell ARG_MAX). We
    force a non-interactive, tool-free single turn and read the model text back
    from the JSON envelope. Runs under the user's Claude subscription with no
    per-token API cost. Requires `claude` on PATH and a prior `claude login`.
    """
    # Note: do NOT pass --bare. Bare mode skips the subscription OAuth credentials
    # from `claude login` and requires ANTHROPIC_API_KEY (metered API billing),
    # which defeats the point of using the CLI. --max-turns 1 plus the system
    # prompt is enough to get a single completion with no agent loop.
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--max-turns",
        "1",
        "--append-system-prompt",
        (
            "You are being used as a text-completion backend. Output ONLY the "
            "content the user prompt asks for (e.g. a single JSON object). Do not "
            "add any preamble, explanation, commentary, or Markdown code fences, "
            "and do not use any tools."
        ),
    ]
    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as error:
        raise ModelCallError(
            "The `claude` CLI was not found on PATH. Install Claude Code and run "
            "`claude login`, or use --backend nvidia.",
            reason="claude_cli_not_found",
        ) from error
    except subprocess.TimeoutExpired as error:
        raise ModelCallError(
            f"claude CLI timed out after {timeout_seconds}s.",
            reason="model_timeout",
        ) from error

    if completed.returncode != 0:
        raise ModelCallError(
            f"claude CLI exited {completed.returncode}: "
            f"{(completed.stderr or '').strip()[:500]}",
            reason="claude_cli_failed",
        )

    stdout = (completed.stdout or "").strip()
    if not stdout:
        raise ModelJSONError("claude CLI returned an empty response.")
    # --output-format json wraps the run; the model text is the "result" field.
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        # If the CLI emitted plain text instead of an envelope, use it directly.
        return stdout
    if isinstance(envelope, dict):
        if envelope.get("is_error"):
            raise ModelCallError(
                f"claude CLI reported an error: {envelope.get('result') or envelope}",
                reason="claude_cli_error",
            )
        result_text = envelope.get("result")
        if not result_text:
            raise ModelJSONError("claude CLI response had no 'result' text.")
        return str(result_text)
    raise ModelJSONError("claude CLI returned an unexpected response shape.")


def complete_via_codex_cli(
    prompt: str,
    *,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
) -> str:
    """Drive the OpenAI Codex CLI (`codex exec`) as a single-shot completion backend.

    Runs under the user's ChatGPT subscription with no per-token API cost. The
    completion instruction and prompt are fed on stdin (past shell ARG_MAX), the
    sandbox is read-only so the agent cannot run tools, and the final agent
    message is read from a temp file via `-o` (clean text, no event chatter).
    Requires `codex` on PATH and a prior `codex login`.
    """
    system = (
        "You are being used as a text-completion backend. Output ONLY the "
        "content the user prompt asks for (e.g. a single JSON object). Do not "
        "add any preamble, explanation, commentary, or Markdown code fences, and "
        "do not run any tools or shell commands."
    )
    with tempfile.NamedTemporaryFile(
        "r", suffix=".codex.txt", delete=False
    ) as handle:
        out_path = handle.name
    # `codex exec -` reads the prompt from stdin. Model-generated shell commands
    # are blocked by --sandbox read-only; mcp_servers={} skips MCP startup. We do
    # NOT use --dangerously-bypass-* so the agent stays confined to a pure answer.
    cmd = [
        "codex",
        "exec",
        "-",
        "-m",
        model,
        "-c",
        f"model_reasoning_effort={reasoning_effort}",
        "-c",
        "mcp_servers={}",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "-o",
        out_path,
    ]
    try:
        completed = subprocess.run(
            cmd,
            input=f"{system}\n\n{prompt}",
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as error:
        with contextlib.suppress(OSError):
            os.unlink(out_path)
        raise ModelCallError(
            "The `codex` CLI was not found on PATH. Install Codex and run "
            "`codex login`, or use a different --backend.",
            reason="codex_cli_not_found",
        ) from error
    except subprocess.TimeoutExpired as error:
        with contextlib.suppress(OSError):
            os.unlink(out_path)
        raise ModelCallError(
            f"codex CLI timed out after {timeout_seconds}s.",
            reason="model_timeout",
        ) from error

    try:
        if completed.returncode != 0:
            raise ModelCallError(
                f"codex CLI exited {completed.returncode}: "
                f"{(completed.stderr or '').strip()[:500]}",
                reason="codex_cli_failed",
            )
        try:
            result_text = Path(out_path).read_text(encoding="utf-8").strip()
        except OSError:
            result_text = ""
        if not result_text:
            raise ModelJSONError("codex CLI returned an empty final message.")
        return result_text
    finally:
        with contextlib.suppress(OSError):
            os.unlink(out_path)


def resolve_complete_fn(
    args: argparse.Namespace,
    injected: Callable[[str], str] | None,
    *,
    direct: bool,
) -> Callable[[str], str]:
    """Pick the model completer. Test-injected functions always win; otherwise
    dispatch on --backend. `direct` selects the raw OpenAI-like client (used by
    the v2 chapter path) over the LlamaIndex wrapper (v1)."""
    if injected is not None:
        return injected

    backend = getattr(args, "backend", "nvidia")
    timeout_seconds = int(getattr(args, "model_timeout_seconds", 180) or 180)

    if backend == "claude-cli":
        claude_model = getattr(args, "claude_model", DEFAULT_CLAUDE_MODEL)
        return lambda model_prompt: complete_via_claude_cli(
            model_prompt,
            model=claude_model,
            timeout_seconds=timeout_seconds,
        )

    if backend == "codex-cli":
        codex_model = getattr(args, "codex_model", DEFAULT_CODEX_MODEL)
        codex_effort = getattr(
            args, "codex_reasoning_effort", DEFAULT_CODEX_REASONING_EFFORT
        )
        return lambda model_prompt: complete_via_codex_cli(
            model_prompt,
            model=codex_model,
            reasoning_effort=codex_effort,
            timeout_seconds=timeout_seconds,
        )

    max_tokens = int(
        getattr(args, "model_max_tokens", DEFAULT_MODEL_MAX_TOKENS)
        or DEFAULT_MODEL_MAX_TOKENS
    )
    if direct:
        return lambda model_prompt: default_complete_direct_openai_like(
            model_prompt,
            model=args.nvidia_model,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    return lambda model_prompt: default_complete(
        model_prompt,
        model=args.nvidia_model,
        timeout_seconds=timeout_seconds,
    )


def complete_model_with_retries(
    *,
    prompt: str,
    args: argparse.Namespace,
    label: str,
    complete_fn: Callable[[str], str] | None,
) -> str:
    completer = resolve_complete_fn(args, complete_fn, direct=False)
    max_retries = max(0, int(getattr(args, "model_max_retries", 0) or 0))
    total_attempts = max_retries + 1
    last_error: Exception | None = None
    last_reason = "model_call_failed"

    for attempt in range(1, total_attempts + 1):
        try:
            with model_timeout(int(getattr(args, "model_timeout_seconds", 0) or 0)):
                return completer(prompt)
        except Exception as error:
            last_error = error
            last_reason = classify_model_error(error)
            if attempt >= total_attempts:
                break
            print(
                f"{label} model call failed ({last_reason}); "
                f"retry {attempt}/{max_retries}.",
                flush=True,
            )
            sleep_before_retry(args)

    raise ModelCallError(
        f"{label} model call failed after {total_attempts} attempt(s): {last_error}",
        reason=last_reason,
    )


def parse_model_json(raw_response: str, *, label: str, debug_path: Path | None = None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as error:
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(raw_response[start : end + 1])
            except json.JSONDecodeError:
                parsed = None
            else:
                if isinstance(parsed, dict):
                    return parsed
        if debug_path is not None:
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(raw_response, encoding="utf-8")
        raise ModelJSONError(
            f"Model response for {label} was not valid JSON: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise ModelJSONError(f"Model response for {label} must be a JSON object.")
    return parsed


def chapter_prompt(
    *,
    chapter: dict[str, Any],
    context: str,
    allowed_ids: list[str],
) -> str:
    return f"""
You are creating student-friendly learning materials from one book chapter.

Return valid JSON only. No Markdown. No code fences. Use only the supplied chapter context.
Cite only these allowed source chunk IDs: {allowed_ids}

Every key_terms, core_lessons, worked_examples, common_misconceptions, and practice_questions item must include source_chunk_ids.

Required JSON shape:
{{
  "chapter_title": "string",
  "estimated_study_time_minutes": 45,
  "chapter_summary": "string",
  "learning_objectives": ["string"],
  "key_terms": [{{"term": "string", "meaning": "string", "source_chunk_ids": ["string"]}}],
  "core_lessons": [{{"title": "string", "explanation": "string", "source_chunk_ids": ["string"]}}],
  "worked_examples": [{{"title": "string", "example": "string", "explanation": "string", "source_chunk_ids": ["string"]}}],
  "common_misconceptions": [{{"misconception": "string", "correction": "string", "source_chunk_ids": ["string"]}}],
  "practice_questions": [{{"question": "string", "answer": "string", "source_chunk_ids": ["string"]}}],
  "review_checklist": ["string"],
  "source_chunk_ids": ["string"]
}}

Chapter number: {chapter["chapter_number"]}
Detected chapter label: {chapter["chapter"]}

Chapter context:
{context}
""".strip()


def collect_source_ids(value: Any) -> list[str]:
    ids: list[str] = []
    if isinstance(value, dict):
        source_ids = value.get("source_chunk_ids")
        if isinstance(source_ids, list):
            ids.extend(str(item).strip() for item in source_ids if str(item).strip())
        for nested_value in value.values():
            if nested_value is source_ids:
                continue
            ids.extend(collect_source_ids(nested_value))
    elif isinstance(value, list):
        for item in value:
            ids.extend(collect_source_ids(item))
    return ids


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def validate_chapter_package(
    package: dict[str, Any],
    *,
    chapter_number: int,
    chapter_label: str,
    allowed_ids: list[str],
) -> dict[str, Any]:
    required_fields = [
        "chapter_title",
        "chapter_summary",
        "learning_objectives",
        "key_terms",
        "core_lessons",
        "worked_examples",
        "common_misconceptions",
        "practice_questions",
        "review_checklist",
        "source_chunk_ids",
    ]
    missing = [field for field in required_fields if field not in package]
    if missing:
        raise BookLearningMaterialsError(
            f"Chapter {chapter_number} model response is missing: {', '.join(missing)}"
        )

    allowed = set(allowed_ids)
    cited_ids = unique_preserve_order(collect_source_ids(package))
    invalid = [node_id for node_id in cited_ids if node_id not in allowed]
    if invalid:
        raise BookLearningMaterialsError(
            f"Chapter {chapter_number} cited unknown source chunk IDs: {', '.join(invalid)}"
        )

    normalized = {
        "chapter_number": chapter_number,
        "chapter_title": str(package.get("chapter_title") or chapter_label).strip(),
        "estimated_study_time_minutes": int(
            package.get("estimated_study_time_minutes") or 45
        ),
        "chapter_summary": str(package["chapter_summary"]).strip(),
        "learning_objectives": package["learning_objectives"],
        "key_terms": package["key_terms"],
        "core_lessons": package["core_lessons"],
        "worked_examples": package["worked_examples"],
        "common_misconceptions": package["common_misconceptions"],
        "practice_questions": package["practice_questions"],
        "review_checklist": package["review_checklist"],
        "source_chunk_ids": unique_preserve_order(package.get("source_chunk_ids") or cited_ids),
    }
    root_invalid = [
        node_id for node_id in normalized["source_chunk_ids"] if node_id not in allowed
    ]
    if root_invalid:
        raise BookLearningMaterialsError(
            f"Chapter {chapter_number} root source_chunk_ids include unknown IDs: "
            + ", ".join(root_invalid)
        )
    return normalized


def chapter_error_package(chapter: dict[str, Any], error: Exception) -> dict[str, Any]:
    return {
        "chapter_number": chapter["chapter_number"],
        "chapter_title": str(chapter["chapter"]),
        "estimated_study_time_minutes": 0,
        "chapter_summary": f"Chapter generation failed: {error}",
        "learning_objectives": [],
        "key_terms": [],
        "core_lessons": [],
        "worked_examples": [],
        "common_misconceptions": [],
        "practice_questions": [],
        "review_checklist": [],
        "source_chunk_ids": [],
        "generation_error": str(error),
    }


def truncate_string(value: Any, max_chars: int) -> str:
    text = normalize_whitespace(str(value or ""))
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def compact_chapter_context(chapters: list[dict[str, Any]], max_chars: int) -> str:
    blocks = []
    for chapter in chapters:
        block = {
            "chapter_number": chapter.get("chapter_number"),
            "chapter_title": chapter.get("chapter_title"),
            "chapter_summary": truncate_string(chapter.get("chapter_summary"), 800),
            "learning_objectives": chapter.get("learning_objectives"),
            "key_terms": [
                {
                    "term": item.get("term"),
                    "meaning": truncate_string(item.get("meaning"), 160),
                    "source_chunk_ids": item.get("source_chunk_ids") or [],
                }
                for item in chapter.get("key_terms", [])[:8]
                if isinstance(item, dict)
            ],
            "review_checklist": chapter.get("review_checklist"),
            "source_chunk_ids": (chapter.get("source_chunk_ids") or [])[:10],
        }
        blocks.append(json.dumps(block, ensure_ascii=False))
    context = "\n".join(blocks)
    return context[:max_chars].rstrip()


def book_synthesis_prompt(*, chapter_context: str, allowed_ids: list[str]) -> str:
    return f"""
You are synthesizing whole-book learning materials from chapter learning packages.

Return valid JSON only. No Markdown. No code fences.
Use only source chunk IDs present in the chapter package context.
Allowed source chunk IDs: {allowed_ids}
Do not repeat the full chapter packages. Only synthesize the book-level fields requested below.

Required JSON shape:
{{
  "book_overview": "string",
  "who_this_is_for": ["string"],
  "how_to_use_this_book": ["string"],
  "study_plan": [
    {{"week": 1, "focus": "string", "chapters": [1, 2], "activities": ["string"]}}
  ],
  "global_key_terms": [
    {{"term": "string", "meaning": "string", "chapter_numbers": [1], "source_chunk_ids": ["string"]}}
  ],
  "final_review": {{"summary": "string", "questions": ["string"]}}
}}

Chapter package context:
{chapter_context}
""".strip()


def repair_book_synthesis_prompt(*, raw_response: str, error: str) -> str:
    return f"""
Repair the malformed JSON response below.

Return valid JSON only. No Markdown. No code fences. No explanation.
Keep only this object shape:
{{
  "book_overview": "string",
  "who_this_is_for": ["string"],
  "how_to_use_this_book": ["string"],
  "study_plan": [
    {{"week": 1, "focus": "string", "chapters": [1, 2], "activities": ["string"]}}
  ],
  "global_key_terms": [
    {{"term": "string", "meaning": "string", "chapter_numbers": [1], "source_chunk_ids": ["string"]}}
  ],
  "final_review": {{"summary": "string", "questions": ["string"]}}
}}

JSON parsing error:
{error}

Malformed response:
{raw_response}
""".strip()


def validate_book_synthesis(
    synthesis: dict[str, Any],
    *,
    allowed_ids: list[str] | None = None,
) -> dict[str, Any]:
    required = [
        "book_overview",
        "who_this_is_for",
        "how_to_use_this_book",
        "study_plan",
        "global_key_terms",
        "final_review",
    ]
    missing = [field for field in required if field not in synthesis]
    if missing:
        raise BookLearningMaterialsError(
            "Book synthesis response is missing: " + ", ".join(missing)
        )
    if allowed_ids is not None:
        allowed = set(allowed_ids)
        cited_ids = unique_preserve_order(collect_source_ids(synthesis))
        invalid = [node_id for node_id in cited_ids if node_id not in allowed]
        if invalid:
            raise BookLearningMaterialsError(
                "Book synthesis cited unknown source chunk IDs: "
                + ", ".join(invalid)
            )
    return {field: synthesis[field] for field in required}


def deterministic_book_synthesis(chapter_packages: list[dict[str, Any]]) -> dict[str, Any]:
    chapter_count = len(chapter_packages)
    chapters_per_week = 1 if chapter_count <= 4 else 2
    study_plan = []
    for start in range(0, chapter_count, chapters_per_week):
        group = chapter_packages[start : start + chapters_per_week]
        chapter_numbers = [int(chapter["chapter_number"]) for chapter in group]
        chapter_titles = [str(chapter.get("chapter_title") or "") for chapter in group]
        study_plan.append(
            {
                "week": len(study_plan) + 1,
                "focus": " and ".join(chapter_titles),
                "chapters": chapter_numbers,
                "activities": [
                    "Read the chapter package.",
                    "Review the key terms.",
                    "Answer the practice questions.",
                    "Check the review checklist.",
                ],
            }
        )

    term_records: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for chapter in chapter_packages:
        chapter_number = chapter.get("chapter_number")
        for item in chapter.get("key_terms", []):
            if not isinstance(item, dict):
                continue
            term = normalize_whitespace(str(item.get("term") or ""))
            if not term:
                continue
            key = term.casefold()
            record = term_records.setdefault(
                key,
                {
                    "term": term,
                    "meaning": truncate_string(item.get("meaning"), 220),
                    "chapter_numbers": [],
                    "source_chunk_ids": [],
                    "_count": 0,
                    "_position": len(term_records),
                },
            )
            record["_count"] += 1
            if chapter_number not in record["chapter_numbers"]:
                record["chapter_numbers"].append(chapter_number)
            record["source_chunk_ids"] = unique_preserve_order(
                record["source_chunk_ids"]
                + [
                    str(node_id)
                    for node_id in item.get("source_chunk_ids", [])
                    if str(node_id).strip()
                ]
            )

    global_key_terms = []
    for record in sorted(
        term_records.values(),
        key=lambda item: (-int(item["_count"]), int(item["_position"])),
    )[:30]:
        global_key_terms.append(
            {
                "term": record["term"],
                "meaning": record["meaning"],
                "chapter_numbers": record["chapter_numbers"],
                "source_chunk_ids": record["source_chunk_ids"],
            }
        )

    chapter_titles = [
        f"Chapter {chapter.get('chapter_number')}: {chapter.get('chapter_title')}"
        for chapter in chapter_packages
    ]
    review_questions = [
        f"What are the most important ideas from {chapter.get('chapter_title')}?"
        for chapter in chapter_packages[:10]
    ]
    while len(review_questions) < 10 and chapter_packages:
        review_questions.append(
            "How do the chapter ideas connect across the source book?"
        )

    summary_parts = [
        truncate_string(chapter.get("chapter_summary"), 180)
        for chapter in chapter_packages[:8]
        if chapter.get("chapter_summary")
    ]

    return {
        "book_overview": (
            "These learning materials cover the main lessons detected from the "
            "source book and organize them into chapter-level study notes, key "
            "terms, examples, practice questions, and review activities."
        ),
        "who_this_is_for": [
            "Learners who want a structured study guide for the source book.",
            "Learners who want chapter-by-chapter lessons and review questions.",
            "Teachers or tutors who want a quick learning outline from the book.",
        ],
        "how_to_use_this_book": [
            "Study one chapter package at a time.",
            "Review the key terms before reading the full explanations.",
            "Answer the practice questions after each chapter.",
            "Use the final review to check your understanding across the book.",
        ],
        "study_plan": study_plan,
        "global_key_terms": global_key_terms,
        "final_review": {
            "summary": " ".join(summary_parts)
            or "Review the chapter summaries, key terms, practice questions, and checklists across the book.",
            "questions": review_questions[:10],
        },
    }


def detect_book_title(chunks: list[dict[str, Any]], fallback: str) -> str:
    for chunk in chunks:
        title = str(chunk.get("book_title") or "").strip()
        if title:
            return title
    return fallback


def source_chunk_record(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": chunk_node_id(chunk),
        "chapter_number": chunk.get("chapter_number"),
        "chapter": chunk.get("chapter"),
        "section": chunk.get("section"),
        "topic": chunk.get("topic"),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "text_preview": text_preview(str(chunk.get("text") or "")),
    }


def dedupe_source_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for chunk in chunks:
        node_id = chunk_node_id(chunk)
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        output.append(source_chunk_record(chunk))
    return output


def dedupe_source_chunk_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        node_id = str(record.get("node_id") or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        output.append(record)
    return output


def source_chunk_ids_from_records(records: list[dict[str, Any]]) -> list[str]:
    return unique_preserve_order(
        [
            str(record.get("node_id") or "").strip()
            for record in records
            if isinstance(record, dict) and str(record.get("node_id") or "").strip()
        ]
    )


def build_book_metadata(
    *,
    plan: dict[str, Any],
    clean_chunks: list[dict[str, Any]],
    detected_chapter_count: int,
) -> dict[str, Any]:
    return {
        "slug": plan["slug"],
        "source_pdf": str(plan["pdf_path"]),
        "title": detect_book_title(clean_chunks, plan["slug"]),
        "detected_chapter_count": detected_chapter_count,
        "detected_section_count": detected_section_count(clean_chunks),
    }


def build_generation_metadata(
    *,
    plan: dict[str, Any],
    args: argparse.Namespace,
    clean_chunks_path: Path,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.nvidia_model,
        "pipeline_version": PIPELINE_VERSION,
        "clean_index_id": plan["clean_index_id"],
        "clean_storage_dir": str(plan["clean_storage_dir"]),
        "clean_chunks_path": str(clean_chunks_path),
        "structure_resolution_path": plan["paths"]["structure_resolution"],
        "chapter_packages_path": str(plan["chapter_packages_json"]),
        "chapter_context_chars": args.chapter_context_chars,
        "book_synthesis_context_chars": args.book_synthesis_context_chars,
    }


def save_chapter_packages_file(
    *,
    path: Path,
    book_metadata: dict[str, Any],
    generation_metadata: dict[str, Any],
    chapter_packages: list[dict[str, Any]],
    source_chunks: list[dict[str, Any]],
    checkpoint: dict[str, Any] | None = None,
) -> None:
    write_json(
        path,
        {
            "book": book_metadata,
            "generation": generation_metadata,
            "chapter_packages": chapter_packages,
            "source_chunks": source_chunks,
            "checkpoint": checkpoint
            or {
                "status": "COMPLETE",
                "generated_chapter_count": len(chapter_packages),
                "target_chapter_count": len(chapter_packages),
                "last_completed_chapter_number": (
                    chapter_packages[-1].get("chapter_number") if chapter_packages else None
                ),
                "errors": [],
            },
        },
    )


def load_chapter_packages_file(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise BookLearningMaterialsError(
            f"Chapter packages file must contain a top-level object: {path}"
        )
    for field in ["book", "generation", "chapter_packages", "source_chunks"]:
        if field not in data:
            raise BookLearningMaterialsError(
                f"Chapter packages file is missing required field: {field}"
            )
    if not isinstance(data["book"], dict):
        raise BookLearningMaterialsError("chapter packages book must be an object.")
    if not isinstance(data["generation"], dict):
        raise BookLearningMaterialsError("chapter packages generation must be an object.")
    if not isinstance(data["chapter_packages"], list):
        raise BookLearningMaterialsError(
            "chapter packages file must contain a chapter_packages array."
        )
    if not isinstance(data["source_chunks"], list):
        raise BookLearningMaterialsError(
            "chapter packages file must contain a source_chunks array."
        )
    return data


def build_checkpoint(
    *,
    status: str,
    chapter_packages: list[dict[str, Any]],
    target_chapter_count: int,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    last_completed = None
    if chapter_packages:
        last_completed = chapter_packages[-1].get("chapter_number")
    return {
        "status": status,
        "generated_chapter_count": len(chapter_packages),
        "target_chapter_count": target_chapter_count,
        "last_completed_chapter_number": last_completed,
        "errors": errors,
    }


def checkpoint_error(chapter: dict[str, Any], error: Exception, *, reason: str | None = None) -> dict[str, Any]:
    return {
        "chapter_number": chapter.get("chapter_number"),
        "chapter": chapter.get("chapter"),
        "reason": reason or getattr(error, "reason", None) or classify_model_error(error),
        "message": str(error),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def write_chapter_checkpoint(
    *,
    path: Path,
    book_metadata: dict[str, Any],
    generation_metadata: dict[str, Any],
    chapter_packages: list[dict[str, Any]],
    source_chunks: list[dict[str, Any]],
    target_chapter_count: int,
    errors: list[dict[str, Any]],
    status: str,
) -> None:
    save_chapter_packages_file(
        path=path,
        book_metadata=book_metadata,
        generation_metadata=generation_metadata,
        chapter_packages=chapter_packages,
        source_chunks=source_chunks,
        checkpoint=build_checkpoint(
            status=status,
            chapter_packages=chapter_packages,
            target_chapter_count=target_chapter_count,
            errors=errors,
        ),
    )


def chapter_failure_message(
    *,
    chapter: dict[str, Any],
    error: Exception,
    checkpoint_path: Path,
    pdf_path: Path,
    output_path: Path,
) -> str:
    reason = getattr(error, "reason", None) or classify_model_error(error)
    return "\n".join(
        [
            "Chapter generation failed after retries.",
            f"Failed chapter: {chapter.get('chapter_number')}",
            f"Reason: {reason}",
            f"Checkpoint saved: {checkpoint_path}",
            "",
            "Resume with:",
            f'python generate_book_learning_materials.py "{pdf_path}" \\',
            f'  --resume-chapter-packages "{checkpoint_path}" \\',
            "  --resume-missing-chapters \\",
            f'  --output "{output_path}" \\',
            "  --overwrite",
        ]
    )


def audit_learning_materials(
    final: dict[str, Any],
    *,
    detected_chapter_count: int,
    max_chapters: int | None,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    required_top = {"book", "generation", "learning_materials", "source_chunks"}
    missing_top = sorted(required_top - set(final))
    if missing_top:
        failures.append("Missing top-level fields: " + ", ".join(missing_top))

    materials = final.get("learning_materials") or {}
    chapters = materials.get("chapters") if isinstance(materials, dict) else None
    source_chunks = final.get("source_chunks")

    if not isinstance(chapters, list) or not chapters:
        failures.append("learning_materials.chapters must be non-empty.")
        chapters = []
    if not isinstance(source_chunks, list) or not source_chunks:
        failures.append("source_chunks must be non-empty.")
        source_chunks = []

    source_ids = {
        chunk.get("node_id")
        for chunk in source_chunks
        if isinstance(chunk, dict) and chunk.get("node_id")
    }
    referenced_ids = unique_preserve_order(collect_source_ids(materials))
    invalid = [node_id for node_id in referenced_ids if node_id not in source_ids]
    if invalid:
        failures.append("Invalid source references: " + ", ".join(invalid))

    required_chapter_fields = [
        "chapter_number",
        "chapter_title",
        "chapter_summary",
        "learning_objectives",
        "key_terms",
        "core_lessons",
        "practice_questions",
        "source_chunk_ids",
    ]
    for chapter in chapters:
        if not isinstance(chapter, dict):
            failures.append("Each chapter must be an object.")
            continue
        missing = [field for field in required_chapter_fields if field not in chapter]
        if missing:
            failures.append(
                f"Chapter {chapter.get('chapter_number')} missing fields: "
                + ", ".join(missing)
            )

    partial_generation = max_chapters is not None and len(chapters) < detected_chapter_count
    if max_chapters is None and len(chapters) != detected_chapter_count:
        failures.append(
            f"Generated chapter count {len(chapters)} does not match detected chapter count {detected_chapter_count}."
        )
    if partial_generation:
        warnings.append("partial_generation true because --max-chapters was used.")

    status = "FAIL" if failures else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return {
        "status": status,
        "chapter_count": len(chapters),
        "source_chunk_count": len(source_chunks),
        "invalid_source_reference_count": len(invalid),
        "partial_generation": partial_generation,
        "warnings": warnings,
        "failures": failures,
    }


def generate_chapter_packages(
    chapters: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    plan: dict[str, Any],
    book_metadata: dict[str, Any],
    generation_metadata: dict[str, Any],
    existing_packages: list[dict[str, Any]] | None = None,
    existing_source_chunks: list[dict[str, Any]] | None = None,
    existing_errors: list[dict[str, Any]] | None = None,
    output_path: Path,
    complete_fn: Callable[[str], str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    packages: list[dict[str, Any]] = list(existing_packages or [])
    source_chunk_records: list[dict[str, Any]] = dedupe_source_chunk_records(
        list(existing_source_chunks or [])
    )
    errors: list[dict[str, Any]] = list(existing_errors or [])
    warnings: list[str] = []

    selected_chapters = chapters[: args.max_chapters] if args.max_chapters else chapters
    target_chapter_count = len(selected_chapters)
    existing_chapter_numbers = {
        int(package["chapter_number"])
        for package in packages
        if package.get("chapter_number") is not None
    }

    for chapter in selected_chapters:
        chapter_number = int(chapter["chapter_number"])
        if chapter_number in existing_chapter_numbers:
            continue

        try:
            context, context_chunks = build_chapter_context(
                chapter,
                max_chars=args.chapter_context_chars,
            )
            allowed_ids = [chunk_node_id(chunk) for chunk in context_chunks]
            raw_response_path = output_path.parent / (
                f"{plan['slug']}.chapter_{chapter_number}.raw_response.txt"
            )
            prompt = chapter_prompt(
                chapter=chapter,
                context=context,
                allowed_ids=allowed_ids,
            )
            max_retries = max(0, int(args.model_max_retries or 0))
            total_attempts = max_retries + 1
            last_error: Exception | None = None

            for attempt in range(1, total_attempts + 1):
                raw = ""
                try:
                    raw = complete_model_with_retries(
                        prompt=prompt,
                        args=args,
                        label=f"chapter {chapter_number}",
                        complete_fn=complete_fn,
                    )
                    parsed = parse_model_json(
                        raw,
                        label=f"chapter {chapter_number}",
                        debug_path=raw_response_path,
                    )
                    package = validate_chapter_package(
                        parsed,
                        chapter_number=chapter_number,
                        chapter_label=chapter["chapter"],
                        allowed_ids=allowed_ids,
                    )
                    break
                except ModelCallError:
                    raise
                except ModelJSONError as error:
                    last_error = error
                    if raw:
                        raw_response_path.parent.mkdir(parents=True, exist_ok=True)
                        raw_response_path.write_text(raw, encoding="utf-8")
                    if attempt >= total_attempts:
                        raise
                    print(
                        f"Chapter {chapter_number} generation failed; "
                        f"retry {attempt}/{max_retries}.",
                        flush=True,
                    )
                    sleep_before_retry(args)
                except BookLearningMaterialsError:
                    raise
            else:
                raise last_error or BookLearningMaterialsError(
                    f"Chapter {chapter_number} generation failed."
                )

            packages.append(package)
            source_chunk_records = dedupe_source_chunk_records(
                source_chunk_records
                + [source_chunk_record(chunk) for chunk in context_chunks]
            )
            write_chapter_checkpoint(
                path=plan["chapter_packages_json"],
                book_metadata=book_metadata,
                generation_metadata=generation_metadata,
                chapter_packages=packages,
                source_chunks=source_chunk_records,
                target_chapter_count=target_chapter_count,
                errors=errors,
                status="IN_PROGRESS",
            )
            print(f"Generated chapter {chapter_number}: {packages[-1]['chapter_title']}")
        except Exception as error:
            error_record = checkpoint_error(chapter, error)
            errors.append(error_record)
            write_chapter_checkpoint(
                path=plan["chapter_packages_json"],
                book_metadata=book_metadata,
                generation_metadata=generation_metadata,
                chapter_packages=packages,
                source_chunks=source_chunk_records,
                target_chapter_count=target_chapter_count,
                errors=errors,
                status="IN_PROGRESS",
            )
            if not args.continue_on_chapter_error:
                raise BookLearningMaterialsError(
                    chapter_failure_message(
                        chapter=chapter,
                        error=error,
                        checkpoint_path=plan["chapter_packages_json"],
                        pdf_path=plan["pdf_path"],
                        output_path=plan["output_json"],
                    )
                ) from error
            packages.append(chapter_error_package(chapter, error))
            existing_chapter_numbers.add(chapter_number)
            warnings.append(
                f"Chapter {chapter_number} generation failed: {error}"
            )
            if "chapter_generation_errors_present" not in warnings:
                warnings.append("chapter_generation_errors_present")
            print(f"Chapter {chapter_number} generation failed: {error}")

    write_chapter_checkpoint(
        path=plan["chapter_packages_json"],
        book_metadata=book_metadata,
        generation_metadata=generation_metadata,
        chapter_packages=packages,
        source_chunks=source_chunk_records,
        target_chapter_count=target_chapter_count,
        errors=errors,
        status="COMPLETE",
    )
    return packages, source_chunk_records, warnings, errors


def generate_book_synthesis(
    chapter_packages: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
    complete_fn: Callable[[str], str] | None,
    output_path: Path,
    raw_response_path: Path,
    allowed_ids: list[str],
) -> tuple[dict[str, Any], list[str]]:
    raw = complete_model_with_retries(
        prompt=book_synthesis_prompt(
            chapter_context=compact_chapter_context(
                chapter_packages,
                args.book_synthesis_context_chars,
            ),
            allowed_ids=allowed_ids,
        ),
        args=args,
        label="book synthesis",
        complete_fn=complete_fn,
    )
    warnings: list[str] = []
    try:
        parsed = parse_model_json(
            raw,
            label="book synthesis",
            debug_path=raw_response_path,
        )
    except BookLearningMaterialsError as initial_error:
        raw_response_path.parent.mkdir(parents=True, exist_ok=True)
        raw_response_path.write_text(raw, encoding="utf-8")
        warnings.append("book_synthesis_model_json_invalid_repair_attempted")

        repaired_raw = complete_model_with_retries(
            prompt=repair_book_synthesis_prompt(
                raw_response=raw,
                error=str(initial_error),
            ),
            args=args,
            label="book synthesis repair",
            complete_fn=complete_fn,
        )
        try:
            repaired = parse_model_json(
                repaired_raw,
                label="book synthesis repair",
                debug_path=raw_response_path.with_name(
                    f"{raw_response_path.stem}.repair.raw_response.txt"
                ),
            )
        except BookLearningMaterialsError:
            warnings.append("book_synthesis_model_failed_used_deterministic_fallback")
            fallback = deterministic_book_synthesis(chapter_packages)
            return validate_book_synthesis(fallback, allowed_ids=allowed_ids), warnings
        warnings.append("book_synthesis_model_json_repaired")
        return validate_book_synthesis(repaired, allowed_ids=allowed_ids), warnings

    return validate_book_synthesis(parsed, allowed_ids=allowed_ids), warnings


def build_report(
    *,
    plan: dict[str, Any],
    preparation_results: list[dict[str, Any]],
    final: dict[str, Any] | None,
    chapter_packages: list[dict[str, Any]] | None = None,
) -> str:
    audit = (final or {}).get("audit") or {}
    source_chunks = (final or {}).get("source_chunks") or []
    chapters = chapter_packages or ((final or {}).get("learning_materials") or {}).get("chapters") or []
    lines = [
        "WHOLE BOOK LEARNING MATERIALS REPORT",
        f"Input PDF: {plan['pdf_path']}",
        f"Slug: {plan['slug']}",
        f"Output JSON: {plan['output_json']}",
        f"Output report: {plan['output_report']}",
        f"Clean chunks path: {plan['paths']['clean_chunks']}",
        f"Clean index ID: {plan['clean_index_id']}",
        f"Clean storage dir: {plan['clean_storage_dir']}",
        "",
        "PREPARATION STEPS",
    ]
    for result in preparation_results:
        detail = f" ({result['reason']})" if result.get("reason") else ""
        lines.append(f"- {result['name']}: {result['status']}{detail}")
    lines.extend(
        [
            "",
            f"Chapter count detected: {(final or {}).get('book', {}).get('detected_chapter_count')}",
            f"Chapter count generated: {len(chapters)}",
            f"Source chunk count: {len(source_chunks)}",
            f"Audit status: {audit.get('status')}",
            "",
            "WARNINGS",
        ]
    )
    warnings = audit.get("warnings") or []
    lines.extend([f"- {warning}" for warning in warnings] or ["- None"])
    lines.append("")
    lines.append("FAILURES")
    failures = audit.get("failures") or []
    lines.extend([f"- {failure}" for failure in failures] or ["- None"])
    lines.append("")
    lines.append("CHAPTERS")
    for chapter in chapters:
        lines.append(
            f"- Chapter {chapter.get('chapter_number')}: {chapter.get('chapter_title')} "
            f"({len(chapter.get('source_chunk_ids') or [])} cited chunks)"
        )
    return "\n".join(lines) + "\n"


def v2_checkpoint_failure_message(
    *,
    chapter: dict[str, Any],
    error: Exception,
    checkpoint_path: Path,
    pdf_path: Path,
    output_path: Path,
    selected_chapter_numbers: list[int],
) -> str:
    chapter_flags = "\n".join(
        f"  --chapter-number {number} \\" for number in selected_chapter_numbers
    )
    return "\n".join(
        [
            "Targeted v2 chapter generation failed after one repair attempt.",
            f"Failed chapter: {chapter.get('chapter_number')}",
            f"Reason: {error}",
            f"Checkpoint saved: {checkpoint_path}",
            "",
            "Resume with:",
            f'python generate_book_learning_materials.py "{pdf_path}" \\',
            f"  --schema-version {v2.BOOK_LEARNING_MATERIALS_V2_SCHEMA_VERSION} \\",
            chapter_flags,
            f'  --chapter-packages-output "{checkpoint_path}" \\',
            f'  --resume-chapter-packages "{checkpoint_path}" \\',
            "  --resume-missing-chapters \\",
            f'  --output "{output_path}" \\',
            "  --model-timeout-seconds 180 \\",
            "  --model-max-retries 2",
        ]
    )


def validate_v2_selected_chapter_candidate(
    *,
    candidate: dict[str, Any],
    chapter: dict[str, Any],
    plan: dict[str, Any],
    args: argparse.Namespace,
    clean_chunks_path: Path,
    clean_chunks_lookup: dict[str, dict[str, Any]],
    source_chunks: list[dict[str, Any]],
    selected_chapter_numbers: list[int],
    book_title: str,
) -> dict[str, Any]:
    book = v2.build_v2_book(
        slug=plan["slug"],
        title=book_title,
        source_pdf=str(plan["pdf_path"]),
        model=args.nvidia_model,
        selected_chapter_numbers=selected_chapter_numbers,
        clean_chunks_path=clean_chunks_path,
        chapter_packages=[candidate],
        source_chunks=source_chunks,
    )
    audit = v2.validate_v2_book_dict(
        book=book,
        clean_chunks_lookup=clean_chunks_lookup,
        clean_chunks_path=clean_chunks_path,
        book_file=plan["output_json"].with_name(
            f".chapter_{int(chapter['chapter_number']):02d}.candidate.json"
        ),
    )
    substantive_errors = v2.validate_substantive_v2_chapter(
        candidate=candidate,
        allowed_ids=[
            str(record.get("node_id"))
            for record in source_chunks
            if str(record.get("node_id") or "").strip()
        ],
    )
    return v2.merge_substantive_errors(audit, substantive_errors)


def generate_v2_targeted_book_learning_materials(
    args: argparse.Namespace,
    *,
    complete_fn: Callable[[str], str] | None = None,
    run_subprocess: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any] | None:
    plan = build_plan(args)
    checkpoint_path = (
        Path(args.chapter_packages_output)
        if getattr(args, "chapter_packages_output", None)
        else None
    )
    if checkpoint_path is None:
        raise BookLearningMaterialsError(
            "--chapter-packages-output is required for targeted v2 generation."
        )

    if not getattr(args, "chapter_number", None):
        raise BookLearningMaterialsError(
            "Full-book v2 generation is deferred to Step 34C.4. "
            "Provide one or more --chapter-number values."
        )

    contract_audit_json, contract_audit_txt = v2.derive_contract_audit_paths(
        plan["output_json"]
    )
    invalid_dir = v2.derive_invalid_candidate_dir(plan["output_json"])
    clean_chunks_path = Path(plan["paths"]["clean_chunks"])

    if args.prepare_only and getattr(args, "resume_chapter_packages", None):
        raise BookLearningMaterialsError(
            "--prepare-only cannot be combined with --resume-chapter-packages."
        )

    print("Whole-book learning materials plan")
    print(f"Schema version: {v2.BOOK_LEARNING_MATERIALS_V2_SCHEMA_VERSION}")
    print(f"Selection mode: {v2.V2_SELECTION_MODE_CHAPTERS}")
    print(f"Input PDF: {plan['pdf_path']}")
    print(f"Slug: {plan['slug']}")
    print(f"Output JSON: {plan['output_json']}")
    print(f"Checkpoint path: {checkpoint_path}")
    print(f"Contract audit JSON: {contract_audit_json}")
    print(f"Contract audit report: {contract_audit_txt}")
    print(f"Clean chunks path: {clean_chunks_path}")
    print(f"Book synthesis performed: no")

    if args.dry_run:
        if not clean_chunks_path.exists():
            print("Clean chunks are missing; preparation would be required before live generation.")
            print("Model calls made: 0")
            print("Dry run complete: no files written")
            return None
        clean_chunks = load_clean_chunks(clean_chunks_path)
        chapters = group_chunks_by_chapter(clean_chunks)
        selected_chapters = v2.select_chapters_by_number(
            chapters,
            list(args.chapter_number or []),
        )
        selected_numbers = [
            int(chapter["chapter_number"]) for chapter in selected_chapters
        ]
        selected_chunk_count = sum(
            len(chapter.get("chunks") or []) for chapter in selected_chapters
        )
        print(f"Detected chapter count: {len(chapters)}")
        print(
            "Selected chapters: "
            + ", ".join(str(number) for number in selected_numbers)
        )
        print(f"Selected chapter count: {len(selected_chapters)}")
        print(f"Selected source chunk count: {selected_chunk_count}")
        print(f"Planned chapter model calls: {len(selected_chapters)}")
        print("Model calls made: 0")
        print("Dry run complete: no files written")
        return None

    if not args.overwrite and not getattr(args, "resume_chapter_packages", None):
        existing = [
            path
            for path in [
                plan["output_json"],
                checkpoint_path,
                contract_audit_json,
                contract_audit_txt,
            ]
            if path.exists()
        ]
        if existing:
            raise BookLearningMaterialsError(
                "Targeted v2 output already exists. Use --overwrite to replace: "
                + ", ".join(str(path) for path in existing)
            )
    elif (
        not args.overwrite
        and getattr(args, "resume_chapter_packages", None)
        and plan["output_json"].exists()
    ):
        raise BookLearningMaterialsError(
            f"Output file already exists: {plan['output_json']}\n"
            "Pass --overwrite to replace it."
        )

    preparation_results = run_preparation(plan, args, run_subprocess=run_subprocess)
    if args.prepare_only:
        print("")
        print("Prepare only completed. NVIDIA not called.")
        print(f"Clean chunks: {clean_chunks_path}")
        return None

    clean_chunks = load_clean_chunks(clean_chunks_path)
    clean_chunks_lookup, clean_errors = v2.load_contract_clean_chunk_lookup(clean_chunks_path)
    if clean_errors:
        print(
            "Clean chunk prevalidation warnings ignored for targeted v2 generation: "
            + "; ".join(
                f"{error.get('code')} {error.get('json_path')}: {error.get('message')}"
                for error in clean_errors[:5]
            )
        )
    clean_hash = v2.clean_chunks_sha256(clean_chunks_path)
    chapters = group_chunks_by_chapter(clean_chunks)
    if not chapters:
        raise BookLearningMaterialsError("No non-front-matter chapters found in clean chunks.")

    selected_chapters = v2.select_chapters_by_number(
        chapters,
        list(args.chapter_number or []),
    )
    selected_numbers = [int(chapter["chapter_number"]) for chapter in selected_chapters]
    selected_chunk_count = sum(
        len(chapter.get("chunks") or []) for chapter in selected_chapters
    )
    book_title = detect_book_title(clean_chunks, plan["slug"])

    print(f"Detected chapter count: {len(chapters)}")
    print("Selected chapters: " + ", ".join(str(number) for number in selected_numbers))
    print(f"Selected chapter count: {len(selected_chapters)}")
    print(f"Selected source chunk count: {selected_chunk_count}")
    print(f"Planned chapter model calls: {len(selected_chapters)}")

    chapter_packages: list[dict[str, Any]] = []
    failed_chapters: list[dict[str, Any]] = []
    model_call_count = 0
    repair_call_count = 0

    resume_path = (
        Path(args.resume_chapter_packages)
        if getattr(args, "resume_chapter_packages", None)
        else None
    )
    if resume_path is not None:
        checkpoint = v2.load_v2_checkpoint(resume_path)
        v2.validate_resume_checkpoint(
            checkpoint=checkpoint,
            source_pdf=str(plan["pdf_path"]),
            clean_chunks_path=clean_chunks_path,
            clean_chunks_hash=clean_hash,
            model=args.nvidia_model,
            selected_chapter_numbers=selected_numbers,
        )
        chapter_packages = list(checkpoint.get("chapter_packages") or [])
        failed_chapters = list(checkpoint.get("failed_chapters") or [])
        model_call_count = int(checkpoint.get("model_call_count") or 0)
        repair_call_count = int(checkpoint.get("repair_call_count") or 0)
        completed_numbers = {
            int(package["chapter_number"])
            for package in chapter_packages
            if isinstance(package, dict) and package.get("chapter_number") is not None
        }
        if completed_numbers != set(selected_numbers) and not args.resume_missing_chapters:
            raise BookLearningMaterialsError(
                "V2 checkpoint is incomplete. Pass --resume-missing-chapters to generate missing chapters."
            )
        print("")
        print(f"Loaded v2 checkpoint: {resume_path}")
        print(f"Completed chapters loaded: {len(chapter_packages)}")

    def write_checkpoint(status: str) -> None:
        checkpoint = v2.build_v2_checkpoint(
            status=status,
            source_pdf=str(plan["pdf_path"]),
            clean_chunks_path=clean_chunks_path,
            clean_chunks_hash=clean_hash,
            model=args.nvidia_model,
            selected_chapter_numbers=selected_numbers,
            chapter_packages=chapter_packages,
            failed_chapters=failed_chapters,
            model_call_count=model_call_count,
            repair_call_count=repair_call_count,
        )
        v2.write_v2_checkpoint(checkpoint_path, checkpoint)

    completed_chapter_numbers = {
        int(package["chapter_number"])
        for package in chapter_packages
        if isinstance(package, dict) and package.get("chapter_number") is not None
    }
    v2_complete_fn = resolve_complete_fn(args, complete_fn, direct=True)

    for chapter in selected_chapters:
        chapter_number = int(chapter["chapter_number"])
        if chapter_number in completed_chapter_numbers:
            continue

        context_json, context_chunks, allowed_ids = v2.chapter_context_blocks(chapter)
        source_records = [
            v2.source_chunk_record(chunk)
            for chunk in context_chunks
        ]
        prompt = v2.build_v2_chapter_prompt(
            chapter=chapter,
            context_json=context_json,
            allowed_ids=allowed_ids,
            model=args.nvidia_model,
        )
        raw_response: str | None = None
        parsed_candidate: dict[str, Any] | None = None
        initial_audit: dict[str, Any] | None = None

        try:
            model_call_count += 1
            raw_response = complete_model_with_retries(
                prompt=prompt,
                args=args,
                label=f"v2 chapter {chapter_number}",
                complete_fn=v2_complete_fn,
            )
            contract_errors: list[dict[str, Any]] = []
            try:
                parsed = parse_model_json(raw_response, label=f"v2 chapter {chapter_number}")
                parsed_candidate = v2.extract_chapter_candidate(parsed)
                if not isinstance(parsed_candidate, dict):
                    raise BookLearningMaterialsError(
                        f"Chapter {chapter_number} model response must be a JSON object."
                    )
                parsed_candidate = v2.normalize_v2_candidate_for_contract(
                    parsed_candidate,
                    allowed_ids=allowed_ids,
                    clean_chunks_lookup=clean_chunks_lookup,
                )
                initial_audit = validate_v2_selected_chapter_candidate(
                    candidate=parsed_candidate,
                    chapter=chapter,
                    plan=plan,
                    args=args,
                    clean_chunks_path=clean_chunks_path,
                    clean_chunks_lookup=clean_chunks_lookup,
                    source_chunks=source_records,
                    selected_chapter_numbers=selected_numbers,
                    book_title=book_title,
                )
                contract_errors = initial_audit.get("errors") or []
            except ModelJSONError as error:
                contract_errors = [
                    {
                        "code": "MODEL_JSON_INVALID",
                        "json_path": "$",
                        "message": str(error),
                    }
                ]
                initial_audit = {"status": "FAIL", "errors": contract_errors}

            if initial_audit["status"] != "PASS":
                v2.save_failed_candidate_artifacts(
                    invalid_dir=invalid_dir,
                    chapter_number=chapter_number,
                    stage="initial",
                    raw_response=raw_response,
                    parsed_candidate=parsed_candidate,
                    contract_errors=contract_errors,
                )
                repair_call_count += 1
                model_call_count += 1
                repair_raw = complete_model_with_retries(
                    prompt=v2.build_v2_repair_prompt(
                        chapter=chapter,
                        context_json=context_json,
                        allowed_ids=allowed_ids,
                        raw_response=raw_response,
                        invalid_candidate=parsed_candidate,
                        contract_errors=contract_errors,
                        model=args.nvidia_model,
                    ),
                    args=args,
                    label=f"v2 chapter {chapter_number} repair",
                    complete_fn=v2_complete_fn,
                )
                repaired_parsed = parse_model_json(
                    repair_raw,
                    label=f"v2 chapter {chapter_number} repair",
                )
                repaired_candidate = v2.extract_chapter_candidate(repaired_parsed)
                if not isinstance(repaired_candidate, dict):
                    raise BookLearningMaterialsError(
                        f"Chapter {chapter_number} repaired response must be a JSON object."
                    )
                repaired_candidate = v2.normalize_v2_candidate_for_contract(
                    repaired_candidate,
                    allowed_ids=allowed_ids,
                    clean_chunks_lookup=clean_chunks_lookup,
                )
                repaired_audit = validate_v2_selected_chapter_candidate(
                    candidate=repaired_candidate,
                    chapter=chapter,
                    plan=plan,
                    args=args,
                    clean_chunks_path=clean_chunks_path,
                    clean_chunks_lookup=clean_chunks_lookup,
                    source_chunks=source_records,
                    selected_chapter_numbers=selected_numbers,
                    book_title=book_title,
                )
                if repaired_audit["status"] != "PASS":
                    v2.save_failed_candidate_artifacts(
                        invalid_dir=invalid_dir,
                        chapter_number=chapter_number,
                        stage="repair",
                        raw_response=repair_raw,
                        parsed_candidate=repaired_candidate,
                        contract_errors=repaired_audit.get("errors") or [],
                    )
                    raise BookLearningMaterialsError(
                        v2.contract_error_message(chapter_number, repaired_audit)
                    )
                parsed_candidate = repaired_candidate

            chapter_packages.append(parsed_candidate)
            completed_chapter_numbers.add(chapter_number)
            write_checkpoint("IN_PROGRESS")
            print(
                f"Generated v2 chapter {chapter_number}: "
                f"{parsed_candidate.get('chapter_title')}"
            )
        except Exception as error:
            failure = {
                "chapter_number": chapter_number,
                "chapter": chapter.get("chapter"),
                "message": str(error),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            failed_chapters.append(failure)
            write_checkpoint("IN_PROGRESS")
            raise BookLearningMaterialsError(
                v2_checkpoint_failure_message(
                    chapter=chapter,
                    error=error,
                    checkpoint_path=checkpoint_path,
                    pdf_path=plan["pdf_path"],
                    output_path=plan["output_json"],
                    selected_chapter_numbers=selected_numbers,
                )
            ) from error

    chapter_packages.sort(
        key=lambda package: selected_numbers.index(int(package["chapter_number"]))
    )
    source_records = []
    for chapter in selected_chapters:
        for chunk in chapter.get("chunks") or []:
            source_records.append(v2.source_chunk_record(chunk))
    source_records = v2.dedupe_source_chunk_records(source_records)

    final = v2.build_v2_book(
        slug=plan["slug"],
        title=book_title,
        source_pdf=str(plan["pdf_path"]),
        model=args.nvidia_model,
        selected_chapter_numbers=selected_numbers,
        clean_chunks_path=clean_chunks_path,
        chapter_packages=chapter_packages,
        source_chunks=source_records,
        audit_status="PENDING",
    )
    final_audit = v2.validate_v2_book_dict(
        book=final,
        clean_chunks_lookup=clean_chunks_lookup,
        clean_chunks_path=clean_chunks_path,
        book_file=plan["output_json"],
    )
    if final_audit["status"] != "PASS":
        v2.atomic_write_json(contract_audit_json, final_audit)
        v2.atomic_write_text(
            contract_audit_txt,
            v2.format_v2_contract_report(final_audit, contract_audit_json),
        )
        raise BookLearningMaterialsError(
            "Final targeted v2 book failed contract validation. "
            f"Audit written: {contract_audit_json}"
        )

    final["audit"] = {
        "status": "PASS",
        "contract_status": "PASS",
        "contract_audit_path": str(contract_audit_json),
        "contract_report_path": str(contract_audit_txt),
    }
    final_audit = v2.validate_v2_book_dict(
        book=final,
        clean_chunks_lookup=clean_chunks_lookup,
        clean_chunks_path=clean_chunks_path,
        book_file=plan["output_json"],
    )
    if final_audit["status"] != "PASS":
        v2.atomic_write_json(contract_audit_json, final_audit)
        v2.atomic_write_text(
            contract_audit_txt,
            v2.format_v2_contract_report(final_audit, contract_audit_json),
        )
        raise BookLearningMaterialsError(
            "Final targeted v2 book failed contract validation after audit stamping. "
            f"Audit written: {contract_audit_json}"
        )

    v2.atomic_write_json(contract_audit_json, final_audit)
    v2.atomic_write_text(
        contract_audit_txt,
        v2.format_v2_contract_report(final_audit, contract_audit_json),
    )
    write_checkpoint("COMPLETE")
    v2.atomic_write_json(plan["output_json"], final)

    print("")
    print("Targeted v2 whole-book learning materials generated.")
    print(f"Selected chapter count: {len(selected_numbers)}")
    print(f"Completed chapter count: {len(chapter_packages)}")
    print(f"Model calls: {model_call_count}")
    print(f"Repair calls: {repair_call_count}")
    print("Checkpoint status: COMPLETE")
    print(f"Contract status: {final_audit['status']}")
    print(f"Output JSON: {plan['output_json']}")
    print(f"Chapter packages checkpoint: {checkpoint_path}")
    print(f"Contract audit JSON: {contract_audit_json}")
    print(f"Contract audit report: {contract_audit_txt}")
    print(f"Preparation steps recorded: {len(preparation_results)}")
    return final


def print_plan(plan: dict[str, Any], args: argparse.Namespace) -> None:
    print("Whole-book learning materials plan")
    print(f"Input PDF: {plan['pdf_path']}")
    print(f"Slug: {plan['slug']}")
    print(f"Output JSON: {plan['output_json']}")
    print(f"Output report: {plan['output_report']}")
    print("")
    print("Derived paths:")
    for key, value in plan["paths"].items():
        if key == "slug":
            continue
        if key.endswith("_id"):
            print(f"- {key}: {value}")
            continue
        path = Path(value) if isinstance(value, str) else value
        exists = "exists" if path.exists() else "missing"
        print(f"- {key}: {value} [{exists}]")
    print("")
    print(f"Dry run: {args.dry_run}")
    print(f"Prepare only: {args.prepare_only}")
    print(f"Rebuild artifacts: {args.rebuild_artifacts}")
    print(f"Overwrite index: {args.overwrite_index}")
    print(f"Model timeout seconds: {args.model_timeout_seconds}")
    print(f"Model max retries: {args.model_max_retries}")
    print(f"Model retry backoff seconds: {args.model_retry_backoff_seconds}")
    if getattr(args, "resume_chapter_packages", None):
        print(f"Resume chapter packages: {args.resume_chapter_packages}")
        print(f"Resume missing chapters: {args.resume_missing_chapters}")
    if args.dry_run:
        print("")
        print("No files written. NVIDIA not called.")


def generate_book_learning_materials(
    args: argparse.Namespace,
    *,
    complete_fn: Callable[[str], str] | None = None,
    run_subprocess: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any] | None:
    plan = build_plan(args)
    schema_version = getattr(args, "schema_version", PIPELINE_VERSION)

    if not plan["pdf_path"].exists():
        raise BookLearningMaterialsError(f"Input PDF does not exist: {plan['pdf_path']}")
    if not plan["pdf_path"].is_file():
        raise BookLearningMaterialsError(f"Input PDF path is not a file: {plan['pdf_path']}")
    if args.max_chapters is not None and args.max_chapters < 1:
        raise BookLearningMaterialsError("--max-chapters must be at least 1.")
    if args.chapter_context_chars < 1000:
        raise BookLearningMaterialsError("--chapter-context-chars must be at least 1000.")
    if args.book_synthesis_context_chars < 1000:
        raise BookLearningMaterialsError(
            "--book-synthesis-context-chars must be at least 1000."
        )
    if args.prepare_only and getattr(args, "resume_chapter_packages", None):
        raise BookLearningMaterialsError(
            "--prepare-only cannot be combined with --resume-chapter-packages."
        )
    if args.resume_missing_chapters and not getattr(args, "resume_chapter_packages", None):
        raise BookLearningMaterialsError(
            "--resume-missing-chapters requires --resume-chapter-packages."
        )
    if args.model_timeout_seconds < 1:
        raise BookLearningMaterialsError("--model-timeout-seconds must be at least 1.")
    if args.model_max_retries < 0:
        raise BookLearningMaterialsError("--model-max-retries must be 0 or greater.")
    if args.model_retry_backoff_seconds < 0:
        raise BookLearningMaterialsError(
            "--model-retry-backoff-seconds must be 0 or greater."
        )
    if schema_version not in {
        PIPELINE_VERSION,
        v2.BOOK_LEARNING_MATERIALS_V2_SCHEMA_VERSION,
    }:
        raise BookLearningMaterialsError(f"Unsupported --schema-version: {schema_version}")

    if schema_version == v2.BOOK_LEARNING_MATERIALS_V2_SCHEMA_VERSION:
        try:
            return generate_v2_targeted_book_learning_materials(
                args,
                complete_fn=complete_fn,
                run_subprocess=run_subprocess,
            )
        except v2.V2GenerationError as error:
            raise BookLearningMaterialsError(str(error)) from error

    if args.dry_run:
        print_plan(plan, args)
        return None

    if plan["output_json"].exists() and not args.overwrite and not args.prepare_only:
        raise BookLearningMaterialsError(
            f"Output file already exists: {plan['output_json']}\n"
            "Pass --overwrite to replace it."
        )

    print_plan(plan, args)
    resume_path = (
        Path(args.resume_chapter_packages)
        if getattr(args, "resume_chapter_packages", None)
        else None
    )

    if resume_path is not None and not args.resume_missing_chapters:
        if not resume_path.exists():
            raise BookLearningMaterialsError(
                f"Chapter packages file does not exist: {resume_path}"
            )
        preparation_results = [
            {
                "name": "prepare",
                "status": "skipped",
                "reason": "--resume-chapter-packages",
            },
            {
                "name": "chapter_generation",
                "status": "skipped",
                "reason": "--resume-chapter-packages",
            },
        ]
        package_file = load_chapter_packages_file(resume_path)
        book_metadata = dict(package_file["book"])
        generation_metadata = dict(package_file["generation"])
        generation_metadata.update(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": args.nvidia_model,
                "book_synthesis_context_chars": args.book_synthesis_context_chars,
                "resumed_from_chapter_packages": str(resume_path),
            }
        )
        chapter_packages = package_file["chapter_packages"]
        source_chunks = dedupe_source_chunk_records(package_file["source_chunks"])
        detected_chapter_count = int(
            book_metadata.get("detected_chapter_count") or len(chapter_packages)
        )
        generation_warnings: list[str] = []
        print("")
        print(f"Loaded chapter packages: {resume_path}")
        print(f"Chapter packages loaded: {len(chapter_packages)}")
    else:
        preparation_results = run_preparation(plan, args, run_subprocess=run_subprocess)

        if args.prepare_only:
            print("")
            print("Prepare only completed. NVIDIA not called.")
            print(f"Clean chunks: {plan['paths']['clean_chunks']}")
            print(f"Clean index ID: {plan['clean_index_id']}")
            print(f"Clean storage dir: {plan['clean_storage_dir']}")
            return None

        clean_chunks_path = Path(plan["paths"]["clean_chunks"])
        clean_chunks = load_clean_chunks(clean_chunks_path)
        chapters = group_chunks_by_chapter(clean_chunks)
        if not chapters:
            raise BookLearningMaterialsError("No non-front-matter chapters found in clean chunks.")

        existing_packages: list[dict[str, Any]] = []
        existing_source_chunks: list[dict[str, Any]] = []
        existing_errors: list[dict[str, Any]] = []
        if resume_path is not None:
            if not resume_path.exists():
                raise BookLearningMaterialsError(
                    f"Chapter packages file does not exist: {resume_path}"
                )
            package_file = load_chapter_packages_file(resume_path)
            existing_packages = list(package_file["chapter_packages"])
            existing_source_chunks = dedupe_source_chunk_records(
                package_file["source_chunks"]
            )
            checkpoint = package_file.get("checkpoint") or {}
            existing_errors = list(checkpoint.get("errors") or [])
            preparation_results.append(
                {
                    "name": "chapter_generation",
                    "status": "resume_missing",
                    "reason": f"loaded {len(existing_packages)} existing chapter packages",
                }
            )
            print("")
            print(f"Loaded partial chapter packages: {resume_path}")
            print(f"Existing chapter packages: {len(existing_packages)}")

        book_metadata = build_book_metadata(
            plan=plan,
            clean_chunks=clean_chunks,
            detected_chapter_count=len(chapters),
        )
        generation_metadata = build_generation_metadata(
            plan=plan,
            args=args,
            clean_chunks_path=clean_chunks_path,
        )
        if resume_path is not None:
            generation_metadata["resumed_from_chapter_packages"] = str(resume_path)
            generation_metadata["resume_missing_chapters"] = True

        chapter_packages, source_chunks, generation_warnings, _chapter_errors = generate_chapter_packages(
            chapters,
            args=args,
            plan=plan,
            book_metadata=book_metadata,
            generation_metadata=generation_metadata,
            existing_packages=existing_packages,
            existing_source_chunks=existing_source_chunks,
            existing_errors=existing_errors,
            output_path=plan["output_json"],
            complete_fn=complete_fn,
        )
        if not chapter_packages:
            raise BookLearningMaterialsError("No chapter packages were generated.")

        detected_chapter_count = len(chapters)
        print(f"Chapter packages saved: {plan['chapter_packages_json']}")

    allowed_ids = source_chunk_ids_from_records(source_chunks)
    synthesis, synthesis_warnings = generate_book_synthesis(
        chapter_packages,
        args=args,
        complete_fn=complete_fn,
        output_path=plan["output_json"],
        raw_response_path=plan["output_json"].parent
        / f"{plan['slug']}.book_synthesis.raw_response.txt",
        allowed_ids=allowed_ids,
    )

    materials = {
        **synthesis,
        "chapters": chapter_packages,
    }
    final: dict[str, Any] = {
        "book": book_metadata,
        "generation": generation_metadata,
        "learning_materials": materials,
        "source_chunks": source_chunks,
    }
    audit = audit_learning_materials(
        final,
        detected_chapter_count=detected_chapter_count,
        max_chapters=args.max_chapters,
    )
    all_warnings = generation_warnings + synthesis_warnings
    if all_warnings:
        audit["warnings"].extend(all_warnings)
        if audit["status"] == "PASS":
            audit["status"] = "PASS_WITH_WARNINGS"
    final["audit"] = audit

    plan["output_json"].parent.mkdir(parents=True, exist_ok=True)
    plan["output_report"].parent.mkdir(parents=True, exist_ok=True)
    plan["output_json"].write_text(
        json.dumps(final, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    plan["output_report"].write_text(
        build_report(
            plan=plan,
            preparation_results=preparation_results,
            final=final,
            chapter_packages=chapter_packages,
        ),
        encoding="utf-8",
    )
    print("")
    print("Whole-book learning materials generated.")
    print(f"Output JSON: {plan['output_json']}")
    print(f"Output report: {plan['output_report']}")
    print(f"Audit status: {audit['status']}")
    print(f"Invalid source references: {audit['invalid_source_reference_count']}")
    return final


def main() -> None:
    args = parse_args()
    try:
        generate_book_learning_materials(args)
    except BookLearningMaterialsError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
