"""Teaching diagrams, drawn from the maths itself.

A picture in a maths lesson carries mathematical content. A cartoon cutting
pizzas into thirds when the problem says quarters teaches the wrong thing, so
these pictures are not drawn by a model and not drawn by hand: they are COMPUTED
from the numbers in the worked example or exercise they illustrate. The same
input always draws the same picture, byte for byte, and a test proves it.

Three drawings, one per shape of teaching:

    bar_model    two bars for the two amounts and a third for the answer, each
                 split into its own equal parts. This is what "make the bottom
                 numbers match" looks like.
    area_model   one square split both ways: the first fraction across, the
                 second down, and the cells where they cross are the product.
    step_layout  the method as numbered steps, each line the working a learner
                 would write, with the sentence that says what the step does.

WHAT THIS MODULE REFUSES. A picture that does not say what the sum says is worse
than no picture, so a diagram is refused rather than approximated: a mixed
number this module cannot draw, text naming no calculation or naming two, an
area model asked to draw more than one whole, a bar model asked to draw a
multiplication. Every refusal names the path and the reason.

NOTHING IS FETCHED. An SVG is text, computed here from integers. There is no
image service, no key, no network — a learner meets the picture because it was
computed at authoring time and sealed into the package.

Friendly generated images — the second kind of illustration the decision names —
are NOT here. They need a hosted image model and the author-approval gate, and
neither exists yet; inventing a stub for them would produce machinery that
passes its own tests and draws nothing real.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from math import lcm
from typing import Any

import lesson_provenance

# Bump when a change here alters the pictures this file draws. It rides in every
# diagram's provenance, so a package emitted last month is not silently assumed
# to have been drawn by today's code.
GENERATOR_VERSION = "rag-diagrams/1.0.0"

# SVG, because a computed diagram is text: inspectable, diffable, and covered by
# the package's hash as the characters it actually is.
MEDIA_TYPE = "image/svg+xml"

# Which drawing a diagram asks for. The author picks — which picture teaches
# this best is a teaching decision — and the drawing refuses a calculation it
# cannot express rather than drawing something else.
KINDS = ("bar_model", "area_model", "step_layout")

ADD, SUBTRACT, MULTIPLY, DIVIDE = "+", "−", "×", "÷"

# A bar split into sixty slivers is not a picture a learner can read. Generous,
# because every fraction pair this book asks about lands far below it.
MOST_PARTS_DRAWN = 60

# The palette. Two shaded tones and one ink, so a diagram reads the same in a
# lesson as in a printed worksheet.
INK = "#1f4e79"
SHADED = "#cfe8ff"
CROSSED = "#7bb8e8"
PAPER = "#ffffff"
QUIET = "#5a6b7b"

_FRACTION = r"\\frac\{(\d+)\}\{(\d+)\}"
_TERM = rf"(?:{_FRACTION}|(\d+))"
_OPERATOR = r"(\+|-|\\times|\\div|×|÷)"
_CALCULATION = re.compile(rf"{_TERM}\s*{_OPERATOR}\s*{_TERM}")

# A digit sitting directly against a fraction is a mixed number. Reading
# `3\frac{1}{4}` as `3` would draw a completely different sum, so it stops here.
_MIXED_NUMBER = re.compile(r"\d\s*\\frac")

_OPERATOR_NAMES = {
    "+": ADD,
    "-": SUBTRACT,
    "\\times": MULTIPLY,
    "×": MULTIPLY,
    "\\div": DIVIDE,
    "÷": DIVIDE,
}


class DiagramRefused(Exception):
    """A picture cannot be drawn from these numbers, and why."""


@dataclass(frozen=True)
class Term:
    """One number as the question writes it, unsimplified.

    `2/4` keeps four parts. Reducing it to a half before drawing would show a
    learner a bar the exercise never mentioned.
    """

    numerator: int
    denominator: int

    @property
    def value(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    @property
    def is_whole(self) -> bool:
        return self.denominator == 1

    @property
    def written(self) -> str:
        return str(self.numerator) if self.is_whole else f"{self.numerator}/{self.denominator}"


@dataclass(frozen=True)
class Calculation:
    """The sum a picture is drawn from."""

    left: Term
    operator: str
    right: Term

    @property
    def result(self) -> Fraction:
        if self.operator == ADD:
            return self.left.value + self.right.value

        if self.operator == SUBTRACT:
            return self.left.value - self.right.value

        if self.operator == MULTIPLY:
            return self.left.value * self.right.value

        return self.left.value / self.right.value

    @property
    def written(self) -> str:
        return f"{self.left.written} {self.operator} {self.right.written}"


def read(text: str, *, path: str) -> Calculation:
    """The calculation a piece of teaching asks about, or a refusal.

    Reads the question's own words — `Work out $\\frac{1}{3} + \\frac{1}{2}$.` —
    rather than taking numbers from a manifest, so the picture cannot drift from
    the example it sits beside. Anything ambiguous is refused: a picture drawn
    from a guess about which sum was meant is a picture that teaches a sum
    nobody wrote.
    """
    source = str(text or "").strip()

    if not source:
        raise DiagramRefused(f"{path} has no text to read numbers from")

    if _MIXED_NUMBER.search(source):
        raise DiagramRefused(
            f"{path} carries a mixed number, which this module does not draw; "
            f"reading it as a whole number would draw a different sum"
        )

    found = _CALCULATION.findall(source)

    if not found:
        raise DiagramRefused(
            f"{path} names no calculation two numbers apart, so there is nothing to draw: {source[:60]!r}"
        )

    if len(found) > 1:
        raise DiagramRefused(
            f"{path} names {len(found)} calculations and a picture can only draw one; "
            f"choosing between them would draw a sum nobody pointed at"
        )

    # Top and bottom, the words the lesson itself uses for a fraction's two
    # numbers; a whole number arrives on its own and is read as itself over one.
    left_top, left_bottom, left_whole, operator, right_top, right_bottom, right_whole = found[0]

    left = Term(int(left_whole), 1) if left_whole else Term(int(left_top), int(left_bottom))
    right = Term(int(right_whole), 1) if right_whole else Term(int(right_top), int(right_bottom))

    if left.is_whole and right.is_whole:
        raise DiagramRefused(f"{path} names no fraction, so there are no equal parts to draw")

    for label, term in (("left", left), ("right", right)):
        if term.denominator == 0:
            raise DiagramRefused(f"{path} divides by zero on the {label}")

    calculation = Calculation(left, _OPERATOR_NAMES[operator], right)

    if calculation.operator == DIVIDE and calculation.right.value == 0:
        raise DiagramRefused(f"{path} divides by zero")

    return calculation


def draw(kind: str, calculation: Calculation, *, path: str) -> dict[str, str]:
    """One picture, its caption and its alt text — all computed from the numbers.

    The caption and the alt text are computed rather than authored for the same
    reason the drawing is: written by hand they could say quarters while the
    picture shows thirds, and the learner who cannot see the picture is the one
    who would never find out.
    """
    if kind not in KINDS:
        raise DiagramRefused(f"{path} asks for {kind!r}, which is not one of {', '.join(KINDS)}")

    if kind == "bar_model":
        return _bar_model(calculation, path=path)

    if kind == "area_model":
        return _area_model(calculation, path=path)

    return _step_layout(calculation, path=path)


def build(
    declared: dict[str, Any],
    *,
    source_text: str,
    source_reference: str,
    grounded_in_source_chunk_ids: list[str],
    path: str,
) -> dict[str, Any]:
    """One declared diagram, drawn and handed over as an asset declaration.

    A computed diagram enters the package through the SAME gate every other
    picture goes through — `lesson_assets` reads this and seals it in. A second
    way into the asset channel would be a second answer to what an asset is.
    """
    if not isinstance(declared, dict):
        raise DiagramRefused(f"{path} is not an object")

    key = str(declared.get("stable_key") or "").strip()

    if not key:
        raise DiagramRefused(f"{path} has no stable_key")

    kind = str(declared.get("kind") or "").strip()
    illustrates = str(declared.get("illustrates") or "").strip()

    if not illustrates:
        raise DiagramRefused(f"{path} does not say what it illustrates")

    calculation = read(source_text, path=f"{path} -> {source_reference}")
    drawing = draw(kind, calculation, path=path)

    return {
        "stable_key": key,
        "media_type": MEDIA_TYPE,
        "illustrates": illustrates,
        "alt_text": drawing["alt_text"],
        "caption": drawing["caption"],
        "svg": drawing["svg"],
        "provenance": {
            "origin": lesson_provenance.PEDAGOGICAL_GENERATION,
            # What the drawing rests on. A diagram computed from a worked
            # example inherits that example's grounding; one computed from a
            # generated exercise rests on no passage of the book, and says so by
            # carrying nothing.
            "grounded_in_source_chunk_ids": sorted(set(grounded_in_source_chunk_ids)),
            "generation_reason": (
                f"{'An' if kind[0] in 'aeiou' else 'A'} {kind.replace('_', ' ')} computed from the "
                f"numbers in {source_reference}: {calculation.written}"
            ),
            "generator_version": GENERATOR_VERSION,
        },
    }


# --------------------------------------------------------------------------- #
# Bar model
# --------------------------------------------------------------------------- #

# Geometry, in the picture's own units and stated here rather than measured. A
# drawing that asked a font or a screen how wide something was would come out
# differently on a different machine, and the same numbers must always draw the
# same picture.
TOP_MARGIN = 16
BAR_WIDTH = 320
BAR_HEIGHT = 44
ROW_GAP = 30
GUTTER = 44
BAR_GAP = 8


def _bar_model(calculation: Calculation, *, path: str) -> dict[str, str]:
    """Two amounts and their answer, each as a bar split into its own parts."""
    if calculation.operator not in (ADD, SUBTRACT):
        raise DiagramRefused(
            f"{path} asks for a bar model of a {calculation.operator} calculation; bars "
            f"drawn side by side show joining and taking away, not {calculation.operator}"
        )

    if calculation.result < 0:
        raise DiagramRefused(
            f"{path} would draw {calculation.written} = {_written(calculation.result)}, and there is "
            f"no bar for less than nothing"
        )

    shared = lcm(calculation.left.denominator, calculation.right.denominator)

    if max(shared, calculation.left.denominator, calculation.right.denominator) > MOST_PARTS_DRAWN:
        raise DiagramRefused(
            f"{path} would split a bar into {shared} parts; that is not a picture a learner can read"
        )

    answer_parts = calculation.result.numerator * (shared // calculation.result.denominator)
    answer_bars = max(1, -(-answer_parts // shared))
    widest = max(1, answer_bars)

    label_x = GUTTER + widest * (BAR_WIDTH + BAR_GAP) + 12
    width = label_x + 96
    height = TOP_MARGIN + 3 * (BAR_HEIGHT + ROW_GAP) - ROW_GAP + TOP_MARGIN

    body: list[str] = []
    rows = (
        (calculation.left.numerator, calculation.left.denominator, 1, ""),
        (calculation.right.numerator, calculation.right.denominator, 1, calculation.operator),
        (answer_parts, shared, answer_bars, "="),
    )

    for index, (shaded, parts, bars, sign) in enumerate(rows):
        y = TOP_MARGIN + index * (BAR_HEIGHT + ROW_GAP)

        if sign:
            body.append(_text(GUTTER - 22, y + BAR_HEIGHT // 2 + 8, sign, size=22, anchor="middle"))

        body.extend(_bar_row(GUTTER, y, parts=parts, shaded=shaded, bars=bars))
        body.extend(
            _written_label(label_x, y + BAR_HEIGHT // 2, shaded, parts)
            if index < 2
            else _result_label(label_x, y + BAR_HEIGHT // 2, calculation.result)
        )

    caption = f"Bar model: {calculation.written} = {_written(calculation.result)}."
    alt_text = (
        f"Three bars. The first is split into {_parts_phrase(calculation.left.denominator)} "
        f"with {calculation.left.numerator} shaded. The second is split into "
        f"{_parts_phrase(calculation.right.denominator)} with {calculation.right.numerator} shaded. "
        f"The answer bar is split into {_parts_phrase(shared)} with {answer_parts} shaded, "
        f"which is {_written(calculation.result)}."
    )

    return {
        "svg": _svg(width, height, body, caption=caption, alt_text=alt_text),
        "caption": caption,
        "alt_text": alt_text,
    }


def _bar_row(x: int, y: int, *, parts: int, shaded: int, bars: int) -> list[str]:
    """One row of the model: whole bars side by side, each split into equal parts."""
    drawn: list[str] = []

    for index in range(bars):
        left = x + index * (BAR_WIDTH + BAR_GAP)
        filled = min(max(shaded - index * parts, 0), parts)
        drawn.extend(_bar(left, y, parts=parts, shaded=filled))

    return drawn


def _bar(x: int, y: int, *, parts: int, shaded: int) -> list[str]:
    drawn = [
        f'<rect x="{x}" y="{y}" width="{BAR_WIDTH}" height="{BAR_HEIGHT}" fill="{PAPER}"/>',
    ]

    if shaded:
        drawn.append(
            f'<rect x="{x}" y="{y}" width="{_tick(shaded, parts, BAR_WIDTH)}" '
            f'height="{BAR_HEIGHT}" fill="{SHADED}"/>'
        )

    drawn.append(f'<g stroke="{INK}" stroke-width="2" fill="none">')
    drawn.append(f'<rect x="{x}" y="{y}" width="{BAR_WIDTH}" height="{BAR_HEIGHT}"/>')

    for part in range(1, parts):
        at = x + _tick(part, parts, BAR_WIDTH)
        drawn.append(f'<line x1="{at}" y1="{y}" x2="{at}" y2="{y + BAR_HEIGHT}"/>')

    drawn.append("</g>")

    return drawn


# --------------------------------------------------------------------------- #
# Area model
# --------------------------------------------------------------------------- #

SQUARE = 288
SQUARE_X = 64
SQUARE_Y = TOP_MARGIN


def _area_model(calculation: Calculation, *, path: str) -> dict[str, str]:
    """One whole, cut both ways: the cells where the two fractions cross."""
    if calculation.operator != MULTIPLY:
        raise DiagramRefused(
            f"{path} asks for an area model of a {calculation.operator} calculation; a square cut "
            f"both ways shows one fraction OF another, which is multiplication"
        )

    for label, term in (("left", calculation.left), ("right", calculation.right)):
        if term.value > 1:
            raise DiagramRefused(
                f"{path} would draw {term.written} on the {label} of one square, and "
                f"{term.written} is more than one whole"
            )

    columns, rows = calculation.left.denominator, calculation.right.denominator

    if max(columns, rows) > MOST_PARTS_DRAWN:
        raise DiagramRefused(
            f"{path} would cut a square into {columns} by {rows} cells; that is not a picture "
            f"a learner can read"
        )

    across, down = calculation.left.numerator, calculation.right.numerator
    crossed_width = _tick(across, columns, SQUARE)
    crossed_height = _tick(down, rows, SQUARE)

    body = [
        f'<rect x="{SQUARE_X}" y="{SQUARE_Y}" width="{SQUARE}" height="{SQUARE}" fill="{PAPER}"/>',
        f'<rect x="{SQUARE_X}" y="{SQUARE_Y}" width="{crossed_width}" height="{SQUARE}" fill="{SHADED}"/>',
        f'<rect x="{SQUARE_X}" y="{SQUARE_Y}" width="{SQUARE}" height="{crossed_height}" fill="{SHADED}"/>',
        f'<rect x="{SQUARE_X}" y="{SQUARE_Y}" width="{crossed_width}" height="{crossed_height}" fill="{CROSSED}"/>',
        f'<g stroke="{INK}" stroke-width="2" fill="none">',
        f'<rect x="{SQUARE_X}" y="{SQUARE_Y}" width="{SQUARE}" height="{SQUARE}"/>',
    ]

    for column in range(1, columns):
        at = SQUARE_X + _tick(column, columns, SQUARE)
        body.append(f'<line x1="{at}" y1="{SQUARE_Y}" x2="{at}" y2="{SQUARE_Y + SQUARE}"/>')

    for row in range(1, rows):
        at = SQUARE_Y + _tick(row, rows, SQUARE)
        body.append(f'<line x1="{SQUARE_X}" y1="{at}" x2="{SQUARE_X + SQUARE}" y2="{at}"/>')

    body.append("</g>")

    # The first fraction reads along the bottom, the second down the side: the
    # picture is labelled where the cuts were made.
    body.extend(_written_label(SQUARE_X + crossed_width // 2 - 12, SQUARE_Y + SQUARE + 34, across, columns))
    body.extend(_written_label(12, SQUARE_Y + crossed_height // 2, down, rows))
    body.append(_text(SQUARE_X + SQUARE + 16, SQUARE_Y + SQUARE // 2 + 8, "=", size=22, anchor="start"))
    body.extend(_result_label(SQUARE_X + SQUARE + 42, SQUARE_Y + SQUARE // 2, calculation.result))

    cells = columns * rows
    crossed = across * down
    caption = f"Area model: {calculation.written} = {_written(calculation.result)}."
    alt_text = (
        f"A square split into {columns} columns and {rows} rows, making {cells} equal cells. "
        f"{across} of the {columns} columns are shaded for {calculation.left.written} and "
        f"{down} of the {rows} rows for {calculation.right.written}. The {crossed} cells where they "
        f"cross are the answer, {crossed} out of {cells}, which is {_written(calculation.result)}."
    )

    return {
        "svg": _svg(
            SQUARE_X + SQUARE + 128,
            SQUARE_Y + SQUARE + 56,
            body,
            caption=caption,
            alt_text=alt_text,
        ),
        "caption": caption,
        "alt_text": alt_text,
    }


# --------------------------------------------------------------------------- #
# Step layout
# --------------------------------------------------------------------------- #

STEP_HEIGHT = 46
STEP_WIDTH = 700


def _step_layout(calculation: Calculation, *, path: str) -> dict[str, str]:
    """The method as numbered steps: the working, and what each line is doing."""
    steps = _steps(calculation)
    height = TOP_MARGIN + len(steps) * STEP_HEIGHT + 8
    body: list[str] = []

    for index, (working, doing) in enumerate(steps):
        y = TOP_MARGIN + index * STEP_HEIGHT
        body.extend(
            [
                f'<rect x="12" y="{y}" width="{STEP_WIDTH - 24}" height="{STEP_HEIGHT - 8}" '
                f'rx="6" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>',
                _text(34, y + 26, f"{index + 1}", size=16, anchor="middle", fill=QUIET),
                _text(52, y + 26, working, size=19, anchor="start"),
                _text(330, y + 26, doing, size=13, anchor="start", fill=QUIET),
            ]
        )

    caption = f"Step by step: {calculation.written} = {_written(calculation.result)}."
    alt_text = f"{_count_phrase(len(steps))} steps: " + "; ".join(
        f"{working} — {doing.rstrip('.').lower()}" for working, doing in steps
    ) + "."

    return {
        "svg": _svg(STEP_WIDTH, height, body, caption=caption, alt_text=alt_text),
        "caption": caption,
        "alt_text": alt_text,
    }


def _steps(calculation: Calculation) -> list[tuple[str, str]]:
    """Each line of working, computed by exact arithmetic — never a model's idea of it."""
    left, right = calculation.left, calculation.right
    steps: list[tuple[str, str]] = [(calculation.written, "Start with the question.")]

    if calculation.operator in (ADD, SUBTRACT):
        shared = lcm(left.denominator, right.denominator)
        left_parts = left.numerator * (shared // left.denominator)
        right_parts = right.numerator * (shared // right.denominator)
        total = left_parts + right_parts if calculation.operator == ADD else left_parts - right_parts

        steps.append(
            (
                f"{left_parts}/{shared} {calculation.operator} {right_parts}/{shared}",
                "Make the bottom numbers match.",
            )
        )
        steps.append(
            (
                f"= {total}/{shared}",
                "Add the top numbers." if calculation.operator == ADD else "Subtract the top numbers.",
            )
        )
    else:
        multiplier = right if calculation.operator == MULTIPLY else Term(right.denominator, right.numerator)

        if calculation.operator == DIVIDE:
            steps.append(
                (
                    f"{left.written} {MULTIPLY} {multiplier.numerator}/{multiplier.denominator}",
                    "Turn the number you are dividing by upside down, then multiply.",
                )
            )

        top = left.numerator * multiplier.numerator
        bottom = left.denominator * multiplier.denominator

        # Written the way the book writes it: a whole number contributes no
        # bottom number to multiply by, so `2/3 × 12` becomes (2 × 12)/3 rather
        # than (2 × 12)/(3 × 1).
        bottom_line = (
            str(left.denominator * multiplier.denominator)
            if 1 in (left.denominator, multiplier.denominator)
            else f"({left.denominator} {MULTIPLY} {multiplier.denominator})"
        )

        steps.append(
            (
                f"({left.numerator} {MULTIPLY} {multiplier.numerator})/{bottom_line}",
                "Multiply the top numbers, then the bottom numbers.",
            )
        )
        steps.append((f"= {top}/{bottom}", "That is the answer, before it is made simpler."))

    steps.append((f"= {_written(calculation.result)}", "Write the answer in its simplest form."))

    return steps


# --------------------------------------------------------------------------- #
# Drawing helpers — no measurement, no randomness, integers only
# --------------------------------------------------------------------------- #


def _svg(width: int, height: int, body: list[str], *, caption: str, alt_text: str) -> str:
    """The finished picture, carrying its own title and description.

    Written with the caption and alt text inside it as well as beside it, so the
    file still describes itself when it is opened on its own.
    """
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" font-family="sans-serif">',
            f"<title>{_escaped(caption)}</title>",
            f"<desc>{_escaped(alt_text)}</desc>",
            *body,
            "</svg>",
        ]
    )


def _tick(part: int, parts: int, across: int) -> int:
    """Where the nth cut falls. Rounded to a whole unit so the picture is exact."""
    return round(across * part / parts)


def _text(x: int, y: int, value: str, *, size: int, anchor: str = "middle", fill: str = INK) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="{fill}">{_escaped(value)}</text>'
    )


def _written_label(x: int, y: int, numerator: int, denominator: int) -> list[str]:
    """A number as the question writes it: stacked, and not reduced on the way."""
    if denominator == 1:
        return [_text(x + 12, y + 7, str(numerator), size=20)]

    return [
        _text(x + 12, y - 5, str(numerator), size=17),
        f'<line x1="{x}" y1="{y}" x2="{x + 24}" y2="{y}" stroke="{INK}" stroke-width="2"/>',
        _text(x + 12, y + 19, str(denominator), size=17),
    ]


def _result_label(x: int, y: int, value: Fraction) -> list[str]:
    """The answer, written as a Year-5 pupil writes it: whole part, then the rest."""
    whole, remainder = divmod(abs(value.numerator), value.denominator)
    sign = "-" if value < 0 else ""
    drawn: list[str] = []
    cursor = x

    if whole or not remainder:
        drawn.append(_text(cursor + 8, y + 7, f"{sign}{whole}", size=20))
        cursor += 20 + 8 * len(str(whole))
        sign = ""

    if remainder:
        drawn.extend(_written_label(cursor, y, remainder, value.denominator))

    return drawn


def _written(value: Fraction) -> str:
    """A fraction in plain words-on-a-line form: '5/6', '1 1/12', '8'."""
    if value.denominator == 1:
        return str(value.numerator)

    whole, remainder = divmod(abs(value.numerator), value.denominator)
    sign = "-" if value < 0 else ""

    if whole:
        return f"{sign}{whole} {remainder}/{value.denominator}"

    return f"{sign}{remainder}/{value.denominator}"


_PARTS_IN_WORDS = {
    2: "halves",
    3: "thirds",
    4: "quarters",
    5: "fifths",
    6: "sixths",
    8: "eighths",
    10: "tenths",
    12: "twelfths",
}

_COUNT_IN_WORDS = {3: "Three", 4: "Four", 5: "Five"}


def _parts_phrase(parts: int) -> str:
    """'6 equal parts (sixths)' — the same words the lesson uses, where it has them."""
    named = _PARTS_IN_WORDS.get(parts)

    return f"{parts} equal parts ({named})" if named else f"{parts} equal parts"


def _count_phrase(count: int) -> str:
    return _COUNT_IN_WORDS.get(count, str(count))


def _escaped(value: str) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
