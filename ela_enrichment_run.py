"""Repair ELA's templated example sentences, a batch at a time, unattended.

3,471 vocabulary items have every example sentence generated from a template —
"The meeting focused on yacht as a key issue" — which teaches nobody anything.
Doing it by hand is: run a command, paste the prompt into ChatGPT, wait, copy the
JSON back, import it. Thirty-five times. This is that loop.

The order matters, and the middle step is the point:

    prompt-generate --ids-file   ->  ChatGPT  ->  VALIDATE  ->  import

Without validation this is only faster. ELA's own validator ran on the original
batches and let all six of the real templates through, because it is a list of
specific sentences somebody noticed rather than a measure of reuse. It now also
counts how often one sentence shape is reused across a batch, and a batch where
the same husk appears for five or more different words is rejected whole and
retried. A bad batch never reaches the database.

Everything the browser needs was learned the hard way and is baked in: a visible
window (headless is served a Cloudflare challenge that looks exactly like being
logged out), uneven gaps between sends, and a hard stop the moment ChatGPT starts
refusing rather than hammering a limited account.

Usage:
  python ela_enrichment_run.py --dry-run --batches 1     # fetch + validate only
  python ela_enrichment_run.py                           # the lot, importing
  python ela_enrichment_run.py --batches 5 --size 100
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

from chatgpt_browser_driver import DEFAULT_PROFILE, ChatGPTDriver

ELA = Path("/Users/roy/Desktop/Work/Ela")
IDS_FILE = Path("output/ela_flaky_item_ids.txt")
WORK = Path("output/ela_enrichment")
CHAT_URL = "https://chatgpt.com/g/g-p-6a64b2721ff081919d9f7a483d7ee498-english-enrichment/project"


def artisan(*args: str, timeout: int = 300) -> tuple[int, str]:
    """Run an ELA artisan command and hand back what it said."""
    p = subprocess.run(["php", "artisan", *args], cwd=ELA, capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def extract_json_array(reply: str) -> list[dict]:
    """The reply should be a bare JSON array. Tolerate a fenced block, because a
    model that is told six times not to add fences will occasionally add fences."""
    text = (reply or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("no JSON array in the reply")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, list) or not data:
        raise ValueError("reply was not a non-empty JSON array")
    return data


def check_identity(batch: list[dict], sent: list[dict]) -> list[str]:
    """The importer matches on item_type + content + source_type + source_label
    together. Change any of them and it inserts a second copy of the word instead
    of updating the real one, leaving the learner with two entries, one good and
    one bad. Cheaper to catch here than to find later in the database."""
    by_content = {i.get("content"): i for i in sent}
    problems = []
    for row in batch:
        original = by_content.get(row.get("content"))
        if original is None:
            problems.append(f"returned a word that was not sent: {row.get('content')!r}")
            continue
        for f in ("item_type", "content", "source_label"):
            if row.get(f) != original.get(f):
                problems.append(
                    f"{original.get('content')!r}: {f} changed "
                    f"{original.get(f)!r} -> {row.get(f)!r}")
    if len(batch) != len(sent):
        problems.append(f"sent {len(sent)} items, got {len(batch)} back")
    return problems


def run_batch(d: ChatGPTDriver, ids: list[int], n: int, *, dry_run: bool) -> bool:
    WORK.mkdir(parents=True, exist_ok=True)
    stem = f"repair-{ids[0]}-{ids[-1]}"
    ids_path = (WORK / f"{stem}.ids.txt").resolve()
    prompt_path = (WORK / f"{stem}.prompt.txt").resolve()
    sent_path = (WORK / f"{stem}.sent.json").resolve()
    out_path = (WORK / f"{stem}.enriched.json").resolve()
    ids_path.write_text("\n".join(str(i) for i in ids) + "\n")

    print(f"\n── batch {n}: {len(ids)} items, ids {ids[0]}–{ids[-1]}", flush=True)

    # --inline-json matters: without it the prompt tells ChatGPT to return a
    # downloadable file, and the driver collects the filename instead of the data.
    code, out = artisan("learning-items:prompt-generate", f"--ids-file={ids_path}",
                        "--inline-json",
                        f"--prompt-output={prompt_path}", f"--export={sent_path}")
    if code != 0 or not prompt_path.exists():
        print(f"   prompt-generate failed: {out[:200]}")
        return False
    sent = json.loads(sent_path.read_text())
    print(f"   prompt built ({prompt_path.stat().st_size:,} bytes, {len(sent)} rows)", flush=True)

    print("   asking ChatGPT…", flush=True)
    reply = d.send_and_wait(CHAT_URL, prompt_path.read_text(), timeout_s=900)
    notice = d.restriction_notice()
    if notice:
        print(f"   ChatGPT refused: {notice}")
        raise SystemExit("stopping — the account is being limited")

    try:
        batch = extract_json_array(reply)
    except (ValueError, json.JSONDecodeError) as exc:
        (WORK / f"{stem}.reply.txt").write_text(reply)
        print(f"   unreadable reply ({exc}); saved for inspection")
        return False
    print(f"   got {len(batch)} enriched rows", flush=True)

    problems = check_identity(batch, sent)
    if problems:
        print("   identity check failed — importing this would duplicate words:")
        for p in problems[:4]:
            print(f"     {p}")
        return False

    out_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False))
    code, out = artisan("learning-items:validate-batch", str(out_path),
                        f"--limit={len(batch)}")
    if code != 0:
        print("   REJECTED by validation:")
        for line in [l for l in out.splitlines() if l.strip()][:4]:
            print(f"     {line.strip()}")
        return False
    print("   validation passed", flush=True)

    if dry_run:
        print(f"   dry run — not imported. JSON at {out_path}")
        return True

    code, out = artisan("learning-items:import", str(out_path))
    print(f"   {'imported' if code == 0 else 'IMPORT FAILED'}: {out.splitlines()[-1][:120] if out else ''}")
    return code == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids-file", default=str(IDS_FILE))
    ap.add_argument("--size", type=int, default=100, help="items per batch")
    ap.add_argument("--batches", type=int, help="stop after this many")
    ap.add_argument("--dry-run", action="store_true", help="fetch and validate, do not import")
    ap.add_argument("--start", type=int, default=0, help="skip this many batches")
    args = ap.parse_args(argv)

    ids = [int(x) for x in Path(args.ids_file).read_text().split() if x.strip().isdigit()]
    chunks = [ids[i : i + args.size] for i in range(0, len(ids), args.size)][args.start :]
    if args.batches:
        chunks = chunks[: args.batches]
    print(f"{len(ids):,} items to repair -> {len(chunks)} batches of {args.size}"
          f"{'  (DRY RUN — nothing will be imported)' if args.dry_run else ''}")

    ok = bad = 0
    # Headless is served a Cloudflare challenge page that never resolves and looks
    # exactly like being logged out. The window has to be visible.
    with ChatGPTDriver(DEFAULT_PROFILE, headless=False) as d:
        if not d.is_logged_in():
            print("Not logged in — run: python chatgpt_browser_driver.py login")
            return 1
        for n, chunk in enumerate(chunks, start=1):
            if n > 1:
                pause = random.uniform(25, 60)
                print(f"   (waiting {pause:.0f}s)", flush=True)
                time.sleep(pause)
            try:
                if run_batch(d, chunk, n, dry_run=args.dry_run):
                    ok += 1
                else:
                    bad += 1
            except SystemExit:
                raise
            except Exception as exc:
                bad += 1
                print(f"   batch failed: {type(exc).__name__}: {str(exc)[:120]}")

    print(f"\n{ok} batches done, {bad} failed. "
          f"Failed batches are safe to re-run — nothing partial was imported.")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
