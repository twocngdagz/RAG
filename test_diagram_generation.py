"""Computed diagrams: the same numbers draw the same picture, every time.

A maths picture carries mathematical content. If the diagram beside "work out
1/3 + 1/2" shows quarters, it teaches a child something false and does it
silently — the learner who cannot see the picture is the one who would never
find out. So these pictures are computed from the numbers in the teaching they
sit beside, and this file is where that claim is made to pay:

    the same numbers draw the same picture — twice in one process, and again in
    a fresh one with a different hash seed, byte for byte
    the picture IS the sum — the bar is split into the parts the question wrote,
    unsimplified, and the shaded width is the fraction of the bar
    a picture that would teach the wrong thing is REFUSED, never approximated
    the drawing rides inside the package, in the asset channel, referenced by an
    illustration block that carries its caption and its alt text
    nothing is fetched: the export draws with the network unplugged

WHAT THIS FILE DOES NOT COVER, and deliberately. B18's other half — friendly
generated images and the author-approval gate that admits them — is not built.
It needs a hosted image model that does not exist here yet, and a stub for it
would be machinery that passes its own tests and draws nothing real. The gate is
therefore untested because it is unbuilt, not because it was forgotten.

    python test_diagram_generation.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import enrichment_comparison
import export_lesson_package as ex
import lesson_diagrams as ld
import lesson_export_manifest as manifest_module
import lesson_package
import teaching_document as td

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures" / "b18"
SHARED = ROOT / "tests" / "fixtures" / "b17"
SOURCE = json.loads((ROOT / "tests" / "fixtures" / "b11" / "math5a.chapter03.book_learning_materials.json").read_text())
MANIFEST = json.loads((FIXTURES / "math5a.chapter03.export_manifest.json").read_text())
COACH = json.loads((SHARED / "math5a.chapter03.enrichment.json").read_text())
ITEMS = json.loads((SHARED / "math_practice_items.json").read_text())


def export(*, manifest=MANIFEST, document=COACH, items=ITEMS):
    return ex.export_chapter(
        "math5a",
        3,
        SOURCE,
        manifest=manifest,
        teaching_document=document,
        practice_items=items,
        asset_base=FIXTURES,
    )


def copy(value):
    return json.loads(json.dumps(value))


def drawn(kind: str, text: str) -> dict[str, str]:
    return ld.draw(kind, ld.read(text, path="test"), path="test")


def row_y(index: int) -> int:
    return ld.TOP_MARGIN + index * (ld.BAR_HEIGHT + ld.ROW_GAP)


def cuts(svg: str, row: int) -> int:
    """How many cuts split the bar on this row — one fewer than its equal parts."""
    y = row_y(row)

    return len(re.findall(rf'<line x1="(\d+)" y1="{y}" x2="\1" y2="{y + ld.BAR_HEIGHT}"/>', svg))


def shaded_widths(svg: str, row: int) -> list[int]:
    y = row_y(row)
    found = re.findall(
        rf'<rect x="\d+" y="{y}" width="(\d+)" height="{ld.BAR_HEIGHT}" fill="{ld.SHADED}"/>', svg
    )

    return [int(width) for width in found]


print("the same numbers draw the same picture, every time")

SUMS = {
    "bar_model": "Work out $\\frac{1}{3} + \\frac{1}{2}$.",
    "area_model": "$$\\frac{3}{5} \\times \\frac{1}{6}$$",
    "step_layout": "Work out $\\frac{2}{3} \\div 4$.",
}

for kind, question in SUMS.items():
    first, second = drawn(kind, question), drawn(kind, question)

    check(f"{kind}: drawn twice, identical to the byte", first["svg"] == second["svg"])
    check(f"{kind}: it is text, and it is an SVG", first["svg"].startswith("<svg"), first["svg"][:40])
    check(
        f"{kind}: it carries its own title and description",
        f"<title>{first['caption']}</title>" in first["svg"] and "<desc>" in first["svg"],
    )

# A fresh interpreter, twice, with the hash seed moved under it: nothing in the
# drawing may depend on set ordering, a clock, or a random number.
ELSEWHERE = (
    "import hashlib, json, sys;"
    "sys.path.insert(0, sys.argv[1]);"
    "import lesson_diagrams as ld;"
    "print(json.dumps({k: hashlib.sha256(ld.draw(k, ld.read(q, path='p'), path='p')['svg']"
    ".encode()).hexdigest() for k, q in json.loads(sys.argv[2]).items()}))"
)


def elsewhere(seed: str) -> dict[str, str]:
    finished = subprocess.run(
        [sys.executable, "-c", ELSEWHERE, str(ROOT), json.dumps(SUMS)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": seed},
        cwd=ROOT,
    )

    if finished.returncode != 0:
        return {"error": finished.stderr[-400:]}

    return json.loads(finished.stdout)


here = {
    kind: hashlib.sha256(drawn(kind, question)["svg"].encode()).hexdigest()
    for kind, question in SUMS.items()
}
there, elsewhen = elsewhere("1"), elsewhere("2")

check("a fresh process draws the same bytes", there == here, str(there))
check("and so does one with a different hash seed", elsewhen == here, str(elsewhen))


print("\nthe picture is the sum, not a picture of a sum")

bars = drawn("bar_model", SUMS["bar_model"])

check("the bar model splits the first bar into thirds", cuts(bars["svg"], 0) + 1 == 3, str(cuts(bars["svg"], 0) + 1))
check("the second into halves", cuts(bars["svg"], 1) + 1 == 2, str(cuts(bars["svg"], 1) + 1))
check(
    "and the answer bar into the sixths they both become",
    cuts(bars["svg"], 2) + 1 == 6,
    str(cuts(bars["svg"], 2) + 1),
)
check(
    "one third of the bar is shaded, and it is a third of the bar's width",
    shaded_widths(bars["svg"], 0) == [round(ld.BAR_WIDTH / 3)],
    str(shaded_widths(bars["svg"], 0)),
)
check(
    "five sixths of the answer bar are shaded",
    shaded_widths(bars["svg"], 2) == [round(ld.BAR_WIDTH * 5 / 6)],
    str(shaded_widths(bars["svg"], 2)),
)
check(
    "the caption states the answer this arithmetic gives",
    bars["caption"] == "Bar model: 1/3 + 1/2 = 5/6.",
    bars["caption"],
)
check(
    "the alt text describes the same picture, in words",
    "3 equal parts (thirds) with 1 shaded" in bars["alt_text"]
    and "6 equal parts (sixths) with 5 shaded" in bars["alt_text"],
    bars["alt_text"],
)

unsimplified = drawn("bar_model", "$$\\frac{2}{4} + \\frac{1}{4}$$")

check(
    "a bar drawn from two quarters shows four parts, not two",
    cuts(unsimplified["svg"], 0) + 1 == 4,
    "reducing the question's own numbers would draw a bar the exercise never mentions",
)
check(
    "and the answer is still written in its simplest form",
    unsimplified["caption"].endswith("= 3/4."),
    unsimplified["caption"],
)

taken_away = drawn("bar_model", "$$\\frac{1}{3} - \\frac{1}{4}$$")

check("subtraction draws the difference", taken_away["caption"].endswith("= 1/12."), taken_away["caption"])
check(
    "over the twelfths both bottoms become",
    cuts(taken_away["svg"], 2) + 1 == 12,
    str(cuts(taken_away["svg"], 2) + 1),
)

over_one = drawn("bar_model", "$$\\frac{1}{2} + \\frac{4}{5}$$")

check(
    "an answer of more than one whole spills into a second bar",
    len(shaded_widths(over_one["svg"], 2)) == 2,
    str(shaded_widths(over_one["svg"], 2)),
)
check(
    "and is written as a mixed number",
    over_one["caption"].endswith("= 1 3/10."),
    over_one["caption"],
)

area = drawn("area_model", SUMS["area_model"])

check(
    "the area model cuts the square 5 across and 6 down",
    area["svg"].count(f'x2="{ld.SQUARE_X + ld.SQUARE}"') == 5
    and area["alt_text"].startswith("A square split into 5 columns and 6 rows, making 30 equal cells."),
    area["alt_text"][:80],
)
check(
    "the crossing cells are the product",
    "The 3 cells where they cross are the answer, 3 out of 30, which is 1/10." in area["alt_text"],
    area["alt_text"],
)
check("and the caption says so", area["caption"] == "Area model: 3/5 × 1/6 = 1/10.", area["caption"])

steps = drawn("step_layout", SUMS["step_layout"])

check(
    "the step layout writes the working a learner would write",
    ["2/3 ÷ 4", "2/3 × 1/4", "(2 × 1)/(3 × 4)", "= 2/12", "= 1/6"]
    == [line for line in ["2/3 ÷ 4", "2/3 × 1/4", "(2 × 1)/(3 × 4)", "= 2/12", "= 1/6"] if line in steps["svg"]],
    steps["alt_text"],
)
working = steps["svg"].split("</desc>", 1)[1]

check(
    "in the order the method goes",
    working.index("2/3 × 1/4") < working.index("= 2/12") < working.index("= 1/6"),
    working[:80],
)
check("and says what each step does", "Turn the number you are dividing by upside down" in steps["svg"])
check("the caption states the answer", steps["caption"] == "Step by step: 2/3 ÷ 4 = 1/6.", steps["caption"])

times_whole = drawn("step_layout", "Work out $\\frac{2}{3} \\times 12$.")

check("a whole-number multiplier is worked through too", times_whole["caption"].endswith("= 8."), times_whole["caption"])
check(
    "different numbers draw a different picture",
    drawn("bar_model", "$$\\frac{1}{3} + \\frac{1}{4}$$")["svg"] != bars["svg"],
)


print("\na picture that would teach the wrong thing is refused")

REFUSALS = (
    ("a mixed number this module cannot draw", "bar_model", "Work out $3\\frac{1}{4} - 1\\frac{2}{3}$.", "mixed number"),
    ("a question naming no calculation", "bar_model", "Four children share three identical pizzas equally.", "names no calculation"),
    ("a bar model of a multiplication", "bar_model", "$$\\frac{3}{5} \\times \\frac{1}{6}$$", "not ×"),
    ("a bar model that would go below nothing", "bar_model", "$$\\frac{1}{4} - \\frac{1}{2}$$", "less than nothing"),
    ("an area model of an addition", "area_model", "Work out $\\frac{1}{3} + \\frac{1}{2}$.", "which is multiplication"),
    ("an area model of more than one whole", "area_model", "Work out $\\frac{3}{5} \\times \\frac{10}{9}$.", "more than one whole"),
    ("a sum with no fraction in it", "step_layout", "$$31 \\times 70$$", "no equal parts"),
)

for label, kind, text, expected in REFUSALS:
    try:
        drawn(kind, text)
        check(label + " is refused", False, "it drew something")
    except ld.DiagramRefused as error:
        check(label + " is refused", True)
        check(f"...and says why: {expected}", expected in str(error), str(error)[:160])

try:
    ld.read("Work out $\\frac{1}{3} + \\frac{1}{2}$ and then $\\frac{1}{4} + \\frac{1}{4}$.", path="test")
    check("text naming two calculations is refused", False, "it picked one")
except ld.DiagramRefused as error:
    check("text naming two calculations is refused", True)
    check(
        "...and says a picture may not choose between them",
        "nobody pointed at" in str(error),
        str(error)[:160],
    )

try:
    ld.draw("friendly_picture", ld.read(SUMS["bar_model"], path="test"), path="test")
    check("a drawing this module does not have is refused", False, "it drew something")
except ld.DiagramRefused as error:
    check("a drawing this module does not have is refused", True, str(error)[:120])


print("\nthe declared mapping says which picture, never what the numbers are")

missing_field = copy(MANIFEST)
del missing_field["diagrams"][0]["appears_after"]

check(
    "a diagram that does not say where it is met is refused",
    "diagrams.0.appears_after is missing" in manifest_module.validate(missing_field),
    str(manifest_module.validate(missing_field)),
)

unknown_kind = copy(MANIFEST)
unknown_kind["diagrams"][0]["kind"] = "friendly_picture"

check(
    "a drawing nothing can draw is refused by the mapping",
    any("is not one of" in problem for problem in manifest_module.validate(unknown_kind)),
    str(manifest_module.validate(unknown_kind)),
)

nowhere_source = copy(MANIFEST)
nowhere_source["diagrams"][0]["numbers_from"] = "core_method"

check(
    "numbers may only come from a worked example or an exercise",
    any("names neither a worked example" in problem for problem in manifest_module.validate(nowhere_source)),
    str(manifest_module.validate(nowhere_source)),
)

no_such_example = copy(MANIFEST)
no_such_example["diagrams"][0]["numbers_from"] = "worked_examples.99"

try:
    export(manifest=no_such_example)
    check("a worked example the lesson does not have is refused", False, "it exported")
except ex.ExportRefused as error:
    check("a worked example the lesson does not have is refused", True)
    check("...and names it", "worked_examples.99" in str(error), str(error)[:160])

prose_example = copy(MANIFEST)
prose_example["diagrams"][0]["numbers_from"] = "worked_examples.0"

try:
    export(manifest=prose_example)
    check("a worked example with no calculation in it is refused", False, "it drew something")
except ex.ExportRefused as error:
    check("a worked example with no calculation in it is refused", True, str(error)[:140])

another_chapter = copy(ITEMS) + [
    {
        "id": "mp-900-ratio_simplify",
        "skill": "ratio_simplify",
        "chapter": 6,
        "prompt": "$$\\frac{1}{3} + \\frac{1}{2}$$",
        "answer_kind": "number",
        "answer_plain": "5/6",
    }
]
foreign_exercise = copy(MANIFEST)
foreign_exercise["diagrams"][1]["numbers_from"] = "exercises.mp-900-ratio_simplify"

try:
    export(manifest=foreign_exercise, items=another_chapter)
    check("a picture of a question this lesson never asks is refused", False, "it exported")
except ex.ExportRefused as error:
    check("a picture of a question this lesson never asks is refused", True)
    check("...and says a learner would never meet it", "met by nobody" in str(error), str(error)[:200])

missing_exercise = copy(MANIFEST)
missing_exercise["diagrams"][1]["numbers_from"] = "exercises.mp-404-add_fractions"

try:
    export(manifest=missing_exercise)
    check("a picture of a question that does not exist is refused", False, "it exported")
except ex.ExportRefused as error:
    check("a picture of a question that does not exist is refused", True, str(error)[:140])

nowhere_to_appear = copy(MANIFEST)
nowhere_to_appear["diagrams"][0]["appears_after"] = "worked_examples.99"

try:
    export(manifest=nowhere_to_appear)
    check("a picture with no place in the lesson is refused", False, "it exported")
except ex.ExportRefused as error:
    check("a picture with no place in the lesson is refused", True)
    check("...and says it would be met nowhere", "met nowhere" in str(error), str(error)[:200])


print("\nthe diagrams ride inside the package, met in the teaching")

package = export()
assets = {asset["stable_key"]: asset for asset in package["assets"]}
blocks = package["teaching_document"]["blocks"]
illustrations = [block for block in blocks if block["type"] == td.ILLUSTRATION_BLOCK_TYPE]
keys = [block["key"] for block in blocks]

check("five concepts, five computed diagrams", len(MANIFEST["diagrams"]) == 5 and len(package["concepts"]) == 5)
check(
    "each one is sealed into the asset channel",
    all(diagram["stable_key"] in assets for diagram in MANIFEST["diagrams"]),
    str(sorted(assets)),
)
check(
    "beside the picture an author drew by hand — one channel, both kinds",
    assets["math5a:ch03:asset:three-quarters-bar"]["provenance"]["origin"] == "manually_authored",
    str(assets["math5a:ch03:asset:three-quarters-bar"]["provenance"]),
)
check(
    "an SVG rides as text, not as bytes",
    all(
        assets[diagram["stable_key"]]["encoding"] == "inline_svg"
        and assets[diagram["stable_key"]]["svg"].startswith("<svg")
        for diagram in MANIFEST["diagrams"]
    ),
)
check(
    "every computed picture says it was drawn for the lesson",
    {assets[diagram["stable_key"]]["provenance"]["origin"] for diagram in MANIFEST["diagrams"]}
    == {"pedagogical_generation"},
)
check(
    "and which code drew it",
    {assets[diagram["stable_key"]]["provenance"]["generator_version"] for diagram in MANIFEST["diagrams"]}
    == {ld.GENERATOR_VERSION},
    ld.GENERATOR_VERSION,
)
check(
    "and what sum it drew",
    "1/3 + 1/2" in assets["math5a:ch03:diagram:add-unlike-fractions"]["provenance"]["generation_reason"],
    assets["math5a:ch03:diagram:add-unlike-fractions"]["provenance"]["generation_reason"],
)
check(
    "a diagram drawn from a worked example rests on what that example rests on",
    bool(assets["math5a:ch03:diagram:add-unlike-fractions"]["provenance"]["grounded_in_source_chunk_ids"]),
)
check(
    "one drawn from a generated exercise rests on nothing, and says so",
    assets["math5a:ch03:diagram:subtract-unlike-fractions"]["provenance"]["grounded_in_source_chunk_ids"] == [],
    "the book asks no such question; naming chunks would claim it does",
)
check(
    "every picture is described for a learner who cannot see it",
    all(asset["alt_text"] and asset["caption"] for asset in package["assets"]),
)
check(
    "and says which concept it teaches",
    {assets[diagram["stable_key"]]["illustrates"] for diagram in MANIFEST["diagrams"]}
    == {concept["stable_key"] for concept in package["concepts"]},
    "one computed diagram per fraction concept",
)

check("five illustration blocks", len(illustrations) == 5, str(len(illustrations)))
check(
    "each is met immediately after the teaching it draws",
    all(
        keys.index(f"illustration.{diagram['stable_key']}") == keys.index(diagram["appears_after"]) + 1
        for diagram in MANIFEST["diagrams"]
    ),
    str([keys.index(block["key"]) for block in illustrations]),
)
check(
    "the block names the picture, and carries its caption and alt text",
    all(
        block["content"]["asset_stable_key"] in assets
        and block["content"]["caption"]
        and block["content"]["alt_text"]
        for block in illustrations
    ),
)
sections = {block["key"]: block["section"] for block in blocks}

check(
    "it sits in the section of the lesson it belongs to",
    all(
        sections[f"illustration.{diagram['stable_key']}"] == sections[diagram["appears_after"]]
        for diagram in MANIFEST["diagrams"]
    ),
    str([block["section"] for block in illustrations]),
)
check(
    "positions are restated, so nothing describes where it used to be",
    [block["position"] for block in blocks] == list(range(len(blocks))),
    str([block["position"] for block in blocks][:6]),
)
check("the whole package is structurally importable", lesson_package.structural_problems(package) == [])

orphaned = copy(package)
orphaned["assets"] = [
    asset for asset in orphaned["assets"] if asset["stable_key"] != "math5a:ch03:diagram:add-unlike-fractions"
]

check(
    "a block showing a picture the package does not carry is refused",
    any("which this package does not carry" in problem for problem in lesson_package.structural_problems(orphaned)),
    str(lesson_package.structural_problems(orphaned)[:2]),
)


print("\nthe hash covers the pictures, and enrichment cannot erase them")

check("the same inputs export to the same hash", export()["content_hash"] == package["content_hash"])
check(
    "the file states its own fingerprint",
    lesson_package.content_hash(package) == package["content_hash"],
)

without_diagrams = copy(MANIFEST)
without_diagrams["diagrams"] = []
undrawn = export(manifest=without_diagrams)

check("a lesson without its diagrams hashes differently", undrawn["content_hash"] != package["content_hash"])
check("because the pictures are inside the thing hashed", len(undrawn["assets"]) == len(package["assets"]) - 5)

richer = copy(MANIFEST)
richer["diagrams"].append(
    {
        "stable_key": "math5a:ch03:diagram:add-unlike-fractions-again",
        "kind": "bar_model",
        "illustrates": "math5a:ch03:add-unlike-fractions",
        "numbers_from": "exercises.mp-010-add_fractions",
        "appears_after": "worked_examples.7",
    }
)
report = enrichment_comparison.compare(package, export(manifest=richer))

check(
    "one more diagram reads as two additions: the picture and the block it is met in",
    enrichment_comparison.summary(report) == "2 added, 0 removed",
    enrichment_comparison.summary(report),
)
check(
    "and the additions name the picture",
    any("add-unlike-fractions-again" in added for added in report["added"]),
    str(report["added"]),
)

try:
    enrichment_comparison.assert_additive(report)
    check("an enriched re-export ships", True)
except enrichment_comparison.EnrichmentRemovedContent as error:
    check("an enriched re-export ships", False, str(error)[:120])

poorer = copy(MANIFEST)
dropped = poorer["diagrams"].pop(3)
loss = enrichment_comparison.compare(package, export(manifest=poorer))

check(
    "dropping a diagram takes its block with it, and both are counted",
    enrichment_comparison.summary(loss) == "0 added, 2 removed",
    enrichment_comparison.summary(loss),
)

try:
    enrichment_comparison.assert_additive(loss)
    check("a re-export that erases a picture is refused", False, "it shipped as an enrichment")
except enrichment_comparison.EnrichmentRemovedContent as error:
    check("a re-export that erases a picture is refused", True)
    check("the refusal names the picture that went missing", dropped["stable_key"] in str(error), str(error)[:200])

redrawn = copy(MANIFEST)
redrawn["diagrams"][0]["numbers_from"] = "exercises.mp-010-add_fractions"
changed = enrichment_comparison.compare(package, export(manifest=redrawn))

check(
    "redrawing one picture from different numbers is a change, not an addition",
    len(changed["removed"]) == 1 and len(changed["added"]) == 1,
    enrichment_comparison.summary(changed),
)


print("\nnothing is fetched: the picture was computed, not downloaded")

# The one address an SVG carries is the namespace that says what an SVG is, and
# nothing fetches it. Everything else that could point outwards must be absent.
NAMESPACE = '<svg xmlns="http://www.w3.org/2000/svg" '
elsewhere_in = [
    marker
    for diagram in MANIFEST["diagrams"]
    for marker in ("http", "<image", "xlink:href", "url(", "<use")
    if marker in assets[diagram["stable_key"]]["svg"].replace(NAMESPACE, "<svg ")
]

check(
    "no drawn picture points anywhere else",
    elsewhere_in == [],
    f"a learner never waits on an image service, but found {elsewhere_in}",
)


class Unplugged(socket.socket):
    def __init__(self, *args, **kwargs):
        raise AssertionError("the export opened a socket")


unplugged, socket.socket = socket.socket, Unplugged

try:
    offline = export()
    check("the whole export draws with the network unplugged", offline["content_hash"] == package["content_hash"])
except AssertionError as error:
    check("the whole export draws with the network unplugged", False, str(error))
finally:
    socket.socket = unplugged


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the same numbers draw the same picture, and it rides inside the file")
raise SystemExit(1 if fails else 0)
