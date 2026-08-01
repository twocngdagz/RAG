"""Domain packs: everything that changes when the book is not PTE.

The system is engine + domain pack. The engine — the generate/check/fix loop, the
evaluator contract, the honesty gate, the teaching schema — is subject-agnostic.
What is subject-specific is declared here, in one place, so adding a book means
adding a pack rather than editing the pipeline.

A pack declares:
  slug          identifies the book; also the output filename prefix
  audience      who the lessons are written for (goes into the prompt)
  ground_truth  what "correct" is checked against — the crucial difference
  evaluators    which checks apply to this domain

The ground truth differs in kind, and that is the interesting part:

  PTE   correctness means "the official Pearson Score Guide says so". That is a
        reading question, so it needs evidence lookup and (for open wording) a
        model judge, which we measured as unreliable for anything mechanical.

  Maths correctness is COMPUTABLE. 4 x 3 = 10 is false with no judgement and no
        evidence lookup. The maths pack's core check is therefore fully
        deterministic — a stronger guarantee than PTE can have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DomainPack:
    slug: str
    # What this pack's rules and wording are, as a version an emitted package
    # can name. A package says which pack produced it so that a lesson emitted
    # under last month's rules is identifiable as such rather than silently
    # assumed to match today's.
    #
    # Bump this when the pack changes anything that alters the lessons it
    # produces: the audience, the ground truth, the evaluators, the limits.
    version: str
    title: str
    audience: str
    ground_truth: str
    # Evaluator names (in pipeline_evaluators.REGISTRY) that apply to this domain.
    evaluators: tuple[str, ...] = ()
    # Highest US reading-grade the prose may reach. None = no limit (adult
    # audiences). A children's book that reads at grade 9 has failed regardless
    # of how correct its content is.
    reading_grade_max: float | None = None
    # Fewest worked examples a lesson may ship with. Worked examples are the
    # single most useful thing in a lesson, and simplifying the prose must not
    # be allowed to quietly cost them (it did: 4.7 -> 2.7 per lesson).
    min_worked_examples: int = 3
    # Wording used in the PER-LESSON message sent with each chapter. This was
    # hardcoded to PTE and leaked "PTE LESSON" and PTE task-type examples into a
    # maths run — the standing project prompt was right, but every message
    # contradicted it.
    task_type_examples: str = "'summarize_written_text'"
    payload_note: str = ""
    # Where this book's files live; {n} is the chapter number.
    base_file: str = "output/{slug}.chapter{n:02d}.book_learning_materials.json"
    enrich_file: str = "output/{slug}.chapter{n:02d}.enrichment.json"
    notes: str = ""

    def base_path(self, n: int) -> str:
        return self.base_file.format(slug=self.slug, n=n)

    def enrich_path(self, n: int) -> str:
        return self.enrich_file.format(slug=self.slug, n=n)


REGISTRY: dict[str, DomainPack] = {
    "pte": DomainPack(
        slug="pte",
        version="1.0.0",
        title="PTE Academic",
        audience="adult test takers, CEFR B1-C1, preparing for PTE Academic",
        ground_truth="the official Pearson PTE Academic Score Guide (PDF)",
        evaluators=("word_range", "trait_names", "worked_example_rules"),
        reading_grade_max=None,   # adult test takers; no child-level constraint
        min_worked_examples=3,    # the existing 19 PTE lessons all meet this
        task_type_examples="'summarize_written_text'",
        payload_note=(
            "Adapt content to this task type, but keep the shape identical. For "
            "non-speaking\ntasks, model_answer may be a written sample or a worked "
            "selection; still provide\nit as a string. useful_language must be a list "
            "of {category, items:[{item,\nwhen_to_use}]} — for reading/selection tasks "
            "use signpost words, linkers, and\noption-elimination phrases rather than "
            "leaving it empty."
        ),
        notes=("Scoring facts are checked against the Score Guide. Mechanical checks "
               "are deterministic; the model judge is advisory only, having been "
               "measured unreliable on numeric contradictions."),
    ),
    "math5a": DomainPack(
        slug="math5a",
        version="1.0.0",
        title="Singapore Math Primary Mathematics 5A",
        audience="Year 5 / Grade 5 pupils (about 10-11 years old) and their teachers",
        ground_truth="arithmetic itself — every calculation is evaluated exactly",
        evaluators=("math_arithmetic", "reading_level"),
        reading_grade_max=6.0,    # 10-11 year olds; grade 5-6 prose
        min_worked_examples=4,    # children learn from demonstrations
        task_type_examples="'fractions', 'word_problems', 'area_and_perimeter'",
        payload_note=(
            "Adapt content to this topic, but keep the shape identical.\n"
            "- Write EVERY calculation in LaTeX inside dollar signs: $\\frac{3}{4}$, "
            "$2\\frac{1}{2}$, $12 \\div 4 = 3$. This is checked automatically.\n"
            "- Division with a remainder: say the remainder — $74 \\div 21 = 3 "
            "\\text{ r } 11$, never $74 \\div 21 = 3$.\n"
            "- model_answer is the COMPLETE solution: the full working, step by step, "
            "then the answer in a sentence.\n"
            "- useful_language is the maths words a pupil needs (bottom number, "
            "product, remainder) and when to use each.\n"
            "- Write for a 10-year-old: about 10 words a sentence, everyday words. "
            "Name a technical term once, then use plain words."
        ),
        notes=("Correctness here is computable, so the core check needs no judge and "
               "no evidence lookup. Blanks (the pupil's answer) are skipped, never "
               "flagged. Source text comes from LlamaParse, which preserves fractions "
               "as LaTeX — generic OCR destroys them and must not be used."),
    ),
}

DEFAULT_SLUG = "pte"


def get(slug: str) -> DomainPack:
    if slug not in REGISTRY:
        raise KeyError(f"unknown domain pack {slug!r}; have {sorted(REGISTRY)}")
    return REGISTRY[slug]


def slug_of(doc: dict[str, Any]) -> str:
    """Which book a lesson belongs to.

    Prefers an explicit "domain"/"book_slug"; otherwise reads the slug out of
    source_label ("pte:ch07"). Falls back to the default rather than raising, so a
    lesson without provenance is still checkable — but see domain_of, which is the
    one callers should use.
    """
    for key in ("domain", "book_slug"):
        v = doc.get(key)
        if isinstance(v, str) and v.strip() in REGISTRY:
            return v.strip()
    label = doc.get("source_label")
    if isinstance(label, str) and ":" in label:
        candidate = label.split(":", 1)[0].strip()
        if candidate in REGISTRY:
            return candidate
    return DEFAULT_SLUG


def domain_of(doc: dict[str, Any]) -> DomainPack:
    return get(slug_of(doc))
