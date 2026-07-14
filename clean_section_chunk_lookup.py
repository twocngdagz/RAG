import json
from collections import Counter
from pathlib import Path
from typing import Any


class CleanChunkLookupError(ValueError):
    pass


def load_clean_chunk_collection(clean_chunks_file: str | Path) -> list[dict[str, Any]]:
    path = Path(clean_chunks_file)

    if not path.exists():
        raise CleanChunkLookupError(f"Clean chunks file does not exist: {path}")

    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CleanChunkLookupError(
            f"Clean chunks file is not valid JSON: {path}\nError: {error}"
        ) from error

    if isinstance(artifact, dict):
        chunks = (
            artifact.get("chunks")
            or artifact.get("nodes")
            or artifact.get("items")
        )
    else:
        chunks = artifact

    if not isinstance(chunks, list) or not chunks:
        raise CleanChunkLookupError(
            "Clean chunks JSON must contain a non-empty chunk collection."
        )

    if not all(isinstance(chunk, dict) for chunk in chunks):
        raise CleanChunkLookupError(
            "Clean chunks JSON must contain only chunk objects."
        )

    return chunks


def clean_chunk_node_id(chunk: dict[str, Any]) -> str | None:
    for key in ("node_id", "chunk_id", "id"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def resolve_clean_chunks_by_ids(
    *,
    clean_chunks: list[dict[str, Any]],
    node_ids: list[str],
    require_text: bool = True,
) -> list[dict[str, Any]]:
    lookup: dict[str, list[dict[str, Any]]] = {}

    for chunk in clean_chunks:
        node_id = clean_chunk_node_id(chunk)
        if node_id:
            lookup.setdefault(node_id, []).append(chunk)

    if not lookup:
        raise CleanChunkLookupError(
            "Clean chunks JSON does not contain any usable chunk IDs."
        )

    requested_counts = Counter(node_ids)
    duplicate_requested_ids = [
        node_id for node_id, count in requested_counts.items() if count > 1
    ]
    if duplicate_requested_ids:
        raise CleanChunkLookupError(
            "Requested source chunk IDs contain duplicates: "
            + ", ".join(duplicate_requested_ids)
        )

    duplicate_matching_ids = [
        node_id for node_id in node_ids if len(lookup.get(node_id, [])) > 1
    ]
    if duplicate_matching_ids:
        raise CleanChunkLookupError(
            "Clean chunks JSON contains duplicate matching node IDs: "
            + ", ".join(duplicate_matching_ids)
        )

    missing_ids = [node_id for node_id in node_ids if node_id not in lookup]
    if missing_ids:
        raise CleanChunkLookupError(
            "Could not resolve full clean text for source chunk IDs: "
            + ", ".join(missing_ids)
        )

    resolved = [lookup[node_id][0] for node_id in node_ids]

    if require_text:
        empty_text_ids = []
        for node_id, chunk in zip(node_ids, resolved):
            text = chunk.get("text")
            if not isinstance(text, str) or not text.strip():
                empty_text_ids.append(node_id)

        if empty_text_ids:
            raise CleanChunkLookupError(
                "Resolved clean chunks contain empty full text for source chunk IDs: "
                + ", ".join(empty_text_ids)
            )

    return resolved


def load_and_resolve_clean_chunks_by_ids(
    *,
    clean_chunks_file: str | Path,
    node_ids: list[str],
    require_text: bool = True,
) -> list[dict[str, Any]]:
    clean_chunks = load_clean_chunk_collection(clean_chunks_file)
    return resolve_clean_chunks_by_ids(
        clean_chunks=clean_chunks,
        node_ids=node_ids,
        require_text=require_text,
    )
