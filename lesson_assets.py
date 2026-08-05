"""The package's asset channel: pictures travel inside the file, never fetched.

A learner never waits on an image service and never connects to one. A picture
is drawn once at authoring time, approved once, and then rides inside the
package — so a lesson can arrive on a slow train, an offline laptop, or a
five-year-old archive and still show its diagrams.

Two encodings, because there are two kinds of picture:

    inline_svg  SVG, which is text. A computed diagram — a bar model, an area
                model — is written into the package as the markup that draws
                it, in a field called `svg`, so it stays inspectable and
                diffable.
    base64      everything else. A raster image is bytes, and bytes ride
                encoded, in a field called `content`.

The payload's field name travels with the encoding because that is what Ela's
importer reads: an inline SVG comes out of `svg`, encoded bytes out of
`content`. The consumer's contract is released, so the producer conforms to it.

Both end up as characters in the same file, and the content hash covers them, so
"N added, 0 removed" covers images too: they are inside the thing compared.

Every asset carries alt text and a caption, and says where it came from. In
maths a picture carries mathematical content — a cartoon cutting pizzas into
thirds when the problem says quarters teaches the wrong thing — so an asset
whose origin nobody recorded is refused rather than shipped anonymously.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

import lesson_provenance

# SVG is text, so it rides as itself. Anything else is bytes and is encoded.
INLINE_MEDIA_TYPE = "image/svg+xml"

# What each encoding is called, and which field the picture rides in under it.
# Ela reads these names, so they are the names written.
INLINE_SVG_ENCODING = "inline_svg"
BASE64_ENCODING = "base64"
PAYLOAD_FIELD = {INLINE_SVG_ENCODING: "svg", BASE64_ENCODING: "content"}

# Where an asset may say it came from. `manually_authored` is an author's own
# upload; `pedagogical_generation` is a drawing made for the lesson. Those are
# the two kinds the illustration decision names, expressed in the provenance
# vocabulary Ela already validates rather than in a second set of labels.
ASSET_ORIGINS = (lesson_provenance.MANUALLY_AUTHORED, lesson_provenance.PEDAGOGICAL_GENERATION)


class AssetRefused(Exception):
    """An asset cannot ride in the package, and why."""


def build(declared: dict[str, Any], *, base_dir: Path, path: str) -> dict[str, Any]:
    """One declared asset, read and sealed into the package."""
    if not isinstance(declared, dict):
        raise AssetRefused(f"{path} is not an object")

    key = str(declared.get("stable_key") or "").strip()

    if not key:
        raise AssetRefused(f"{path} has no stable_key")

    media_type = str(declared.get("media_type") or "").strip()

    if not media_type:
        raise AssetRefused(f"{path} has no media_type, so a reader cannot tell what it is")

    for field in ("alt_text", "caption"):
        if not str(declared.get(field) or "").strip():
            raise AssetRefused(
                f"{path} has no {field}; a picture nobody described reaches a learner who cannot see it"
            )

    illustrates = str(declared.get("illustrates") or "").strip()

    if not illustrates:
        raise AssetRefused(
            f"{path} does not say what it illustrates; an asset attached to nothing "
            f"is weight the package carries and no learner meets"
        )

    inline = declared.get("svg")
    file_reference = str(declared.get("file") or "").strip()

    if bool(inline) == bool(file_reference):
        raise AssetRefused(
            f"{path} must declare exactly one of svg (text, written in place) or file "
            f"(bytes, read and encoded); it declares {'both' if inline else 'neither'}"
        )

    if inline:
        if media_type != INLINE_MEDIA_TYPE:
            raise AssetRefused(
                f"{path} rides inline but is {media_type!r}; only {INLINE_MEDIA_TYPE} is text"
            )

        payload = str(inline).strip()
        raw = payload.encode("utf-8")
        encoding = INLINE_SVG_ENCODING
    else:
        if media_type == INLINE_MEDIA_TYPE:
            raise AssetRefused(
                f"{path} is {INLINE_MEDIA_TYPE} but ships as a file; SVG rides inline, as text"
            )

        source = (base_dir / file_reference).resolve()

        if not source.is_file():
            raise AssetRefused(f"{path} names {file_reference!r}, which does not exist")

        raw = source.read_bytes()
        payload = base64.b64encode(raw).decode("ascii")
        encoding = BASE64_ENCODING

    if not raw:
        raise AssetRefused(f"{path} is empty; there is no picture in it")

    return {
        "stable_key": key,
        "media_type": media_type,
        "encoding": encoding,
        PAYLOAD_FIELD[encoding]: payload,
        # The bytes as they were before encoding, so an importer can check that
        # what it decoded is what was sealed in.
        "byte_length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "alt_text": str(declared["alt_text"]).strip(),
        "caption": str(declared["caption"]).strip(),
        "illustrates": illustrates,
        "provenance": _provenance(declared.get("provenance"), path),
    }


def _provenance(declared: Any, path: str) -> dict[str, Any]:
    if not isinstance(declared, dict):
        raise AssetRefused(f"{path} has no provenance; a picture of unknown origin teaches on trust")

    origin = str(declared.get("origin") or "").strip()

    if origin not in ASSET_ORIGINS:
        raise AssetRefused(
            f"{path}.provenance origin {origin or 'missing'!r} is not one of {', '.join(ASSET_ORIGINS)}"
        )

    if origin == lesson_provenance.MANUALLY_AUTHORED:
        author = str(declared.get("author_reference") or "").strip()

        if not author:
            raise AssetRefused(f"{path} claims an author but does not say who")

        return {"origin": origin, "author_reference": author}

    record = {
        "origin": origin,
        "grounded_in_source_chunk_ids": [
            str(chunk) for chunk in (declared.get("grounded_in_source_chunk_ids") or [])
        ],
        "generation_reason": str(declared.get("generation_reason") or "").strip(),
        "generator_version": str(declared.get("generator_version") or "").strip(),
    }

    missing = [field for field in ("generation_reason", "generator_version") if not record[field]]

    if missing:
        raise AssetRefused(f"{path} was drawn for the lesson but names no {', '.join(missing)}")

    return record
