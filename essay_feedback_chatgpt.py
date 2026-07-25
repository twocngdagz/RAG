"""Score a PTE essay through the ChatGPT web app instead of a hosted open model.

The same job as essay_feedback.py, a different engine behind it. Enrichment
already proved this route: a dedicated logged-in Chrome profile driven by
Playwright, talking to a ChatGPT Project, produced markedly better work than the
free hosted models. This applies that route to marking.

Deliberately thin. The rubric, the band descriptors, the JSON contract, the
word-count and Form rules and the reconcile step all come from essay_feedback,
imported rather than copied. Two markers with two rubrics would drift apart
within a week and nobody would notice which one a stored mark came from. Here
there is one rubric and two ways of asking it, and both return the identical
shape, so anything downstream — the score card, the history, the split into what
you said and how you wrote it — works unchanged.

What is different, and why:
  - One browser, one conversation, one essay at a time. There is no concurrency
    to be had, so this suits batch marking far better than a student waiting.
  - A reply can take a minute or more.
  - It can fail in ways an API cannot: logged out, plan limit reached, the page
    redesigned. Each is raised as a plain error rather than a silent bad mark.
  - Every reply is asked for in a fresh conversation. A Project chat accumulates
    context, and an essay scored after five other essays is not scored on its own
    merits.

Note this drives a web session rather than an API, which is not what ChatGPT's
terms have in mind; it is your account and your material, but worth knowing.

Usage:
  # one-time, in the automation profile
  python chatgpt_browser_driver.py login

  python essay_feedback_chatgpt.py --chat-url "https://chatgpt.com/g/<project>/project" \
      --prompt-file prompt.txt --essay-file essay.txt
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

import essay_feedback as ef
from chatgpt_browser_driver import DEFAULT_PROFILE, ChatGPTDriver

# The rubric belongs in the ChatGPT Project's own instructions, pasted once, not
# re-sent with every essay. Two reasons: a wall of identical criteria repeated in
# message after message is exactly what automated traffic looks like, and the
# project keeps it out of the conversation where it would compete with the essay
# for attention. Generated from essay_feedback so it cannot drift from the rubric
# the hosted marker uses — regenerate with --print-role after changing the bands.
ROLE_PROMPT = (
    "You are marking PTE Academic Write Essay responses.\n\n"
    "Every message you receive will contain an essay prompt and a learner's "
    "essay. Score it against the criteria below and reply with ONLY the JSON "
    "object described at the end. No commentary before or after it, ever.\n\n"
    + ef.SYSTEM_PROMPT
)

PREAMBLE = (
    "Score the essay below using these criteria exactly. Reply with only the "
    "JSON object described at the end — no commentary before or after it.\n\n"
)


def build_prompt(prompt_text: str, essay_text: str, *, send_rubric: bool = False) -> str:
    """The message for one essay.

    By default this is just the prompt and the essay, because the rubric lives in
    the Project instructions. Pass send_rubric=True to make the message
    self-contained — useful for a one-off against a plain chat, but it makes every
    message long and near-identical, which is worth avoiding in a batch.
    """
    head = (PREAMBLE + ef.SYSTEM_PROMPT + "\n\n---\n\n") if send_rubric else ""
    return (
        head
        + "ESSAY PROMPT:\n"
        + prompt_text.strip()
        + "\n\nLEARNER'S ESSAY:\n"
        + essay_text.strip()
        + "\n\nScore this essay now and return only the JSON."
    )


def pause_between(min_s: float = 20.0, max_s: float = 50.0) -> float:
    """Wait a varied amount between essays in a batch, and say so.

    Five essays arriving at exact intervals reads as a script. Uneven gaps in the
    tens of seconds look like a person reading a reply before pasting the next
    one. Call this between calls, not inside score_essay, so a single mark is
    never slowed down for no reason.
    """
    seconds = random.uniform(min_s, max_s)
    print(f"      (waiting {seconds:.0f}s)", flush=True)
    time.sleep(seconds)
    return seconds


class ChatGPTUnavailable(RuntimeError):
    """Logged out, plan limit reached, or the page did not behave as expected.

    Raised rather than returning a mark, so a caller can fall back to the hosted
    model. A missing mark is recoverable; a wrong one shown to a learner is not.
    """


def score_essay(
    prompt_text: str,
    essay_text: str,
    *,
    chat_url: str,
    profile_dir: str = DEFAULT_PROFILE,
    # Headless is blocked. Cloudflare serves headless Chrome a "Just a moment..."
    # challenge page that never resolves, so the composer never appears and the
    # session looks logged out however valid the cookies are. A visible window
    # gets through. Measured, not assumed — headless returned the challenge page
    # while the same profile headed reached the app.
    headless: bool = False,
    timeout_s: int = 300,
    send_rubric: bool = False,
    driver: ChatGPTDriver | None = None,
) -> dict[str, Any]:
    """Mark one essay. Same arguments and same returned shape as
    essay_feedback.score_essay, plus where to send it.

    Pass `driver` to reuse one browser across a batch — starting Chrome per essay
    costs more than the marking does.
    """
    if driver is not None:
        return _score_with(driver, prompt_text, essay_text, chat_url, timeout_s, send_rubric)
    with ChatGPTDriver(profile_dir, headless=headless) as d:
        return _score_with(d, prompt_text, essay_text, chat_url, timeout_s, send_rubric)


def _score_with(
    d: ChatGPTDriver, prompt_text: str, essay_text: str, chat_url: str,
    timeout_s: int, send_rubric: bool = False,
) -> dict[str, Any]:
    if not d.is_logged_in():
        raise ChatGPTUnavailable(
            "Not logged in to ChatGPT in the automation profile. "
            "Run: python chatgpt_browser_driver.py login"
        )
    try:
        message = build_prompt(prompt_text, essay_text, send_rubric=send_rubric)
        reply = d.send_and_wait(chat_url, message, timeout_s=timeout_s)
    except Exception as exc:
        notice = d.restriction_notice()
        if notice:
            raise ChatGPTUnavailable(f"ChatGPT refused: {notice}") from exc
        raise ChatGPTUnavailable(f"ChatGPT did not reply: {type(exc).__name__}") from exc

    notice = d.restriction_notice()
    if notice:
        raise ChatGPTUnavailable(f"ChatGPT refused: {notice}")

    try:
        raw = ef.extract_json(reply)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ChatGPTUnavailable(f"Could not read JSON out of the reply: {exc}") from exc

    # Code stays authoritative over everything mechanical, exactly as it is for
    # the hosted model: word count and the Form band are recomputed here, traits
    # are clamped, the gating rule is applied, and the total is re-added.
    result = ef._reconcile(raw, essay_text)
    result["marker"] = "chatgpt"       # which engine produced it, for history
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chat-url", help="the ChatGPT project or chat URL")
    ap.add_argument("--print-role", action="store_true",
                    help="print the text to paste into the Project instructions, then exit")
    ap.add_argument("--send-rubric", action="store_true",
                    help="put the rubric in the message instead of relying on the Project")
    ap.add_argument("--prompt", help="essay prompt text")
    ap.add_argument("--prompt-file")
    ap.add_argument("--essay", help="the learner's essay")
    ap.add_argument("--essay-file")
    ap.add_argument("--profile-dir", default=DEFAULT_PROFILE)
    ap.add_argument("--headed", action="store_true", help="show the browser (useful when it misbehaves)")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--json", action="store_true", help="print the raw JSON")
    args = ap.parse_args(argv)

    if args.print_role:
        print(ROLE_PROMPT)
        return 0
    if not args.chat_url:
        print("--chat-url is required (or use --print-role)", file=sys.stderr)
        return 2

    prompt = args.prompt or (Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else None)
    essay = args.essay or (Path(args.essay_file).read_text(encoding="utf-8") if args.essay_file else None)
    if not prompt or not essay:
        print("need a prompt and an essay (--prompt/--prompt-file, --essay/--essay-file)", file=sys.stderr)
        return 2

    try:
        r = score_essay(prompt, essay, chat_url=args.chat_url,
                        profile_dir=args.profile_dir, headless=not args.headed,
                        timeout_s=args.timeout, send_rubric=args.send_rubric)
    except ChatGPTUnavailable as exc:
        print(f"ChatGPT marking unavailable: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(r, indent=2, ensure_ascii=False) if args.json else ef.format_report(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
