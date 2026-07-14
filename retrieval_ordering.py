import json
from pathlib import Path
from typing import Any, Iterable


VALID_ORDERINGS = {"semantic", "document"}


class RetrievalOrderingError(ValueError):
    pass


def load_selected_chapters(structure_resolution_path: str) -> list[dict]:
    path = Path(structure_resolution_path)

    if not path.exists():
        raise RetrievalOrderingError(
            f"Structure resolution file does not exist: {structure_resolution_path}"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RetrievalOrderingError(
            f"Structure resolution file is not valid JSON: {structure_resolution_path}"
        ) from error

    if not isinstance(data, dict):
        raise RetrievalOrderingError("Structure resolution JSON must be an object.")

    selected_outline = data.get("selected_outline")
    if not isinstance(selected_outline, dict):
        raise RetrievalOrderingError("Structure resolution is missing selected_outline.")

    chapters = selected_outline.get("chapters")
    if not isinstance(chapters, list):
        raise RetrievalOrderingError(
            "Structure resolution is missing selected_outline.chapters."
        )

    return chapters


def build_section_position_map(
    structure_resolution_path: str,
    chapter_number: int | None = None,
) -> dict[tuple[int | None, str], int]:
    chapters = load_selected_chapters(structure_resolution_path)
    section_positions = {}

    for chapter in chapters:
        current_chapter_number = chapter.get("chapter_number")

        if chapter_number is not None and current_chapter_number != chapter_number:
            continue

        sections = chapter.get("sections") or []
        if not isinstance(sections, list):
            continue

        for position, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue

            section_title = (
                section.get("section_title")
                or section.get("title")
                or section.get("section")
            )
            if section_title is None:
                continue

            section_positions[(current_chapter_number, str(section_title))] = position

    return section_positions


def node_metadata(retrieved_node: Any) -> dict:
    node = getattr(retrieved_node, "node", retrieved_node)
    metadata = getattr(node, "metadata", None)

    if isinstance(metadata, dict):
        return metadata

    return {}


def node_id(retrieved_node: Any) -> str:
    node = getattr(retrieved_node, "node", retrieved_node)
    value = getattr(node, "node_id", None)

    if value is None:
        return ""

    return str(value)


def sortable_number(value: Any) -> tuple[int, int | float]:
    if value is None:
        return (1, 0)

    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, 0)


def document_sort_key(
    retrieved_node: Any,
    section_positions: dict[tuple[int | None, str], int],
) -> tuple:
    metadata = node_metadata(retrieved_node)
    chapter_number = metadata.get("chapter_number")
    section_title = metadata.get("section")
    section_position = section_positions.get((chapter_number, section_title))

    return (
        sortable_number(chapter_number),
        sortable_number(section_position),
        sortable_number(metadata.get("page_start")),
        sortable_number(metadata.get("page_end")),
        node_id(retrieved_node),
    )


def order_retrieved_nodes(
    retrieved_nodes: Iterable[Any],
    *,
    ordering: str,
    structure_resolution_path: str,
) -> list[Any]:
    if ordering not in VALID_ORDERINGS:
        raise RetrievalOrderingError(
            f"Invalid ordering: {ordering}. Expected one of: document, semantic."
        )

    selected_nodes = list(retrieved_nodes)

    if ordering == "semantic":
        return selected_nodes

    section_positions = build_section_position_map(structure_resolution_path)

    return sorted(
        selected_nodes,
        key=lambda retrieved_node: document_sort_key(
            retrieved_node,
            section_positions,
        ),
    )


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen = set()
    unique_values = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        unique_values.append(value)

    return unique_values


def build_section_coverage(
    *,
    expanded_section_titles: list[str],
    retrieved_nodes: Iterable[Any],
) -> dict:
    expanded_titles = unique_preserve_order(expanded_section_titles)

    if not expanded_titles:
        return {
            "expanded_section_count": 0,
            "covered_section_count": 0,
            "missing_section_count": 0,
            "covered_section_titles": [],
            "missing_section_titles": [],
        }

    expanded_title_set = set(expanded_titles)
    retrieved_section_titles = {
        metadata.get("section")
        for metadata in (node_metadata(retrieved_node) for retrieved_node in retrieved_nodes)
        if metadata.get("section") in expanded_title_set
    }
    covered_titles = [
        section_title
        for section_title in expanded_titles
        if section_title in retrieved_section_titles
    ]
    missing_titles = [
        section_title
        for section_title in expanded_titles
        if section_title not in retrieved_section_titles
    ]

    return {
        "expanded_section_count": len(expanded_titles),
        "covered_section_count": len(covered_titles),
        "missing_section_count": len(missing_titles),
        "covered_section_titles": covered_titles,
        "missing_section_titles": missing_titles,
    }
