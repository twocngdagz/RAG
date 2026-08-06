"""Generate a chapter's class lessons, one concept at a time, through ChatGPT.

The sibling of `enrich_lessons.py`, not its replacement. Enrichment turns a
chapter's grounded base into the teaching detail behind it. This turns that
detail into the CLASS LESSON for one concept — the goal, the method, the worked
examples — under `class_lesson_contract.py` and the document it hands over.

Nothing here writes teaching. The prompt is the contract plus this run's context;
the lesson comes back from the generator; this module decides what to ask, in
what order, and what to keep.

PER CONCEPT, NEVER PER CHAPTER. Chapter 3 is five runs, one for each of its
concepts. A chapter in one prompt is too heavy — enrichment alone takes eighteen
to twenty minutes for a chapter, and a chapter's worth of class-lesson writing is
larger again — and it also loses the thing that makes re-running cheap: a concept
that came back thin is re-run on its own.

EVERY RUN CARRIES THE CONCEPT'S CURRENT LESSON. Run one finds nothing and
generates. Run two sends run one's lesson back with "this exists, expand it".
Run three sends both. The generator always sees the current state, so a pass adds
rather than repeats, and `class_lesson_contract.merge` keeps what is stored,
whatever comes back — nothing is ever deleted.

RUNS ARE UNLIMITED, AND A RE-RUN IS DELIBERATE. By default a concept that already
has a class lesson is skipped and costs no request: that is what makes an
interrupted chapter resume where it stopped, and what stops a second pass over a
chapter from duplicating anything. `--expand` is how you ask for another pass,
and `--concept` is how you ask for one on a single concept.

WHICH CONCEPTS. The chapter's approved export manifest, which is where a concept's
key and statement are decided. An unapproved mapping is a machine's proposal, and
its keys can still move; `--manifest` will read one anyway — a class lesson filed
under a key that later changes is orphaned rather than wrong — but the run says
so every time.

WHICH CHATGPT PROJECT. Any of them. Enrichment leans on a project whose standing
instructions already know what to do with a pasted lesson; this carries the whole
contract in every message instead, so the project supplies nothing but a fresh
chat per request — which is what a URL ending in `/project` gives. Log in once
with `python chatgpt_browser_driver.py login`.

    python run_class_lessons.py concepts --book math5a --chapter 3
    python run_class_lessons.py prompt   --book math5a --chapter 3 --concept math5a:ch03:add-unlike-fractions
    python run_class_lessons.py run      --book math5a --chapter 3 --project-url "https://chatgpt.com/g/g-p-XXXX/project"
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PWError

import class_lesson_contract as contract
import domain_packs
import lesson_export_manifest as manifest_module
import teaching_document
from chatgpt_browser_driver import DEFAULT_PROFILE, ChatGPTDriver

# Where a chapter's class lessons live, and what reading one promises. Defined
# once, next door, because the exporter reads the same file: two copies of the
# store's shape drift, and the drift shows up as a package missing teaching.
from class_lesson_store import (  # noqa: F401  (re-exported: this runner's own vocabulary)
    STORE_FILE,
    STORE_SCHEMA_VERSION,
    ClassLessonsRefused,
    empty_store,
    lesson_of,
    record,
    store_path,
)
from class_lesson_store import load as load_store
from class_lesson_store import save as save_store

# Reading a JSON object out of a ChatGPT reply is the enrichment runner's job
# already, DOM quirks and citation artifacts included. A second copy of it would
# drift the first time ChatGPT's markup moved.
from enrich_lessons import extract_json_object, scrape_reply_json, strip_citation_artifacts


class RunRefused(Exception):
    """The run cannot start, and why. Raised before any request is sent."""


# --------------------------------------------------------------------------- #
# 1. What a run reads: the concepts, and the chapter's enriched material.
# --------------------------------------------------------------------------- #

def concepts_of(slug: str, chapter: int, *, manifest_file: str | Path | None = None) -> tuple[list[dict], Path, bool]:
    """The chapter's concepts, where they were read from, and whether it is approved."""
    path = Path(manifest_file) if manifest_file else manifest_module.manifest_path(slug, chapter)

    if not path.exists():
        raise RunRefused(
            f"no export manifest at {path}. A concept's key and statement are decided in the "
            f"mapping, not here — draft one with draft_export_manifest.py, approve it, or name "
            f"an unapproved one with --manifest and accept that its keys can still move."
        )

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RunRefused(f"{path} is not readable JSON: {error}") from error

    approved = manifest.get(manifest_module.APPROVAL_FIELD) is True

    if not approved and not manifest_file:
        # The same refusal the exporter makes, for the same reason: nobody has
        # said yes to this mapping yet.
        manifest_module.assert_approved(manifest, str(path))

    concepts = manifest.get("concepts") or []

    if not concepts:
        raise RunRefused(
            f"{path} declares no concepts"
            + (
                f", because it is a review of {', '.join(manifest['reviews'])}. A review lesson "
                f"teaches nothing and has no concepts of its own; there is no class lesson to write."
                if manifest.get("reviews")
                else ". A class lesson is written for a concept, and this chapter has none."
            )
        )

    for index, concept in enumerate(concepts):
        for field in ("stable_key", "statement"):
            if not isinstance(concept, dict) or not str(concept.get(field) or "").strip():
                raise RunRefused(f"{path}: concepts[{index}] has no {field}")

    return concepts, path, approved


def load_material(pack: domain_packs.DomainPack, chapter: int, *, enrichment_file: str | Path | None = None) -> dict:
    """The chapter's enrichment, which is what a class lesson is written from."""
    path = Path(enrichment_file) if enrichment_file else Path(pack.enrich_path(chapter))

    if not path.exists():
        raise RunRefused(
            f"no enrichment for chapter {chapter} at {path}. A class lesson is a transform of "
            f"the chapter's enriched material; enrich it first with enrich_lessons.py."
        )

    try:
        material = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RunRefused(f"{path} is not readable JSON: {error}") from error

    schema = str(material.get("schema_version") or "").strip()

    if schema != teaching_document.COACH_SCHEMA_VERSION:
        raise RunRefused(
            f"{path} is {schema or 'unversioned'!r}, not "
            f"{teaching_document.COACH_SCHEMA_VERSION!r}; this runner knows where teaching lives "
            f"in that shape and not in another"
        )

    expected = f"{pack.slug}:ch{chapter:02d}"

    if str(material.get("source_label") or "").strip() != expected:
        raise RunRefused(
            f"{path} identifies as {material.get('source_label')!r} but this run is for "
            f"{expected!r}; class lessons would be written from another chapter's material"
        )

    return material


# --------------------------------------------------------------------------- #
# 2. The run: one concept at a time, resuming where it stopped.
# --------------------------------------------------------------------------- #

def to_run(concepts: list[dict], store: dict[str, Any], *, expand: bool, only: list[str] | None) -> list[dict]:
    """Which concepts this run will actually ask about.

    Default: the ones with no class lesson yet. That single rule is both halves
    of the resume promise — a chapter that failed at the fifth concept asks for
    the fifth, and a chapter run twice asks for nothing.
    """
    chosen = concepts

    if only:
        wanted = {key.strip() for key in only}
        known = {concept["stable_key"] for concept in concepts}
        unknown = sorted(wanted - known)

        if unknown:
            raise RunRefused(
                f"this lesson has no concept {', '.join(unknown)}. Its concepts are: "
                + ", ".join(sorted(known))
            )

        chosen = [concept for concept in concepts if concept["stable_key"] in wanted]

    if expand:
        return chosen

    return [concept for concept in chosen if lesson_of(store, concept["stable_key"]) is None]


def prompt_for(
    concept: dict,
    *,
    concepts: list[dict],
    pack: domain_packs.DomainPack,
    material: dict[str, Any],
    store: dict[str, Any],
) -> str:
    """The whole message for one concept: the contract, the context, the current lesson."""
    return contract.build_prompt(
        pack=pack,
        concept_key=concept["stable_key"],
        concept_statement=concept["statement"],
        other_concepts=[
            {"stable_key": other["stable_key"], "statement": other["statement"]}
            for other in concepts
            if other["stable_key"] != concept["stable_key"]
        ],
        material=material,
        current=lesson_of(store, concept["stable_key"]),
    )


def _pause_seconds(args) -> int:
    """How long to wait before the next request.

    Randomised inside [--cooldown, --cooldown-max] so the cadence is not a fixed
    metronome — the enrichment runner's rule, for the same account.
    """
    low = max(0, args.cooldown)

    if low == 0:
        return 0

    return random.randint(low, max(low, getattr(args, "cooldown_max", low)))


def cmd_run(args) -> int:
    pack = domain_packs.get(args.book)
    concepts, manifest_path, approved = concepts_of(args.book, args.chapter, manifest_file=args.manifest)
    material = load_material(pack, args.chapter, enrichment_file=args.enrichment)
    path = Path(args.out) if args.out else store_path(args.book, args.chapter)
    store = load_store(path, args.book, args.chapter)

    print(f"book: {pack.slug} — {pack.title}, chapter {args.chapter}")
    print(f"concepts: {len(concepts)} from {manifest_path}")

    if not approved:
        print(
            f"  ! {manifest_path} is NOT approved. Its concept keys are a proposal and can still "
            f"move; a class lesson filed under one that changes is orphaned.",
            file=sys.stderr,
        )

    targets = to_run(concepts, store, expand=args.expand, only=args.concept)
    skipped = [
        concept["stable_key"]
        for concept in concepts
        if concept not in targets and lesson_of(store, concept["stable_key"]) is not None
    ]

    if not targets:
        print("nothing to do: every concept asked for already has a class lesson.")
        print("  re-run with --expand to add to them.")
        return 0

    written: list[str] = []
    failed: list[str] = []
    sent_before = False

    with ChatGPTDriver(args.profile_dir, headless=args.headless) as driver:
        for concept in targets:
            key = concept["stable_key"]
            current = lesson_of(store, key)
            print(f"\n=== {key} ===")
            print(f"  {'expanding' if current else 'first run'}: {concept['statement'][:90]}")

            # Pace before sending rather than after: a run that stops here has
            # not just idled for ten minutes doing nothing.
            if sent_before and args.cooldown > 0:
                delay = _pause_seconds(args)
                print(f"  waiting {delay // 60}m {delay % 60}s before this request…")
                time.sleep(delay)

            prompt = prompt_for(concept, concepts=concepts, pack=pack, material=material, store=store)
            sent_before = True
            # The accepted lesson and the report of what this run added, kept
            # together so neither can be read from an earlier concept's attempt.
            outcome: tuple[dict[str, Any], dict] | None = None

            for attempt in range(1, args.max_attempts + 1):
                raw = ""
                label = f"attempt {attempt}/{args.max_attempts}"
                print(f"  {label}: prompt {len(prompt):,} chars -> project (fresh chat)")

                try:
                    reply = driver.send_and_wait(args.project_url, prompt, timeout_s=args.timeout)
                    raw = scrape_reply_json(driver.page) or reply
                    candidate = contract.validate(
                        strip_citation_artifacts(extract_json_object(raw)),
                        concept_key=key,
                        concept_statement=concept["statement"],
                    )
                    candidate, report = contract.merge(current, candidate)
                    contract.assert_expanded(report)
                    contract.assert_nothing_lost(current, candidate)
                    outcome = (candidate, report)
                    break
                except (contract.ClassLessonRefused, contract.ClassLessonAddedNothing,
                        contract.ClassLessonLostContent, ValueError, json.JSONDecodeError,
                        RuntimeError, TimeoutError, PWError) as error:
                    # Beside the lessons it was refused for, so the reply and the
                    # file it failed to join are read in the same place.
                    debug = path.with_name(f"_class_lesson.{_slugged(key)}.reply.txt")
                    debug.parent.mkdir(parents=True, exist_ok=True)
                    debug.write_text(raw or "", encoding="utf-8")
                    print(f"  ! {label} rejected: {error}\n    raw reply saved to {debug}",
                          file=sys.stderr)

                    if attempt >= args.max_attempts:
                        failed.append(key)
                        break

                    notice = driver.restriction_notice()

                    if notice:
                        wait = args.limit_backoff
                        print(f"  !! usage restriction: {notice!r}\n"
                              f"     backing off {wait // 60}m before retrying {key}…",
                              file=sys.stderr)
                    else:
                        wait = _pause_seconds(args)
                        print(f"     retrying {key} in {wait // 60}m {wait % 60}s…")

                    if wait > 0:
                        time.sleep(wait)

            if outcome is not None:
                merged, report = outcome
                # Persisted per concept, immediately. An interruption after this
                # point costs the concepts not yet run and none of the ones done.
                record(store, key, merged, report)
                save_store(path, store)
                print(f"  OK  {contract.summary(report)} -> {path}")

                for description in report["added"]:
                    print(f"      + {description}")

                written.append(key)
            elif args.stop_on_error:
                print("  stopping: --stop-on-error", file=sys.stderr)
                break

    print(f"\n{'=' * 48}")
    print(f"chapter {args.chapter}: {len(written)}/{len(targets)} concepts written this run.")

    if skipped:
        print(f"  already had a class lesson (no request sent): {len(skipped)}")

    if failed:
        print(f"  STILL FAILING: {failed} — re-run the same command; it asks only for these.")

    return 0 if not failed else 1


def cmd_concepts(args) -> int:
    """What this chapter's concepts are and which of them have a lesson. No browser."""
    concepts, manifest_path, approved = concepts_of(args.book, args.chapter, manifest_file=args.manifest)
    path = Path(args.out) if args.out else store_path(args.book, args.chapter)
    store = load_store(path, args.book, args.chapter)

    print(f"{manifest_path}{'' if approved else '  (NOT approved — keys are provisional)'}")
    print(f"class lessons: {path}{'' if path.exists() else '  (nothing generated yet)'}")

    for concept in concepts:
        key = concept["stable_key"]
        lesson = lesson_of(store, key)
        runs = ((store.get("concepts") or {}).get(key) or {}).get("runs") or []

        if lesson is None:
            print(f"  [ ] {key} — no class lesson yet")
            continue

        print(
            f"  [x] {key} — {len(runs)} run(s), {len(lesson.get('techniques') or [])} technique(s), "
            f"{len(lesson.get('worked_examples') or [])} worked example(s)"
        )

        for index, run in enumerate(runs, start=1):
            print(f"        run {index}: {run}")

    return 0


def cmd_prompt(args) -> int:
    """Print exactly what one concept's request would send. No browser."""
    pack = domain_packs.get(args.book)
    concepts, _, _ = concepts_of(args.book, args.chapter, manifest_file=args.manifest)
    material = load_material(pack, args.chapter, enrichment_file=args.enrichment)
    path = Path(args.out) if args.out else store_path(args.book, args.chapter)
    store = load_store(path, args.book, args.chapter)
    wanted = [concept for concept in concepts if concept["stable_key"] in set(args.concept)]

    if not wanted:
        raise RunRefused(
            f"no concept named {', '.join(args.concept)}. This lesson's concepts are: "
            + ", ".join(concept["stable_key"] for concept in concepts)
        )

    for concept in wanted:
        prompt = prompt_for(concept, concepts=concepts, pack=pack, material=material, store=store)
        print(f"\n===== {concept['stable_key']} ({len(prompt):,} chars) =====\n")
        print(prompt)

    return 0


def _slugged(concept_key: str) -> str:
    return concept_key.replace(":", ".").replace("/", ".")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate class lessons, one concept at a time.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(target) -> None:
        # Required rather than defaulted. The sibling runner defaults to pte and
        # this stage exists for math5a; a default either way would be the wrong
        # book for half the commands typed, and it decides where every file is
        # read from and written to.
        target.add_argument("--book", required=True, choices=sorted(domain_packs.REGISTRY),
                            help="which domain pack / book, e.g. math5a")
        target.add_argument("--chapter", type=int, required=True)
        target.add_argument("--manifest", help="read concepts from this mapping instead of the "
                                               "chapter's approved manifest (an unapproved one is "
                                               "allowed here, and said so on every run)")
        target.add_argument("--out", help="where the chapter's class lessons are stored "
                                          "(default output/<slug>.chapterNN.class_lessons.json)")

    listing = sub.add_parser("concepts", help="list the chapter's concepts and what each has.")
    common(listing)
    listing.set_defaults(func=cmd_concepts)

    showing = sub.add_parser("prompt", help="print the request for one concept (no browser).")
    common(showing)
    showing.add_argument("--concept", action="append", required=True, help="concept stable key")
    showing.add_argument("--enrichment", help="the chapter's enrichment (default: the pack's path)")
    showing.set_defaults(func=cmd_prompt)

    running = sub.add_parser("run", help="drive ChatGPT per concept, validate, merge, store.")
    common(running)
    running.add_argument("--project-url", required=True, help="ChatGPT project URL (ends /project).")
    running.add_argument("--enrichment", help="the chapter's enrichment (default: the pack's path)")
    running.add_argument("--concept", action="append",
                         help="run only this concept (repeatable). Default: every concept without "
                              "a class lesson.")
    running.add_argument("--expand", action="store_true",
                         help="run concepts that already have a class lesson, to add to them. "
                              "Default is to skip them, which is what makes a re-run resume.")
    running.add_argument("--profile-dir", default=DEFAULT_PROFILE)
    running.add_argument("--timeout", type=int, default=900,
                         help="seconds of SILENCE that end a request (default 900).")
    running.add_argument("--cooldown", type=int, default=300,
                         help="minimum seconds between requests (0 disables).")
    running.add_argument("--cooldown-max", type=int, default=600,
                         help="maximum seconds between requests; the pause is random in the window.")
    running.add_argument("--max-attempts", type=int, default=3,
                         help="times to re-ask for one concept before giving up on it (default 3).")
    running.add_argument("--limit-backoff", type=int, default=1800,
                         help="seconds to wait after a usage-limit notice (default 1800).")
    running.add_argument("--headless", action="store_true")
    running.add_argument("--stop-on-error", action="store_true",
                         help="stop the chapter at the first concept that fails.")
    running.set_defaults(func=cmd_run)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        return args.func(args)
    except (RunRefused, ClassLessonsRefused, manifest_module.ManifestUnapproved) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
