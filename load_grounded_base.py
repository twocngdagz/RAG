"""Load a book's grounded-base chapters into the DB via the lighter path.

For books not built by the PTE extract->resolve->audit chain (see
book_learning_materials_store.register_chapter_file). Reads the per-chapter files
the domain pack points at and upserts each, so the API lists the book and the
frontend can navigate it. Stored with contract_status "extracted", never "PASS" —
honest about what was and was not verified.

Usage:
  python load_grounded_base.py --book math5a              # all chapters found
  python load_grounded_base.py --book math5a --chapters 3
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy.orm import Session

import book_learning_materials_store as store
import domain_packs


def chapters_on_disk(pack: domain_packs.DomainPack) -> list[int]:
    pattern = Path(pack.base_path(0)).name.replace("chapter00", "chapter*")
    found = []
    for p in Path("output").glob(pattern):
        m = re.search(r"chapter(\d+)", p.name)
        if m:
            found.append(int(m.group(1)))
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", required=True, choices=sorted(domain_packs.REGISTRY))
    ap.add_argument("--chapters", type=int, nargs="*")
    ap.add_argument("--db-url", default=store.DEFAULT_DB_URL)
    args = ap.parse_args(argv)

    pack = domain_packs.get(args.book)
    wanted = args.chapters or chapters_on_disk(pack)
    if not wanted:
        print(f"No grounded-base files found for {args.book!r} in output/.", file=sys.stderr)
        return 1

    engine = store.create_db(args.db_url)
    loaded, failed = [], []
    with Session(engine) as session:
        for n in wanted:
            path = Path(pack.base_path(n))
            if not path.exists():
                print(f"  ch{n:02d}: no file at {path}", file=sys.stderr)
                failed.append(n)
                continue
            record, problems = store.register_chapter_file(session, path)
            if problems:
                print(f"  ch{n:02d}: rejected — {'; '.join(problems)}", file=sys.stderr)
                failed.append(n)
                continue
            print(f"  ch{n:02d}: loaded ({record.contract_status}) — {record.chapter_title}")
            loaded.append(n)
        session.commit()

    print(f"\n{len(loaded)}/{len(wanted)} chapters loaded for {args.book}.")
    if failed:
        print(f"  FAILED: {failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
