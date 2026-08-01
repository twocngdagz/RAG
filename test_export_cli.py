"""The production entry point: validate the source, then write, or write nothing.

Two properties, both about what ends up on disk.

The source contract runs FIRST. A book that fails it has something wrong with
its claims or their grounding, and exporting anyway would launder that into a
package Ela imports as though it were sound — the last place the problem is
still visible.

And a refusal leaves NO file. A partial package on disk is worse than none: it
looks like an artefact, and B11.1 has no way to tell it from a complete one.

    python test_export_cli.py
"""
from __future__ import annotations

import json
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
MANIFEST = FIXTURES / "b11" / "math5a.chapter03.export_manifest.json"

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


def run(book: Path, manifest: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "export_lesson_package.py"),
            "--slug", "math5a",
            "--chapter", "3",
            "--book", str(book),
            "--clean-chunks", str(CHUNKS),
            "--manifest", str(manifest),
            "--out", str(out),
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
check("names its schema", package.get("schema_version") == "learning.package.v1", str(package.get("schema_version")))
check("carries the lesson", package.get("lesson", {}).get("stable_key") == "math5a:ch03")
check("carries objectives and activities", bool(package.get("objectives")) and bool(package.get("activities")))


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
bad["activities"][0]["objective_alignments"] = []
bad_manifest.write_text(json.dumps(bad))

bad_out = workspace / "bad-manifest-out.json"
refused = run(BOOK, bad_manifest, bad_out)

check("exits non-zero", refused.returncode != 0, str(refused.returncode))
check("leaves no output", not bad_out.exists())
check("names the gap in the mapping", "objective_alignments" in refused.stderr, refused.stderr[:160])


print("\nan unresolved element path writes nothing")

drifted_manifest = workspace / "drifted-manifest.json"
drifted = json.loads(MANIFEST.read_text())
drifted["activities"][0]["elements"] = ["core_lessons.99.explanation"]
drifted_manifest.write_text(json.dumps(drifted))

drifted_out = workspace / "drifted-out.json"
drift = run(BOOK, drifted_manifest, drifted_out)

check("exits non-zero", drift.returncode != 0, str(drift.returncode))
check("leaves no output", not drifted_out.exists())
check("names the path that no longer resolves", "core_lessons.99" in drift.stderr, drift.stderr[:160])


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the entry point validates, then writes, or writes nothing")
raise SystemExit(1 if fails else 0)
