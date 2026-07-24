"""The unattended-run behaviour of `enrich_lessons run`, with a fake browser.

Proves the overnight properties without sending a single real request:
  1. A lesson that fails a check is RE-GENERATED, not dropped.
  2. Both check layers gate acceptance - structure AND facts.
  3. A usage-limit notice triggers the long backoff, not the normal pace, and
     retries the same lesson instead of aborting the batch.
  4. Attempts are capped, so a permanently-bad lesson can't loop forever.
  5. Waits are never actually slept in tests - they're recorded.

    python test_enrich_run_loop.py
"""
from __future__ import annotations

import json
import types
from pathlib import Path
from unittest import mock

from dotenv import load_dotenv
load_dotenv()

import enrich_lessons as E

fails: list[str] = []


def check(label, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


GOOD = json.loads(Path("output/pte.chapter07.enrichment.json").read_text())
# Chapter 16's own lesson: validate_enrichment checks the lesson identifies as
# the chapter we asked for, so a multi-lesson test needs the matching fixture.
GOOD16 = json.loads(Path("output/pte.chapter16.enrichment.json").read_text())


def _lesson(**over):
    d = json.loads(json.dumps(GOOD))
    d.update(over)
    return d


class FakeDriver:
    """Stands in for the browser: hands back a scripted reply per attempt."""
    def __init__(self, replies, notice_on=()):
        self.replies = list(replies)
        self.notice_on = set(notice_on)   # 1-based attempt numbers that show a limit
        self.sends = 0
        self.page = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send_and_wait(self, url, payload, timeout_s=0):
        self.sends += 1
        r = self.replies[min(self.sends - 1, len(self.replies) - 1)]
        if isinstance(r, Exception):
            raise r
        return json.dumps(r)

    def restriction_notice(self):
        return "You've reached your limit" if self.sends in self.notice_on else None


def run_with(replies, *, notice_on=(), chapters=(7,), status=None, **argv_extra):
    """Run cmd_run against a fake driver; return (result, sleeps, stored_docs)."""
    sleeps: list[int] = []
    stored: list[dict] = []
    argv = ["run", *[str(c) for c in chapters], "--project-url", "https://x/project"]
    for k, v in argv_extra.items():
        flag = f"--{k.replace('_','-')}"
        argv += [flag] if v is None else [flag, str(v)]
    args = E.parse_args(argv)
    driver = FakeDriver(replies, notice_on)
    # Default: pretend nothing is on disk yet, so tests exercise generation.
    status_fn = status or (lambda n: ("missing", ["none"]))

    with mock.patch.object(E, "ChatGPTDriver", lambda *a, **k: driver), \
         mock.patch.object(E, "lesson_status", status_fn), \
         mock.patch.object(E, "scrape_reply_json", lambda page: None), \
         mock.patch.object(E.time, "sleep", lambda s: sleeps.append(int(s))), \
         mock.patch.object(E, "build_payload", lambda n: "PAYLOAD"), \
         mock.patch.object(E, "write_enrichment_file",
                           lambda doc, n: (stored.append(doc), Path(f"/tmp/l{n}.json"))[1]), \
         mock.patch.object(E.store, "create_db", lambda url: None), \
         mock.patch.object(E, "Session", lambda e: mock.MagicMock()), \
         mock.patch.object(E.store, "load_enrichment_file",
                           lambda s, p: types.SimpleNamespace(id=1)):
        code = E.cmd_run(args)
    return code, sleeps, stored, driver


print("a clean lesson is accepted on the first attempt")
code, sleeps, stored, drv = run_with([GOOD])
check("accepted", len(stored) == 1, f"stored={len(stored)}")
check("only one request sent", drv.sends == 1, str(drv.sends))

print("\na lesson failing the FACT check is re-generated, not dropped")
bad = _lesson()
for f in bad["overview"]["scoring_factors"]:
    if f["name"] == "Vocabulary range":
        f["name"] = "Vocabulary"          # wrong trait name -> fact check rejects
code, sleeps, stored, drv = run_with([bad, GOOD])
check("retried and then stored", len(stored) == 1 and drv.sends == 2, f"sends={drv.sends}")
check("waited between attempts", len(sleeps) >= 1 and 300 <= sleeps[0] <= 600, str(sleeps))

print("\na lesson failing the STRUCTURE check is re-generated too")
code, sleeps, stored, drv = run_with([{"nope": 1}, GOOD])
check("retried and then stored", len(stored) == 1 and drv.sends == 2, f"sends={drv.sends}")

print("\na usage limit backs off long and retries the SAME lesson")
code, sleeps, stored, drv = run_with([{"nope": 1}, GOOD], notice_on=(1,))
check("still stored after backoff", len(stored) == 1, f"stored={len(stored)}")
check("used the long backoff, not the normal pace",
      sleeps and sleeps[0] == 1800, str(sleeps))
check("did NOT abort the batch", drv.sends == 2, str(drv.sends))

print("\na permanently-bad lesson gives up at the cap")
code, sleeps, stored, drv = run_with([{"nope": 1}], max_attempts=3)
check("nothing stored", len(stored) == 0)
check("tried exactly max_attempts times", drv.sends == 3, str(drv.sends))
check("slept between attempts only (n-1)", len(sleeps) == 2, str(sleeps))
check("exit code reports failure", code == 1, str(code))

print("\nmulti-lesson run paces between lessons as well as between attempts")
code, sleeps, stored, drv = run_with([GOOD, GOOD16], chapters=(7, 16))
check("both lessons stored", len(stored) == 2, str(len(stored)))
check("one inter-lesson wait, in the 5-10m window",
      len(sleeps) == 1 and 300 <= sleeps[0] <= 600, str(sleeps))

print("\nauto-resume: an already-good lesson is skipped, with no request and no wait")
# lesson 7 is already done; only 16 gets generated, so 16's own fixture is the reply
code, sleeps, stored, drv = run_with([GOOD16], chapters=(7, 16),
                                     status=lambda n: ("ok", []) if n == 7 else ("missing", []))
check("no request for the finished lesson", drv.sends == 1, str(drv.sends))
check("only the missing one was written", len(stored) == 1, str(len(stored)))
check("skipping cost no wait", sleeps == [], str(sleeps))

print("\nauto-resume: a lesson that exists but NO LONGER passes is regenerated")
code, sleeps, stored, drv = run_with([GOOD], chapters=(7,),
                                     status=lambda n: ("stale", ["trait name wrong"]))
check("regenerated the stale lesson", drv.sends == 1 and len(stored) == 1, str(drv.sends))

print("\nauto-resume: --force regenerates even a passing lesson")
code, sleeps, stored, drv = run_with([GOOD], chapters=(7,),
                                     status=lambda n: ("ok", []), force=None)
check("forced a request anyway", drv.sends == 1 and len(stored) == 1, str(drv.sends))

print("\neverything already done -> no requests at all")
code, sleeps, stored, drv = run_with([GOOD], chapters=(7, 16), status=lambda n: ("ok", []))
check("zero requests sent", drv.sends == 0, str(drv.sends))
check("exit code is success", code == 0, str(code))

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "unattended run behaviour holds")
raise SystemExit(1 if fails else 0)
