"""Draft lessons for PTE task types the source book predates.

The course book was written for the older test format, so it contains nothing on
Summarize Group Discussion or Respond to a Situation — both made permanent from
7 August 2025. The grounded pipeline can only teach what is in the book, so these
two lessons are built from Pearson's own published guidance instead.

Their provenance is therefore DIFFERENT from every other lesson and is marked as
such: "source_kind": "pearson_official" (vs the book-grounded lessons), plus a
provenance_note. The UI shows a banner so a learner is never misled about where
the teaching came from.

Facts below are taken from Pearson's "Prepare for the two new question types"
(V4, July 2025) and pearsonpte.com's Summarize Group Discussion article.

Usage:
  python draft_official_task_lessons.py            # generate + validate + write
  python draft_official_task_lessons.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

import enrich_lessons as el

OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"

SGD_FACTS = """PTE LESSON (official Pearson guidance) — enrich this into the teaching-first version.
source_label: pte:ch18
chapter_number: 18
lesson_title: Lesson 18: Summarize Group Discussion
estimated_study_time: About 2 hours, including timed practice with recorded discussions.

TASK FORMAT (from Pearson official guidance):
- You listen to a group discussion between THREE people. The topic is academic.
- The audio lasts about 2.5 to 3 minutes and plays ONCE only; it cannot be replayed.
- You see instructions and an audio box; the audio starts automatically after a few seconds.
- You should take notes while listening.
- After the audio ends you have 10 SECONDS to prepare and UP TO 2 MINUTES to speak your summary.
- Communicative skill: Speaking. Scored on Content, Oral Fluency and Pronunciation.
- Content also receives a human expert review before the score is finalised.
- Question type added to PTE Academic permanently from 7 August 2025 (Speaking went from 7 to 9 questions).

WHAT THE RESPONSE MUST CONTAIN (official):
- An accurate summary of the WHOLE discussion, not a list of who spoke in order.
- The topic, the main ideas, and supporting detail for each main idea.
- What each of the three speakers says, thinks and feels, attributed to the right speaker.
- Where speakers agree or disagree, or hold the same or different opinions.
- Connections between ideas using linking words, in academic language.

OFFICIAL DO:
- Take effective notes: write the Topic (T), Main Ideas (MI), and S1, S2, S3 with what each says.
- Start with a short summary of the listening, then introduce main ideas with supporting details.
- Mention which speaker said which point.
- Use linking words to connect topics.
- State where speakers agree or disagree.

OFFICIAL DON'T:
- Don't just list in order who said what — it is a summary, not a transcript.
- Don't add information that is incorrect or misrepresent what a speaker said.
- Don't confuse the speakers (attributing speaker 1's point to speaker 2 costs content).
- Don't try to mention every single point; summarize the main points.
- Don't speak for too little time — you must cover the entire audio.
- Don't jump between ideas without flow or connection.
- Don't introduce topics mechanically ("topic 1 is, topic 2 is...").

OFFICIAL NOTE STRUCTURE (from Pearson's worked example):
T: the topic. MI: each main idea. Under each main idea, S1 / S2 / S3 with their supporting details.
"""

RTS_FACTS = """PTE LESSON (official Pearson guidance) — enrich this into the teaching-first version.
source_label: pte:ch19
chapter_number: 19
lesson_title: Lesson 19: Respond to a Situation
estimated_study_time: About 1.5 hours, including timed spoken practice.

TASK FORMAT (from Pearson official guidance):
- You READ and LISTEN to a prompt describing an everyday or academic situation.
- You may take notes as you listen, but time is limited.
- After the audio ends you have 10 SECONDS to prepare and 40 SECONDS to respond.
- You speak your response as if talking directly to the person or people in the situation.
- Communicative skill: Speaking. Scored on Content, Oral Fluency and Pronunciation.
- Content also receives a human expert review before the score is finalised.
- Question type added to PTE Academic permanently from 7 August 2025.

OFFICIAL SAMPLE PROMPT:
"You are doing a group project for a class. The other members of your group have asked you to
prepare the slides for the presentation. You are willing to do the slides but need them to give you
all the information that you have to include before the weekend. What would you say to them?"

OFFICIAL EXCELLENT SAMPLE ANSWER:
"Hi everyone! I'm happy to create the slides for this presentation we're giving. To be successful
though, I'll need you to each send me all the information and content you've gathered for our group
project before this coming weekend so I'll have enough time to complete the slides. Please send the
information to my email by end of day this Friday - does that work for everyone?"
Why it scores well (official explanation): it covers the main information — (1) willing to design the
slides, (2) needs more information, (3) needs it before the weekend — so the primary communication
goal is fully met; it is polite, in the first person, and has the correct tone (persuasive and strong
enough) to make the request.

OFFICIAL DO:
- Speak like you are talking to the person — use the first person ("I..."), not the third person.
- Start with an opening suited to the listener (e.g. "Hi...", "Excuse me...").
- Cover the main points of the prompt without missing out or changing any important information.
- Understand the formality and tone: are you being assertive or persuasive, and with whom?
- Use contractions ("I'll...", "they'll...") because it is spoken language and aids fluency.
- Use polite language appropriate to the relationship.

OFFICIAL DON'T:
- Don't forget to mention all the key points from the prompt.
- Don't change the information (saying "Saturday" when the prompt says "by the end of this week" is a content error).
- Don't just copy the words from the prompt.
- Don't use limited expressions and repetition ("I'd like..., I'd like..., I'd like...").
- Don't pre-memorize an answer — it will not cover the situation's points and scores very low.
- Don't SUMMARIZE the situation; this is not a summarize task, it is a response.
- Don't be over-polite when the request is strong ("would you possibly..." vs "I need...").
- Don't give your opinion on whether the task is reasonable, or suggest how to change the situation.
"""

TASKS = [
    (18, "summarize_group_discussion", SGD_FACTS),
    (19, "respond_to_a_situation", RTS_FACTS),
]

PROVENANCE = (
    "This lesson is NOT from the course book, which predates this question type. It is built from "
    "Pearson's official published guidance for the two question types added to PTE Academic on "
    "7 August 2025 ('Prepare for the two new question types', V4 July 2025, and pearsonpte.com). "
    "Format facts, timings, do/don't advice and the sample answer come from that guidance; the "
    "method, techniques, drills and practice plan are teaching support built on top of it."
)


def chat(messages: list[dict[str, str]], *, model: str, timeout: float = 300.0) -> str:
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not set (add it to .env).")
    resp = httpx.post(
        OLLAMA_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.4}},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


DEPTH = (
    "\nDEPTH REQUIREMENT: this lesson must be as substantial as a full course lesson. "
    "Provide at least 7 techniques, at least 3 worked_examples (each with a complete, "
    "realistic model_answer for a 2-minute or 40-second spoken response as appropriate), "
    "at least 8 common_mistakes, at least 5 useful_language categories, at least 6 drills, "
    "and at least 12 mastery_checklist items."
)


def draft(chapter: int, task_type: str, facts: str, *, model: str, attempts: int = 3) -> dict[str, Any]:
    system = (
        "You are the Lesson Enrichment engine for a PTE Academic learning app. You turn the "
        "supplied official task guidance into a rich, TEACHING-FIRST lesson. Treat every supplied "
        "fact as authoritative and never contradict it. Do not invent timings or scoring traits "
        "beyond those given. Output only the JSON object."
    )
    user = facts + "\n" + el.SCHEMA_CONTRACT + DEPTH
    last: Exception | None = None
    for _ in range(attempts):
        try:
            raw = chat([{"role": "system", "content": system}, {"role": "user", "content": user}], model=model)
            doc = el.normalize_document(el.strip_citation_artifacts(el.extract_json_object(raw)))
            # Provenance is different from every other lesson — mark it explicitly.
            doc["task_type"] = task_type
            doc["source_kind"] = "pearson_official"
            doc.setdefault("metadata", {})["provenance_note"] = PROVENANCE
            el.validate_enrichment(doc, chapter)
            if len(doc["techniques"]) >= 6 and len(doc["worked_examples"]) >= 2:
                return doc
            last = ValueError(
                f"too thin (techniques={len(doc['techniques'])}, worked={len(doc['worked_examples'])})"
            )
        except Exception as exc:  # transient bad JSON or contract miss — retry
            last = exc
    raise RuntimeError(f"could not draft a substantial lesson after {attempts} attempts: {last}")


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    p = argparse.ArgumentParser(description="Draft lessons for task types the book predates.")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    for chapter, task_type, facts in TASKS:
        print(f"\n=== Lesson {chapter}: {task_type} ===")
        try:
            doc = draft(chapter, task_type, facts, model=args.model)
        except Exception as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            continue
        print(
            f"  OK  techniques={len(doc['techniques'])} worked={len(doc['worked_examples'])} "
            f"mistakes={len(doc['common_mistakes'])} checklist={len(doc['mastery_checklist'])}"
        )
        if args.dry_run:
            continue
        path = el.write_enrichment_file(doc, chapter)
        print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
