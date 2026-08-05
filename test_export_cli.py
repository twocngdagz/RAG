"""The production entry point: validate the source, then write, or write nothing.

Three properties, all about what ends up on disk.

The source contract runs FIRST. A book that fails it has something wrong with
its claims or their grounding, and exporting anyway would launder that into a
package Ela imports as though it were sound — the last place the problem is
still visible.

A refusal leaves NO file. A partial package on disk is worse than none: it looks
like an artefact, and an importer has no way to tell it from a complete one.

And a re-export that erases teaching refuses BEFORE it writes, leaving the
previous package where it is. Discovering the loss after overwriting the only
copy of what was lost is not a check.

    python test_export_cli.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures"
# One book, one pack, one chapter. The triple must agree: a source describing
# `sample-v2` exported under math5a's rules is refused by the exporter, and a
# test that did that was asserting CLI behaviour it could never reach.
BOOK = FIXTURES / "b11" / "math5a.chapter03.book_learning_materials.json"
CHUNKS = FIXTURES / "b11" / "math5a.chapter03.clean_chunks.json"
MANIFEST = FIXTURES / "b17" / "math5a.chapter03.export_manifest.json"
COACH = FIXTURES / "b17" / "math5a.chapter03.enrichment.json"
ITEMS = FIXTURES / "b17" / "math_practice_items.json"

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


def run(book: Path, manifest: Path, out: Path, *extra: str, coach: Path = COACH) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "export_lesson_package.py"),
            "--slug", "math5a",
            "--chapter", "3",
            "--book", str(book),
            "--clean-chunks", str(CHUNKS),
            "--manifest", str(manifest),
            "--enrichment", str(coach),
            "--practice-items", str(ITEMS),
            "--out", str(out),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


workspace = Path(tempfile.mkdtemp())


print("valid source and mapping writes a package that reloads identically")

out = workspace / "package.json"
result = run(BOOK, MANIFEST, out)

check("exits zero", result.returncode == 0, result.stderr[:200])
check("writes the file", out.exists())

package = json.loads(out.read_text()) if out.exists() else {}

check("reloads as the same package", package.get("content_hash") is not None)
check("names its schema", package.get("schema_version") == "learning.package.v2", str(package.get("schema_version")))
check("carries the lesson", package.get("lesson", {}).get("stable_key") == "math5a:ch03")
check(
    "carries the teaching document, the concepts and their banks",
    bool(package.get("teaching_document", {}).get("blocks"))
    and bool(package.get("concepts"))
    and all(concept["exercises"] for concept in package.get("concepts") or []),
)


print("\nre-running produces the same semantic hash")

second = workspace / "package-again.json"
rerun = run(BOOK, MANIFEST, second)

check("the rerun exits zero", rerun.returncode == 0, rerun.stderr[:200])

reloaded = json.loads(second.read_text()) if second.exists() else {}

# Both hashes ABSENT compared equal, so a run that wrote nothing at all passed
# this check. The hash must exist before it can agree with anything.
check(
    "the same source and mapping give the same hash",
    bool(reloaded.get("content_hash")) and reloaded.get("content_hash") == package.get("content_hash"),
    f"{reloaded.get('content_hash') or 'missing'} vs {package.get('content_hash') or 'missing'}",
)
check(
    "the two files are byte-identical",
    second.exists() and out.exists() and second.read_text() == out.read_text(),
)


print("\nan invalid source writes nothing")

broken_book = workspace / "broken-book.json"
broken = json.loads(BOOK.read_text())
# Remove the grounding a claim asserts, which the source contract checks and
# this exporter must never paper over.
broken["learning_materials"]["chapters"][0]["core_lessons"][0]["explanation"]["source_chunk_ids"] = ["nope:missing"]
broken_book.write_text(json.dumps(broken))

missing_out = workspace / "not-written.json"
failed = run(broken_book, MANIFEST, missing_out)

check("exits non-zero", failed.returncode != 0, str(failed.returncode))
check("leaves no output", not missing_out.exists())
check("says the source contract refused it", "contract" in failed.stderr.lower(), failed.stderr[:160])


print("\nan invalid mapping writes nothing")

bad_manifest = workspace / "bad-manifest.json"
bad = json.loads(MANIFEST.read_text())
bad["concepts"][0].pop("bank")
bad_manifest.write_text(json.dumps(bad))

bad_out = workspace / "bad-manifest-out.json"
refused = run(BOOK, bad_manifest, bad_out)

check("exits non-zero", refused.returncode != 0, str(refused.returncode))
check("leaves no output", not bad_out.exists())
check("names the gap in the mapping", "bank" in refused.stderr, refused.stderr[:160])


print("\nan unresolved element path writes nothing")

drifted_manifest = workspace / "drifted-manifest.json"
drifted = json.loads(MANIFEST.read_text())
drifted["resources"][0]["elements"] = ["review_checklist.99"]
drifted_manifest.write_text(json.dumps(drifted))

drifted_out = workspace / "drifted-out.json"
drift = run(BOOK, drifted_manifest, drifted_out)

check("exits non-zero", drift.returncode != 0, str(drift.returncode))
check("leaves no output", not drifted_out.exists())
check("names the path that no longer resolves", "review_checklist.99" in drift.stderr, drift.stderr[:160])


print("\na re-export says what it added, and refuses to call a removal an enrichment")

# The manifest names its assets relative to itself, so the enriched copies live
# beside the real one rather than in the workspace.
enriched_coach = FIXTURES / "b17" / "_enriched.coach.json"
poorer_coach = FIXTURES / "b17" / "_poorer.coach.json"

try:
    coach = json.loads(COACH.read_text())

    richer = json.loads(json.dumps(coach))
    richer["worked_examples"].append(
        {
            "title": "Add three eighths and one quarter",
            "input": "Work out $\\frac{3}{8} + \\frac{1}{4}$.",
            "decoding": "The bottom numbers are different.",
            "plan": "Change one quarter into two eighths.",
            "model_answer": "$\\frac{3}{8} + \\frac{2}{8} = \\frac{5}{8}$.",
            "annotations": [{"part": "$\\frac{2}{8}$", "comment": "The same amount, in eighths."}],
        }
    )
    enriched_coach.write_text(json.dumps(richer))

    poorer = json.loads(json.dumps(coach))
    dropped = poorer["worked_examples"].pop(2)
    poorer_coach.write_text(json.dumps(poorer))

    enrichment = run(BOOK, MANIFEST, out, coach=enriched_coach)

    check("an additive re-export exits zero", enrichment.returncode == 0, enrichment.stderr[:200])
    check("it prints what it added", "1 added, 0 removed" in enrichment.stdout, enrichment.stdout[:160])

    before = out.read_text()
    erasure = run(BOOK, MANIFEST, out, coach=poorer_coach)

    check("a re-export that drops teaching exits non-zero", erasure.returncode != 0, str(erasure.returncode))
    check("it says what went missing", dropped["title"][:20] in erasure.stderr, erasure.stderr[:220])
    check("it says an edit is the honest way to remove something", "edit" in erasure.stderr, erasure.stderr[:220])
    check("and the previous package is still on disk, untouched", out.read_text() == before)

    named_edit = run(BOOK, MANIFEST, out, "--edit", "the example taught a method the book does not use", coach=poorer_coach)

    check("a named edit is allowed through", named_edit.returncode == 0, named_edit.stderr[:200])
    check("and says it was an edit", "edit:" in named_edit.stdout, named_edit.stdout[:160])
    check("and the removal is written", out.read_text() != before)
finally:
    for scratch in (enriched_coach, poorer_coach):
        scratch.unlink(missing_ok=True)

shutil.rmtree(workspace, ignore_errors=True)


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the entry point validates, then writes, or writes nothing")
raise SystemExit(1 if fails else 0)
