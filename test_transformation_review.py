"""The review gate: does an approval license exactly one claim, and nothing else?

The risk this guards is not that the mechanism fails closed -- an approval that
does not load simply refuses, and content is lost, which is loud. The risk is
that it fails OPEN: an approval keeps licensing a claim after the claim was
reworded, or after the book was reparsed, and `source_transformed` goes on
asserting that a person checked something they never read.

So most of what follows edits one thing and asserts the approval stops working.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import math_claim_grounding as grounding
import transformation_review as review

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  -- {detail}" if detail and not cond else ""))

    if not cond:
        fails.append(label)


CHUNKS = [
    {"node_id": "math5a:p32", "text": "Here is another way to show that 5 div 4 = 5/4. Each child receives 1 pancake first."},
    {"node_id": "math5a:p33", "text": "A bucket contains 8 qt of water poured equally into 3 jugs."},
]

CLAIM = "Dividing a whole by a number creates a fraction."
PATH = "chapter03.core_lessons.0.explanation"
REVIEWER = {"id": "content-owner@example.test", "name": "A Content Owner", "kind": review.REVIEWER_HUMAN}


def manifest(**overrides) -> dict:
    approval = {
        "claim_path": PATH,
        "claim_hash": review.claim_hash(CLAIM),
        "source_content_revision": review.source_revision(CHUNKS),
        "source_chunk_ids": ["math5a:p32"],
        "transformation_type": "demonstration_to_statement",
        "reviewer": REVIEWER,
        "reviewed_at": "2026-08-01T00:00:00Z",
        "verdict": review.VERDICT_FAITHFUL,
    }
    approval.update(overrides)

    return {
        "schema_version": review.REVIEW_SCHEMA_VERSION,
        "chapter_number": 3,
        "approvals": [approval],
    }


def approvals(**overrides) -> review.ApprovalSet:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "review.json"
        path.write_text(json.dumps(manifest(**overrides)), encoding="utf-8")

        return review.load(path, chapter_number=3)


def build(text: str = CLAIM, chunks=None, approval_set=None, path: str | None = PATH) -> dict:
    return grounding.build_claim(
        text,
        "core_lessons",
        chunks if chunks is not None else CHUNKS,
        claim_path=path,
        approvals=approval_set,
    )


# --- the claim is not quotable, so it never grounds ------------------------- #

claim = build()
check("unquotable prose is never source_grounded", claim["origin"] != "source_grounded", claim["origin"])

# --- without approvals, it refuses ------------------------------------------ #

check("no approvals means refusal", build()["origin"] == "insufficient_source_evidence")
check("refusal carries no text", build()["text"] is None)

# --- with a matching approval, it transforms -------------------------------- #

ok = build(approval_set=approvals())
check("a matching approval yields source_transformed", ok["origin"] == "source_transformed", ok["origin"])
check("transformed claim keeps its text", ok["text"] == CLAIM)
check("transformed claim names the reviewed chunks", ok["source_chunk_ids"] == ["math5a:p32"])
check("transformed claim names the transformation", ok["transformation"] == "demonstration_to_statement")
check("transformed claim records who approved it", ok["reviewed_by"] == REVIEWER["id"])
check("transformed claim quotes no source words", ok["evidence_spans"] == [])
check("transformed claim is not also grounded", ok["grounded_in_source_chunk_ids"] == [])

# --- editing the claim invalidates the approval ----------------------------- #

reworded = build("Dividing a whole by a number always creates a fraction.", approval_set=approvals())
check("rewording the claim invalidates approval", reworded["origin"] == "insufficient_source_evidence", reworded["origin"])
check("rewording says why", "reworded" in (reworded["reason"] or ""), reworded["reason"] or "")

# --- editing the source invalidates the approval ---------------------------- #

reparsed = [dict(CHUNKS[0], text=CHUNKS[0]["text"] + " Extra line from a reparse."), CHUNKS[1]]
stale = build(chunks=reparsed, approval_set=approvals())
check("changing the source invalidates approval", stale["origin"] == "insufficient_source_evidence", stale["origin"])
check("stale source says why", "source has changed" in (stale["reason"] or ""), stale["reason"] or "")

# A reparse that keeps the ids but changes the words must still invalidate --
# an id-only revision would silently keep approving.
check(
    "revision covers chunk text, not just ids",
    review.source_revision(CHUNKS) != review.source_revision(reparsed),
)

# --- a rejection is not merely an absence ----------------------------------- #

rejected = build(approval_set=approvals(verdict=review.VERDICT_UNFAITHFUL))
check("a rejected transformation refuses", rejected["origin"] == "insufficient_source_evidence")
check("rejection says a reviewer rejected it", "rejected" in (rejected["reason"] or ""), rejected["reason"] or "")

# --- an approval licenses ONE claim path ------------------------------------ #

other = build(path="chapter03.core_lessons.1.explanation", approval_set=approvals())
check("approval does not leak to another claim path", other["origin"] == "insufficient_source_evidence", other["origin"])

pathless = build(path=None, approval_set=approvals())
check("a claim with no path cannot be approved", pathless["origin"] == "insufficient_source_evidence")

# --- approvals naming absent chunks are wrong, not stale -------------------- #

absent = build(approval_set=approvals(source_chunk_ids=["math5a:p99"]))
check("approval against a chunk not in the chapter refuses", absent["origin"] == "insufficient_source_evidence")
check("absent chunk is named in the reason", "math5a:p99" in (absent["reason"] or ""), absent["reason"] or "")

# --- generated claims never consult approvals ------------------------------- #

generated = grounding.build_claim(
    "Try five of these on your own.",
    "practice_question",
    CHUNKS,
    claim_path=PATH,
    approvals=approvals(),
)
check("a generated kind is never transformed", generated["origin"] == "pedagogical_generation", generated["origin"])

# --- manifest validation ----------------------------------------------------- #

problems = review.validate(manifest(), chapter_number=3)
check("a complete manifest validates", problems == [], "; ".join(problems))

check(
    "a manifest for another chapter is rejected",
    any("chapter" in p for p in review.validate(manifest(), chapter_number=4)),
)

bad = manifest()
bad["approvals"].append(dict(bad["approvals"][0], verdict=review.VERDICT_UNFAITHFUL))
check(
    "two verdicts for one claim are rejected",
    any("second time" in p for p in review.validate(bad, chapter_number=3)),
)

for field in review.REQUIRED_APPROVAL_FIELDS:
    incomplete = manifest()
    incomplete["approvals"][0].pop(field)
    check(
        f"a manifest missing {field} is rejected",
        any(field in p for p in review.validate(incomplete, chapter_number=3)),
    )

check(
    "an unknown transformation type is rejected",
    any("transformation_type" in p for p in review.validate(manifest(transformation_type="vibes"), chapter_number=3)),
)

check(
    "an anonymous reviewer is rejected",
    any("reviewer" in p for p in review.validate(manifest(reviewer={"id": "", "name": ""}), chapter_number=3)),
)

check(
    "a reviewer that is not a person is rejected",
    any("reviewer" in p for p in review.validate(manifest(reviewer="automation"), chapter_number=3)),
)

# --- an AI recommendation can never become an approval ---------------------- #

AI = {"id": "openai-codex", "name": "OpenAI Codex", "kind": review.REVIEWER_AI_ASSISTED}

check(
    "an AI-assisted reviewer cannot approve",
    any("kind" in p for p in review.validate(manifest(reviewer=AI), chapter_number=3)),
)

check(
    "a reviewer with no stated kind cannot approve",
    any("kind" in p for p in review.validate(
        manifest(reviewer={"id": "someone", "name": "Someone"}), chapter_number=3)),
)

recommendation = {
    "schema_version": review.RECOMMENDATION_SCHEMA_VERSION,
    "chapter_number": 3,
    "recommendations": [
        {
            "claim_path": PATH,
            "claim_hash": review.claim_hash(CLAIM),
            "disposition": review.DISPOSITION_CANDIDATE,
            "recommended_verdict": review.VERDICT_FAITHFUL,
            "rationale": "Page 32 demonstrates the division; the claim states the rule it shows.",
            "recommended_by": AI,
        }
    ],
}


def with_rec(**overrides) -> dict:
    return {
        **recommendation,
        "recommendations": [dict(recommendation["recommendations"][0], **overrides)],
    }

check(
    "a well-formed recommendation validates as a recommendation",
    review.validate_recommendations(recommendation, chapter_number=3) == [],
    "; ".join(review.validate_recommendations(recommendation, chapter_number=3)),
)

# The load path reads the approval schema only. A recommendation file handed to
# it fails on the schema line before any claim is licensed.
check(
    "a recommendation file is not a valid approval file",
    review.validate(recommendation, chapter_number=3) != [],
)

with tempfile.TemporaryDirectory() as tmp:
    rec_path = Path(tmp) / "recs.json"
    rec_path.write_text(json.dumps(recommendation), encoding="utf-8")
    try:
        review.load(rec_path, chapter_number=3)
        check("loading a recommendation file as approvals raises", False)
    except review.ReviewManifestInvalid:
        check("loading a recommendation file as approvals raises", True)

smuggled = dict(recommendation["recommendations"][0], verdict=review.VERDICT_FAITHFUL)
check(
    "a recommendation carrying `verdict` is rejected",
    any("verdict" in p for p in review.validate_recommendations(
        {**recommendation, "recommendations": [smuggled]}, chapter_number=3)),
)

check(
    "a recommendation claiming to be human is rejected",
    any("kind" in p for p in review.validate_recommendations(
        {**recommendation, "recommendations": [dict(recommendation["recommendations"][0], recommended_by=REVIEWER)]},
        chapter_number=3)),
)

check(
    "a recommendation with no rationale is rejected",
    any("why" in p for p in review.validate_recommendations(
        {**recommendation, "recommendations": [dict(recommendation["recommendations"][0], rationale="")]},
        chapter_number=3)),
)

# --- omissions are recorded, never silent ----------------------------------- #

check(
    "an omitted claim must say why",
    any("why" in p for p in review.validate_recommendations(
        with_rec(disposition=review.DISPOSITION_OMITTED), chapter_number=3)),
)

check(
    "an omitted claim with a reason validates",
    review.validate_recommendations(
        with_rec(disposition=review.DISPOSITION_OMITTED,
                 omission_reason="States a method the source does not teach."),
        chapter_number=3) == [],
)

check(
    "a claim with no disposition is rejected",
    any("disposition" in p for p in review.validate_recommendations(
        with_rec(disposition=None), chapter_number=3)),
)

check(
    "a candidate carrying an omission reason is rejected",
    any("omission" in p for p in review.validate_recommendations(
        with_rec(omission_reason="dropped"), chapter_number=3)),
)

# --- the real chapter 3 worksheet ------------------------------------------- #

worksheet_path = Path(__file__).parent / "review" / "math5a.chapter03.recommendations.json"

if worksheet_path.exists():
    sheet = json.loads(worksheet_path.read_text(encoding="utf-8"))
    check(
        "the chapter 3 worksheet validates",
        review.validate_recommendations(sheet, chapter_number=3) == [],
        "; ".join(review.validate_recommendations(sheet, chapter_number=3)),
    )
    # Every claim the producer refused is accounted for -- either it goes to a
    # reviewer or it says why it does not. A refused claim missing from here is
    # content that vanished without anyone deciding it should.
    check(
        "the worksheet accounts for all 16 refused claims",
        len(sheet["recommendations"]) == 16,
        str(len(sheet["recommendations"])),
    )
    check(
        "no recommendation in the worksheet can approve anything",
        all("verdict" not in entry for entry in sheet["recommendations"]),
    )

missing_path = Path(tempfile.gettempdir()) / "definitely-not-a-review-manifest.json"
try:
    review.load(missing_path, chapter_number=3)
    check("a missing manifest raises", False)
except review.ReviewManifestMissing:
    check("a missing manifest raises", True)

print()
print(f"{len(fails)} failed" if fails else "all checks passed")
raise SystemExit(1 if fails else 0)
