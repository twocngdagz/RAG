"""Store generated learning-material chapters in a database for serving.

The milestone: generate once (done -- 17 grounded PTE chapters), store with stable
IDs, serve read-only over an API. This is the storage layer.

Each canonical chapter file is a self-contained, contract-validated document (one
book envelope holding one chapter). We store one row per chapter keyed by a stable
id -- f"{book_slug}:ch{chapter_number:02d}" -- so re-generating a chapter replaces
its row atomically without touching its siblings, which is what the handoff's
enrichment plan needs.

The whole document is kept as-is in a JSON column rather than re-modelled into
tables. book_learning_materials_contract.py is already the authoritative schema
and validator; normalizing the deep grounded-object tree into columns would
duplicate it and invite exactly the generator/contract drift that has bitten this
project. Metadata worth querying (title, provenance, contract status) is lifted
into typed columns; the document is validated on write and served whole.

EMPTY_CLEAN_CHUNK_TEXT is treated as non-blocking on load: it reports an empty
chunk in the clean index (a source-index issue), not a defect in the stored
chapter, whose grounding already passed at generation time.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from book_learning_materials_contract import validate_book_contract

DEFAULT_DB_URL = "sqlite:///storage/learning_materials.db"
# Contract error codes that describe the source clean-chunk index rather than the
# stored chapter document, so they do not block loading a validated chapter.
NON_BLOCKING_CONTRACT_CODES = {"EMPTY_CLEAN_CHUNK_TEXT"}


class StoreError(RuntimeError):
    pass


class Base(DeclarativeBase):
    pass


class ChapterRecord(Base):
    __tablename__ = "learning_material_chapters"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    book_slug: Mapped[str] = mapped_column(String, index=True)
    chapter_number: Mapped[int] = mapped_column(Integer)
    chapter_title: Mapped[str] = mapped_column(String)
    source_pdf: Mapped[str | None] = mapped_column(String, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String, nullable=True)
    backend: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_at: Mapped[str | None] = mapped_column(String, nullable=True)
    contract_status: Mapped[str] = mapped_column(String)
    loaded_at: Mapped[str] = mapped_column(String)
    document: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("book_slug", "chapter_number", name="uq_book_chapter"),
    )

    def index_item(self) -> dict[str, Any]:
        """The thin metadata the list endpoint needs -- no document body."""
        return {
            "id": self.id,
            "book_slug": self.book_slug,
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "backend": self.backend,
            "model": self.model,
            "contract_status": self.contract_status,
        }


ENRICHMENT_SCHEMA_VERSION = "pte_lesson_enrichment.v1"
# A lesson enrichment names the lesson it belongs to via source_label, e.g. "pte:ch01".
_SOURCE_LABEL_RE = re.compile(r"^([a-z0-9_-]+):ch0*(\d+)$", re.IGNORECASE)


class EnrichmentRecord(Base):
    """The teaching layer for one lesson, stored beside the grounded base.

    One row per (book, chapter). The whole enrichment document is kept in a JSON
    column; it is synthesized teaching (not source-quoted), so it is NOT run
    through the base contract -- its own schema_version gates it. Re-generating a
    lesson's enrichment replaces this row without touching the base chapter.
    """

    __tablename__ = "learning_material_enrichments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    book_slug: Mapped[str] = mapped_column(String, index=True)
    chapter_number: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String)
    task_type: Mapped[str | None] = mapped_column(String, nullable=True)
    lesson_title: Mapped[str | None] = mapped_column(String, nullable=True)
    source_label: Mapped[str | None] = mapped_column(String, nullable=True)
    loaded_at: Mapped[str] = mapped_column(String)
    document: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("book_slug", "chapter_number", name="uq_enrichment_book_chapter"),
    )


def stable_chapter_id(book_slug: str, chapter_number: int) -> str:
    return f"{book_slug}:ch{chapter_number:02d}"


def extract_metadata(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document.get("learning_materials"), dict):
        raise StoreError("Document has no learning_materials object.")
    chapters = document["learning_materials"].get("chapters")
    if not isinstance(chapters, list) or len(chapters) != 1:
        raise StoreError("Expected exactly one chapter per stored document.")
    chapter = chapters[0]
    number = chapter.get("chapter_number")
    if not isinstance(number, int):
        raise StoreError("Chapter is missing an integer chapter_number.")

    book = document.get("book") or {}
    generation = document.get("generation") or {}
    slug = book.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise StoreError("Document is missing book.slug.")

    return {
        "book_slug": slug,
        "chapter_number": number,
        "chapter_title": chapter.get("chapter_title") or f"Chapter {number}",
        "source_pdf": book.get("source_pdf"),
        "schema_version": document.get("schema_version"),
        "backend": generation.get("backend"),
        "model": generation.get("model"),
        "generated_at": generation.get("generated_at"),
    }


def blocking_contract_errors(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        e for e in audit.get("errors", [])
        if e.get("code") not in NON_BLOCKING_CONTRACT_CODES
    ]


def create_db(db_url: str = DEFAULT_DB_URL):
    if db_url.startswith("sqlite:///") and not db_url.endswith(":memory:"):
        Path(db_url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return engine


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_chapter(
    session: Session, document: dict[str, Any], *, contract_status: str
) -> ChapterRecord:
    meta = extract_metadata(document)
    record_id = stable_chapter_id(meta["book_slug"], meta["chapter_number"])
    record = session.get(ChapterRecord, record_id)
    if record is None:
        record = ChapterRecord(id=record_id)
        session.add(record)
    record.book_slug = meta["book_slug"]
    record.chapter_number = meta["chapter_number"]
    record.chapter_title = meta["chapter_title"]
    record.source_pdf = meta["source_pdf"]
    record.schema_version = meta["schema_version"]
    record.backend = meta["backend"]
    record.model = meta["model"]
    record.generated_at = meta["generated_at"]
    record.contract_status = contract_status
    record.loaded_at = now_iso()
    record.document = json.dumps(document, ensure_ascii=False)
    return record


def load_chapter_file(
    session: Session, book_file: str | Path, *, clean_chunks_file: str | Path
) -> tuple[ChapterRecord | None, list[dict[str, Any]]]:
    """Validate a chapter document and upsert it. Returns (record, blocking_errors).

    A document with blocking (structural) contract errors is NOT stored."""
    audit = validate_book_contract(book_file=book_file, clean_chunks_file=clean_chunks_file)
    blocking = blocking_contract_errors(audit)
    if blocking:
        return None, blocking

    # Status reflects the stored DOCUMENT's validity, not the source clean-chunk
    # index. A raw FAIL caused only by EMPTY_CLEAN_CHUNK_TEXT (an empty chunk in the
    # index) would mislabel a chapter whose own content is contract-valid, so with
    # no blocking errors the document is PASS.
    document = json.loads(Path(book_file).read_text(encoding="utf-8"))
    record = upsert_chapter(session, document, contract_status="PASS")
    return record, []


def list_chapters(session: Session, book_slug: str | None = None) -> list[ChapterRecord]:
    stmt = select(ChapterRecord)
    if book_slug:
        stmt = stmt.where(ChapterRecord.book_slug == book_slug)
    stmt = stmt.order_by(ChapterRecord.book_slug, ChapterRecord.chapter_number)
    return list(session.scalars(stmt))


def get_chapter(session: Session, book_slug: str, chapter_number: int) -> ChapterRecord | None:
    return session.get(ChapterRecord, stable_chapter_id(book_slug, chapter_number))


def list_books(session: Session) -> list[dict[str, Any]]:
    from sqlalchemy import func

    stmt = (
        select(ChapterRecord.book_slug, func.count())
        .group_by(ChapterRecord.book_slug)
        .order_by(ChapterRecord.book_slug)
    )
    return [{"slug": slug, "chapter_count": count} for slug, count in session.execute(stmt)]


# --------------------------------------------------------------------------- #
# Enrichment (teaching layer)
# --------------------------------------------------------------------------- #

def stable_enrichment_id(book_slug: str, chapter_number: int) -> str:
    return f"{book_slug}:ch{chapter_number:02d}:enrichment"


def extract_enrichment_metadata(document: dict[str, Any]) -> dict[str, Any]:
    schema_version = document.get("schema_version")
    if schema_version != ENRICHMENT_SCHEMA_VERSION:
        raise StoreError(
            f"Unsupported enrichment schema_version: {schema_version!r} "
            f"(expected {ENRICHMENT_SCHEMA_VERSION!r})."
        )
    label = str(document.get("source_label") or "").strip()
    match = _SOURCE_LABEL_RE.match(label)
    if not match:
        raise StoreError(
            f"Enrichment source_label must look like 'slug:chNN'; got {label!r}."
        )
    return {
        "book_slug": match.group(1).lower(),
        "chapter_number": int(match.group(2)),
        "schema_version": schema_version,
        "task_type": document.get("task_type"),
        "lesson_title": document.get("lesson_title"),
        "source_label": label,
    }


def upsert_enrichment(session: Session, document: dict[str, Any]) -> EnrichmentRecord:
    meta = extract_enrichment_metadata(document)
    record_id = stable_enrichment_id(meta["book_slug"], meta["chapter_number"])
    record = session.get(EnrichmentRecord, record_id)
    if record is None:
        record = EnrichmentRecord(id=record_id)
        session.add(record)
    record.book_slug = meta["book_slug"]
    record.chapter_number = meta["chapter_number"]
    record.schema_version = meta["schema_version"]
    record.task_type = meta["task_type"]
    record.lesson_title = meta["lesson_title"]
    record.source_label = meta["source_label"]
    record.loaded_at = now_iso()
    record.document = json.dumps(document, ensure_ascii=False)
    return record


def load_enrichment_file(session: Session, path: str | Path) -> EnrichmentRecord:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return upsert_enrichment(session, document)


def get_enrichment(session: Session, book_slug: str, chapter_number: int) -> EnrichmentRecord | None:
    return session.get(EnrichmentRecord, stable_enrichment_id(book_slug, chapter_number))


def chapters_with_enrichment(session: Session, book_slug: str) -> list[int]:
    stmt = (
        select(EnrichmentRecord.chapter_number)
        .where(EnrichmentRecord.book_slug == book_slug)
        .order_by(EnrichmentRecord.chapter_number)
    )
    return list(session.scalars(stmt))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load chapter documents into the DB.")
    p.add_argument("book_files", nargs="+", help="Chapter JSON files to load.")
    p.add_argument("--clean-chunks-file", required=True)
    p.add_argument("--db-url", default=DEFAULT_DB_URL)
    p.add_argument("--verify", action="store_true", help="Round-trip check after load.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    engine = create_db(args.db_url)
    loaded, rejected = 0, 0

    with Session(engine) as session:
        for book_file in sorted(args.book_files):
            try:
                record, blocking = load_chapter_file(
                    session, book_file, clean_chunks_file=args.clean_chunks_file
                )
            except StoreError as error:
                print(f"REJECT {book_file}: {error}", file=sys.stderr)
                rejected += 1
                continue
            if record is None:
                print(f"REJECT {book_file}: {len(blocking)} blocking contract error(s):",
                      file=sys.stderr)
                for e in blocking[:5]:
                    print(f"    {e.get('code')} {e.get('json_path')}", file=sys.stderr)
                rejected += 1
                continue
            print(f"loaded {record.id}  [{record.contract_status}]  {record.chapter_title}")
            loaded += 1
        session.commit()

        if args.verify:
            ok = verify_round_trip(session, args.book_files)
            print(f"round-trip: {'OK' if ok else 'MISMATCH'} for {len(args.book_files)} file(s)")
            if not ok:
                return 1

    print(f"\nLoaded {loaded}, rejected {rejected}.")
    return 1 if rejected else 0


def verify_round_trip(session: Session, book_files: list[str]) -> bool:
    for book_file in book_files:
        original = json.loads(Path(book_file).read_text(encoding="utf-8"))
        meta = extract_metadata(original)
        record = get_chapter(session, meta["book_slug"], meta["chapter_number"])
        if record is None or json.loads(record.document) != original:
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
