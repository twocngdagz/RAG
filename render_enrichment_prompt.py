"""Render the ready-to-paste ChatGPT project prompt for a book.

The prompt is engine + domain pack: `docs/enrichment-engine.md` holds the
book-agnostic instructions with `{{SLOTS}}`, and `docs/enrichment-domain-<slug>.md`
fills them. This joins the two so a new book needs a pack, not a new prompt.

Self-verifying: rendering the `pte` pack must reproduce `docs/enrichment-prompt.md`,
the prompt actually pasted into the live ChatGPT project. If it doesn't, the engine
and the pack have drifted apart and the render is not trustworthy — so `--check`
compares them and fails loudly rather than quietly emitting something different
from what is running in production.

Usage:
  python render_enrichment_prompt.py --book math5a          # print it
  python render_enrichment_prompt.py --book math5a --write  # also save it
  python render_enrichment_prompt.py --check                # verify against PTE
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
ENGINE = DOCS / "enrichment-engine.md"
LIVE_PTE_PROMPT = DOCS / "enrichment-prompt.md"


def engine_body() -> str:
    """The prompt itself, without the explanatory preamble above the first rule."""
    text = ENGINE.read_text(encoding="utf-8")
    _, _, body = text.partition("\n---\n")
    return (body or text).strip()


def slots_for(slug: str) -> dict[str, str]:
    """Slot values from a domain pack, keyed by slot name."""
    path = DOCS / f"enrichment-domain-{slug}.md"
    if not path.exists():
        raise SystemExit(f"No domain pack for {slug!r}: {path} not found.")
    out: dict[str, str] = {}
    for part in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.M)[1:]:
        head, _, body = part.partition("\n")
        name = head.strip().strip("`").strip("{}")
        if not re.fullmatch(r"[A-Z_]+", name):
            continue                      # prose sections in the pack, not slots
        body = body.strip()
        body = re.sub(r"^```json\n|\n```$", "", body).strip()
        out[name] = body
    return out


def render(slug: str) -> str:
    text = engine_body()
    for name, value in slots_for(slug).items():
        text = text.replace("{{" + name + "}}", value)
    leftover = sorted(set(re.findall(r"\{\{([A-Z_]+)\}\}", text)))
    if leftover:
        raise SystemExit(f"Domain pack {slug!r} leaves slots unfilled: {leftover}")
    return text


def _norm(s: str) -> list[str]:
    return [ln.rstrip() for ln in s.strip().splitlines() if ln.strip()]


def check() -> int:
    """Rendering pte must reproduce the prompt that is actually live."""
    if not LIVE_PTE_PROMPT.exists():
        print("No live PTE prompt to compare against.", file=sys.stderr)
        return 1
    rendered = _norm(render("pte"))
    live = _norm(LIVE_PTE_PROMPT.read_text(encoding="utf-8").partition("\n---\n")[2]
                 or LIVE_PTE_PROMPT.read_text(encoding="utf-8"))
    if rendered == live:
        print("OK — engine + pte pack reproduces the live prompt exactly.")
        return 0
    diff = list(difflib.unified_diff(live, rendered, "live prompt", "rendered", lineterm="", n=1))
    print(f"DRIFT — {len([d for d in diff if d.startswith(('+', '-')) and not d.startswith(('++', '--'))])} "
          f"differing lines between the live PTE prompt and the render:")
    print("\n".join(diff[:40]))
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", default="math5a")
    ap.add_argument("--write", action="store_true", help="save to docs/enrichment-prompt-<slug>.md")
    ap.add_argument("--check", action="store_true", help="verify the render against the live PTE prompt")
    args = ap.parse_args(argv)

    if args.check:
        return check()

    text = render(args.book)
    if args.write:
        out = DOCS / f"enrichment-prompt-{args.book}.md"
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}  ({len(text):,} chars)", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
