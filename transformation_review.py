"""Human approvals for claims that carry the book's substance in other words.

A workbook demonstrates. It does not explain. Singapore Math 5A shows that
5 div 4 = 5/4 with a picture of shared pancakes and a long division; nowhere does
it write the sentence "dividing a whole by a number creates a fraction". So the
prose a learner needs cannot be lifted from the page, and `source_grounded` --
which promises the book says this, in these words -- is unavailable.

`source_transformed` is the honest origin for that prose: still the book's
content, no longer the book's words. But nothing in software can check that a
rewording preserved what the page demonstrates. Text matching proves the
opposite of what is needed here: these claims are transformations precisely
BECAUSE they do not match. Emitting `source_transformed` on the strength of a
model having produced it would assert the book supports a statement with nothing
behind the assertion -- a weaker guarantee than every other origin RAG emits.

So the fact automation cannot supply is supplied by a person, and recorded:

    a reviewer read this claim beside these chunks of the source, and says the
    rewriting preserved what the source demonstrates.

An approval pins the exact claim and the exact source it was judged against.
Change either -- reword the claim, reparse the book -- and the approval no
longer matches, because what the reviewer read no longer exists. It goes back to
`insufficient_source_evidence` and export stops. Approval is not a permanent
exemption for a claim path; it is a statement about one version of one claim
against one version of the source.

This is a contract EXTENSION, and its gate is stronger than the automated ones
it sits beside, not weaker: grounded claims need no human at all.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REVIEW_SCHEMA_VERSION = "lesson.transformation_review.v1"

# Advisory recommendations live under their OWN schema in their OWN file, and
# `load()` reads only the approval schema. That separation is the enforcement:
# a recommendation cannot license anything, because the code path that licenses
# claims never opens the file recommendations are in.
#
# The distinction is the whole point of the gate. A model reading a claim beside
# its source and judging it faithful is useful work -- it narrows what a person
# must look at -- but recording it as an approval would swap "a model wrote
# this" for "a model approved it" while presenting the result as reviewed.
RECOMMENDATION_SCHEMA_VERSION = "lesson.transformation_recommendation.v1"

# Who is answering. An approval requires a person; a recommendation requires an
# honest statement that it is not one.
REVIEWER_HUMAN = "human"
REVIEWER_AI_ASSISTED = "ai_assisted"

VERDICT_FAITHFUL = "faithful"
VERDICT_UNFAITHFUL = "unfaithful"
VERDICTS = (VERDICT_FAITHFUL, VERDICT_UNFAITHFUL)

# What a transformation DID to the source. Named, because "transformed" alone
# does not tell a later reader whether the meaning was at risk: restating a
# worked example in prose is a different act from condensing a whole chapter.
TRANSFORMATION_TYPES = (
    # The page works an example; the claim states the rule it demonstrates.
    "demonstration_to_statement",
    # The page's own words, simplified for a younger reader.
    "simplified_restatement",
    # Several pages' content pulled into one statement.
    "condensed_summary",
    # A term the book uses throughout, defined from how it is used.
    "usage_to_definition",
)

REQUIRED_APPROVAL_FIELDS = (
    "claim_path",
    "claim_hash",
    "source_content_revision",
    "source_chunk_ids",
    "transformation_type",
    "reviewer",
    "verdict",
)


class ReviewManifestMissing(Exception):
    """No approvals file where one was required."""


class ReviewManifestInvalid(Exception):
    """An approvals file that cannot be trusted to mean what it says."""


def claim_hash(text: str) -> str:
    """Identity of the exact words a reviewer read.

    Deliberately hashes the text verbatim -- no normalising, no case folding.
    A reviewer approves wording, and rewording is the thing that can silently
    change meaning while a normalised hash stays equal.
    """
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def source_revision(chunks: list[dict[str, Any]]) -> str:
    """Identity of the source material as it stood when reviewed.

    Covers ids AND text: a reparse that keeps `math5a:p32` but changes what is
    on page 32 has invalidated every judgement made against it, and an id-only
    revision would not notice.
    """
    payload = [
        {"node_id": str(chunk.get("node_id") or ""), "text": chunk.get("text") or ""}
        for chunk in chunks
    ]
    payload.sort(key=lambda entry: entry["node_id"])
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


class ApprovalSet:
    """The approvals for one chapter, answering one question per claim."""

    def __init__(self, approvals: list[dict[str, Any]], *, source_path: str) -> None:
        self._by_path = {str(approval["claim_path"]): approval for approval in approvals}
        self._source_path = source_path

    def __len__(self) -> int:
        return len(self._by_path)

    def paths(self) -> set[str]:
        return set(self._by_path)

    def approval_for(
        self,
        claim_path: str,
        text: str,
        revision: str,
        available_chunk_ids: set[str],
    ) -> tuple[dict[str, Any] | None, str]:
        """The approval that licenses this claim, or why nothing does.

        Returns the reason as well as the verdict because "not approved" is not
        actionable, and "the claim was reworded since Roy approved it" tells
        whoever fixes it what happened and what to do.
        """
        approval = self._by_path.get(claim_path)

        if approval is None:
            return None, "no reviewer has looked at this claim"

        if approval["verdict"] == VERDICT_UNFAITHFUL:
            note = str(approval.get("note") or "").strip()

            return None, f"a reviewer rejected this transformation{': ' + note if note else ''}"

        if approval["claim_hash"] != claim_hash(text):
            return None, "the claim has been reworded since it was approved"

        if approval["source_content_revision"] != revision:
            return None, "the source has changed since this was approved"

        # An approval naming chunks the chapter does not have is not a stale
        # approval, it is a wrong one -- the reviewer judged the claim against
        # material that is not there.
        missing = [
            chunk_id
            for chunk_id in approval["source_chunk_ids"]
            if chunk_id not in available_chunk_ids
        ]

        if missing:
            return None, f"approved against chunks this chapter does not contain: {', '.join(missing)}"

        return approval, ""


def load(path: str | Path, *, chapter_number: int) -> ApprovalSet:
    """Read and fully validate an approvals file before anything consults it."""
    manifest_path = Path(path)

    if not manifest_path.exists():
        raise ReviewManifestMissing(
            f"{manifest_path} does not exist; transformed claims require reviewed approvals"
        )

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewManifestInvalid(f"{manifest_path} is not valid JSON: {exc}") from exc

    problems = validate(raw, chapter_number=chapter_number)

    if problems:
        raise ReviewManifestInvalid(f"{manifest_path}: " + "; ".join(problems))

    return ApprovalSet(raw["approvals"], source_path=str(manifest_path))


def validate(manifest: Any, *, chapter_number: int) -> list[str]:
    """Everything wrong with an approvals file, not just the first thing."""
    problems: list[str] = []

    if not isinstance(manifest, dict):
        return ["approvals manifest must be an object"]

    if manifest.get("schema_version") != REVIEW_SCHEMA_VERSION:
        problems.append(
            f"schema_version must be {REVIEW_SCHEMA_VERSION!r}, "
            f"got {manifest.get('schema_version')!r}"
        )

    if manifest.get("chapter_number") != chapter_number:
        problems.append(
            f"approvals are for chapter {manifest.get('chapter_number')!r}, "
            f"not chapter {chapter_number}"
        )

    approvals = manifest.get("approvals")

    if not isinstance(approvals, list):
        return problems + ["approvals must be a list"]

    seen: set[str] = set()

    for index, approval in enumerate(approvals):
        where = f"approvals[{index}]"

        if not isinstance(approval, dict):
            problems.append(f"{where} must be an object")
            continue

        for field in REQUIRED_APPROVAL_FIELDS:
            value = approval.get(field)

            if value is None or (isinstance(value, str) and not value.strip()):
                problems.append(f"{where} is missing {field}")

        path = str(approval.get("claim_path") or "")

        if path and path in seen:
            # Two verdicts for one claim is not a duplicate record, it is an
            # unresolved disagreement, and silently taking the first would
            # discard a rejection.
            problems.append(f"{where} approves {path} a second time")

        seen.add(path)

        verdict = approval.get("verdict")

        if verdict is not None and verdict not in VERDICTS:
            problems.append(f"{where} has verdict {verdict!r}, expected one of {', '.join(VERDICTS)}")

        transformation = approval.get("transformation_type")

        if transformation is not None and transformation not in TRANSFORMATION_TYPES:
            problems.append(f"{where} has unknown transformation_type {transformation!r}")

        chunk_ids = approval.get("source_chunk_ids")

        if not isinstance(chunk_ids, list) or not chunk_ids:
            problems.append(f"{where} must name the source chunks it was judged against")
        elif any(not str(chunk_id).strip() for chunk_id in chunk_ids):
            problems.append(f"{where} has a blank source chunk id")

        reviewer = approval.get("reviewer")

        if isinstance(reviewer, dict):
            for field in ("id", "name"):
                if not str(reviewer.get(field) or "").strip():
                    problems.append(f"{where} reviewer is missing {field}")

            kind = reviewer.get("kind")

            if kind != REVIEWER_HUMAN:
                # An approval is a person's statement. Anything else answering
                # here -- a model, a script, an unstated kind -- would make the
                # record claim a human check that did not happen, which is
                # worse than having no record at all.
                problems.append(
                    f"{where} reviewer.kind is {kind!r}; an authoritative approval "
                    f"requires {REVIEWER_HUMAN!r}"
                )
        elif reviewer is not None:
            problems.append(f"{where} reviewer must be an object identifying a person")

    return problems


def validate_recommendations(manifest: Any, *, chapter_number: int) -> list[str]:
    """Everything wrong with an ADVISORY recommendation file.

    Deliberately a separate function from `validate()`, over a separate schema,
    so that no caller can pass one where the other is expected and have it come
    back clean. A recommendation carries `recommended_verdict`, never `verdict`:
    the field an approval is read for does not exist here, so a recommendation
    handed to the approval path fails on missing fields rather than licensing
    anything.
    """
    problems: list[str] = []

    if not isinstance(manifest, dict):
        return ["recommendations manifest must be an object"]

    if manifest.get("schema_version") != RECOMMENDATION_SCHEMA_VERSION:
        problems.append(
            f"schema_version must be {RECOMMENDATION_SCHEMA_VERSION!r}, "
            f"got {manifest.get('schema_version')!r}"
        )

    if manifest.get("chapter_number") != chapter_number:
        problems.append(f"recommendations are for chapter {manifest.get('chapter_number')!r}")

    entries = manifest.get("recommendations")

    if not isinstance(entries, list):
        return problems + ["recommendations must be a list"]

    for index, entry in enumerate(entries):
        where = f"recommendations[{index}]"

        if not isinstance(entry, dict):
            problems.append(f"{where} must be an object")
            continue

        if "verdict" in entry:
            # The one field name that would let a recommendation be mistaken
            # for an approval by anything reading loosely.
            problems.append(f"{where} must not carry `verdict`; recommendations advise, they do not decide")

        if entry.get("recommended_verdict") not in VERDICTS:
            problems.append(f"{where} needs a recommended_verdict of {' or '.join(VERDICTS)}")

        if not str(entry.get("rationale") or "").strip():
            # A recommendation exists to save a person reading time. One with no
            # reasoning saves them nothing and invites agreement by default.
            problems.append(f"{where} must say why")

        author = entry.get("recommended_by")

        if not isinstance(author, dict):
            problems.append(f"{where} must name what produced the recommendation")
        else:
            if author.get("kind") != REVIEWER_AI_ASSISTED:
                problems.append(
                    f"{where} recommended_by.kind must be {REVIEWER_AI_ASSISTED!r} -- "
                    f"a recommendation states plainly that no person made it"
                )

            for field in ("id", "name"):
                if not str(author.get(field) or "").strip():
                    problems.append(f"{where} recommended_by is missing {field}")

    return problems
