import json
from pathlib import Path
from typing import Any


class SectionScopeError(ValueError):
    pass


FLAT_DESCENDANT_START_WORDS = {
    "add",
    "ask",
    "break",
    "choose",
    "define",
    "describe",
    "design",
    "evaluate",
    "give",
    "include",
    "iterate",
    "keep",
    "organize",
    "provide",
    "separate",
    "specify",
    "test",
    "use",
    "version",
    "write",
}


def load_structure_resolution(path: Path) -> dict:
    if not path.exists():
        raise SectionScopeError(f"Structure resolution file does not exist: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SectionScopeError(
            f"Structure resolution file is not valid JSON: {path}\nError: {error}"
        ) from error

    if not isinstance(data, dict):
        raise SectionScopeError("Structure resolution JSON must be an object.")

    return data


def get_selected_chapters(structure_resolution: dict) -> list[dict]:
    selected_outline = structure_resolution.get("selected_outline")

    if not isinstance(selected_outline, dict):
        raise SectionScopeError("Structure resolution is missing selected_outline.")

    chapters = selected_outline.get("chapters")

    if not isinstance(chapters, list):
        raise SectionScopeError("Structure resolution is missing selected_outline.chapters.")

    return chapters


def get_section_title(section: dict) -> str | None:
    title = section.get("section_title") or section.get("title") or section.get("section")

    if title is None:
        return None

    return str(title)


def section_level(section: dict) -> int | None:
    level = section.get("level")

    if level is None:
        return None

    try:
        return int(level)
    except (TypeError, ValueError):
        return None


def chapter_label(chapter: dict) -> str | None:
    explicit_chapter = chapter.get("chapter")

    if explicit_chapter:
        return str(explicit_chapter)

    chapter_number = chapter.get("chapter_number")

    if chapter_number is not None:
        return f"CHAPTER {chapter_number}"

    chapter_title = chapter.get("chapter_title")

    if chapter_title:
        return str(chapter_title)

    return None


def matching_sections(
    chapters: list[dict],
    requested_section: str,
    chapter_number: int | None,
) -> list[tuple[dict, int, dict]]:
    matches = []

    for chapter in chapters:
        if chapter_number is not None and chapter.get("chapter_number") != chapter_number:
            continue

        sections = chapter.get("sections") or []
        if not isinstance(sections, list):
            continue

        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                continue

            if get_section_title(section) == requested_section:
                matches.append((chapter, index, section))

    return matches


def is_flat_parent_title(title: str) -> bool:
    normalized_title = title.strip().lower()

    return any(
        phrase in normalized_title
        for phrase in (
            "best practices",
            "use cases",
            "workflow",
            "strategies",
            "methods",
            "patterns",
            "techniques",
        )
    )


def is_flat_descendant_title(title: str) -> bool:
    normalized_title = title.strip().lower()
    first_word = normalized_title.split(maxsplit=1)[0] if normalized_title else ""

    return first_word in FLAT_DESCENDANT_START_WORDS


def expand_by_section_level(sections: list[dict], start_index: int) -> list[str]:
    requested_section = sections[start_index]
    requested_title = get_section_title(requested_section)

    if requested_title is None:
        return []

    requested_level = section_level(requested_section)
    if requested_level is None:
        return [requested_title]

    titles = [requested_title]

    for section in sections[start_index + 1 :]:
        current_level = section_level(section)
        current_title = get_section_title(section)

        if current_title is None:
            continue

        if current_level is None:
            break

        if current_level <= requested_level:
            break

        titles.append(current_title)

    return titles


def expand_flat_parent_sections(sections: list[dict], start_index: int) -> list[str]:
    requested_section = sections[start_index]
    requested_title = get_section_title(requested_section)

    if requested_title is None or not is_flat_parent_title(requested_title):
        return [requested_title] if requested_title else []

    requested_level = section_level(requested_section)
    titles = [requested_title]

    for section in sections[start_index + 1 :]:
        current_title = get_section_title(section)

        if current_title is None:
            continue

        current_level = section_level(section)
        if (
            requested_level is not None
            and current_level is not None
            and current_level < requested_level
        ):
            break

        if not is_flat_descendant_title(current_title):
            break

        titles.append(current_title)

    return titles


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    unique_values = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        unique_values.append(value)

    return unique_values


def resolve_section_scope(
    structure_resolution_path: str,
    section_title: str,
    chapter_number: int | None = None,
    include_descendants: bool = False,
) -> dict:
    structure_path = Path(structure_resolution_path)
    structure_resolution = load_structure_resolution(structure_path)
    chapters = get_selected_chapters(structure_resolution)
    matches = matching_sections(
        chapters=chapters,
        requested_section=section_title,
        chapter_number=chapter_number,
    )

    if not matches:
        chapter_message = (
            f" in chapter {chapter_number}" if chapter_number is not None else ""
        )
        raise SectionScopeError(
            f"Section title not found{chapter_message}: {section_title}"
        )

    matched_chapter_numbers = {
        match[0].get("chapter_number")
        for match in matches
        if match[0].get("chapter_number") is not None
    }

    if chapter_number is None and len(matched_chapter_numbers) > 1:
        chapters_text = ", ".join(str(number) for number in sorted(matched_chapter_numbers))
        raise SectionScopeError(
            f"Section title appears in multiple chapters: {section_title}. "
            f"Provide --chapter-number. Matching chapters: {chapters_text}"
        )

    if len(matches) > 1:
        raise SectionScopeError(
            f"Section title appears multiple times in the selected scope: {section_title}"
        )

    chapter, section_index, section = matches[0]
    sections = chapter.get("sections") or []
    requested_level = section_level(section)

    if include_descendants:
        section_titles = expand_by_section_level(sections, section_index)

        if len(section_titles) == 1:
            section_titles = expand_flat_parent_sections(sections, section_index)
    else:
        requested_title = get_section_title(section)
        section_titles = [requested_title] if requested_title else []

    section_titles = unique_preserve_order(section_titles)

    return {
        "requested_section": section_title,
        "chapter": chapter_label(chapter),
        "chapter_number": chapter.get("chapter_number"),
        "parent_level": requested_level,
        "include_descendants": include_descendants,
        "section_titles": section_titles,
    }
