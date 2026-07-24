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
        title="PTE Academic",
        audience="adult test takers, CEFR B1-C1, preparing for PTE Academic",
        ground_truth="the official Pearson PTE Academic Score Guide (PDF)",
        evaluators=("word_range", "trait_names", "worked_example_rules"),
        reading_grade_max=None,   # adult test takers; no child-level constraint
        min_worked_examples=3,    # the existing 19 PTE lessons all meet this
        notes=("Scoring facts are checked against the Score Guide. Mechanical checks "
               "are deterministic; the model judge is advisory only, having been "
               "measured unreliable on numeric contradictions."),
    ),
    "math5a": DomainPack(
        slug="math5a",
        title="Singapore Math Primary Mathematics 5A",
        audience="Year 5 / Grade 5 pupils (about 10-11 years old) and their teachers",
        ground_truth="arithmetic itself — every calculation is evaluated exactly",
        evaluators=("math_arithmetic", "reading_level"),
        reading_grade_max=6.0,    # 10-11 year olds; grade 5-6 prose
        min_worked_examples=4,    # children learn from demonstrations
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
