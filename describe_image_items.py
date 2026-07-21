"""Generate PTE "Describe Image" practice items with computed ground truth.

Describe Image is scored mostly on Content: did the test taker give an overview,
pick the high-value features, quote the values correctly, compare, and close?
Scoring that needs to know what is actually in the image — so instead of asking a
model to interpret a picture, we go the other way:

  model invents only the SCENARIO + NUMBERS  ->  contract-validate (code)
  ->  facts are COMPUTED from those numbers (code)  ->  SVG rendered from them

The ground truth is therefore arithmetic, not judgement: the highest value, the
overall trend, the biggest gap and the shares are derived, never guessed. A model
can invent a silly dataset, but it cannot invent a wrong fact about it.

Chart types are the data-driven ones whose facts are computable: bar, line, pie.

Usage:
  export OLLAMA_API_KEY=...      # or .env
  python describe_image_items.py --count 6 --dry-run
  python describe_image_items.py --count 6
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"
OUTPUT_FILE = "output/describe_image_items.json"

CHART_TYPES = {"bar", "line", "pie"}
MIN_POINTS, MAX_POINTS = 4, 8
PREP_SECONDS = 25      # official Describe Image preparation time
SPEAK_SECONDS = 40     # official response time


# --------------------------------------------------------------------------- #
# Generation — the model supplies ONLY a scenario and numbers.
# --------------------------------------------------------------------------- #

def _chat(messages: list[dict[str, str]], *, model: str, temperature: float = 0.8, timeout: float = 240.0) -> str:
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not set (add it to .env).")
    resp = httpx.post(
        OLLAMA_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "stream": False, "options": {"temperature": temperature}},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.DOTALL)


def extract_json(text: str) -> Any:
    text = (text or "").strip()
    for candidate in (text, *(m.group(1) for m in _FENCE_RE.finditer(text))):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    for a, b in (("{", "}"), ("[", "]")):
        i, j = text.find(a), text.rfind(b)
        if i != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError(f"No JSON found in reply ({len(text)} chars).")


def generate_specs(count: int, *, model: str = DEFAULT_MODEL) -> list[dict[str, Any]]:
    system = (
        "You invent datasets for PTE Academic 'Describe Image' practice charts. "
        f"Produce exactly {count} chart specifications on varied real-world/academic "
        "topics (energy, education, transport, health, employment, environment, "
        "technology, population). Do not repeat a topic.\n\n"
        "Rules:\n"
        f"- chart_type is one of: bar, line, pie.\n"
        f"- {MIN_POINTS}-{MAX_POINTS} data points, plausible realistic values.\n"
        "- line charts must use time-ordered labels (years, months, quarters) and "
        "show an interesting shape (rise, fall, peak or dip) — not a flat line.\n"
        "- pie charts must have values that sum to 100 (percentages).\n"
        "- bar charts compare categories; make one clearly highest and one clearly lowest.\n"
        "- labels are short (1-3 words). Titles are descriptive and include the period if relevant.\n\n"
        "STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block "
        'containing {"items": [ ... ]}. Each item has exactly: "chart_type", '
        '"title", "subject" (a short noun phrase naming what is measured), '
        '"x_label", "y_label", "unit" (e.g. "%", "million tonnes", "hours"), and '
        '"points": [{"label": "<short>", "value": <number>}]. No prose outside the block.'
    )
    raw = _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": "Generate the specs now."}],
        model=model,
    )
    data = extract_json(raw)
    items = data.get("items", data) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


# --------------------------------------------------------------------------- #
# Contract validation (deterministic)
# --------------------------------------------------------------------------- #

REQUIRED = {"chart_type", "title", "subject", "unit", "points"}


def contract_validate(obj: Any) -> tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "not an object"
    missing = REQUIRED - set(obj)
    if missing:
        return False, f"missing fields: {sorted(missing)}"
    if obj["chart_type"] not in CHART_TYPES:
        return False, f"unknown chart_type {obj['chart_type']!r}"
    for f in ("title", "subject", "unit"):
        if not isinstance(obj.get(f), str) or not obj[f].strip():
            return False, f"empty {f}"
    pts = obj.get("points")
    if not isinstance(pts, list) or not (MIN_POINTS <= len(pts) <= MAX_POINTS):
        return False, f"{len(pts) if isinstance(pts, list) else '?'} points (need {MIN_POINTS}-{MAX_POINTS})"
    for p in pts:
        if not isinstance(p, dict) or not isinstance(p.get("label"), str) or not p["label"].strip():
            return False, "a point has no label"
        if not isinstance(p.get("value"), (int, float)) or isinstance(p.get("value"), bool):
            return False, f"non-numeric value for {p.get('label')!r}"
        if p["value"] < 0:
            return False, f"negative value for {p['label']!r}"
    if obj["chart_type"] == "pie":
        total = sum(p["value"] for p in pts)
        if not (99 <= total <= 101):
            return False, f"pie values sum to {total:g}, not 100"
    values = [p["value"] for p in pts]
    if len(set(values)) == 1:
        return False, "all values identical (nothing to describe)"
    return True, "ok"


# --------------------------------------------------------------------------- #
# Ground truth — COMPUTED from the data, never judged.
# --------------------------------------------------------------------------- #

def _fmt(v: float, unit: str) -> str:
    s = f"{v:g}"
    return f"{s}{unit}" if unit.strip() in {"%"} else f"{s} {unit}".strip()


def compute_facts(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive the facts a good description should contain. Arithmetic only."""
    pts = spec["points"]
    unit = spec["unit"]
    kind = spec["chart_type"]
    labels = [p["label"] for p in pts]
    values = [float(p["value"]) for p in pts]
    hi_i, lo_i = values.index(max(values)), values.index(min(values))
    total = sum(values)
    facts: list[dict[str, Any]] = [
        {
            "key": "overview",
            "importance": "essential",
            "text": f"The {kind} chart shows {spec['subject']}, measured in {unit}.",
        },
        {
            "key": "highest",
            "importance": "essential",
            "text": f"{labels[hi_i]} is the highest at {_fmt(values[hi_i], unit)}.",
        },
        {
            "key": "lowest",
            "importance": "essential",
            "text": f"{labels[lo_i]} is the lowest at {_fmt(values[lo_i], unit)}.",
        },
    ]

    if kind == "line":
        first, last = values[0], values[-1]
        delta = last - first
        direction = "rose" if delta > 0 else "fell" if delta < 0 else "stayed level"
        facts.append({
            "key": "overall_trend",
            "importance": "essential",
            "text": (
                f"Overall the figure {direction} from {_fmt(first, unit)} in {labels[0]} "
                f"to {_fmt(last, unit)} in {labels[-1]}"
                + (f", a change of {_fmt(abs(delta), unit)}." if delta else ".")
            ),
        })
        # steepest consecutive move
        steps = [(abs(values[i + 1] - values[i]), i) for i in range(len(values) - 1)]
        mag, i = max(steps)
        if mag:
            way = "increase" if values[i + 1] > values[i] else "decrease"
            facts.append({
                "key": "biggest_change",
                "importance": "supporting",
                "text": f"The sharpest {way} is between {labels[i]} and {labels[i + 1]} ({_fmt(mag, unit)}).",
            })
        if values[hi_i] > first and values[hi_i] > last:
            facts.append({
                "key": "peak",
                "importance": "supporting",
                "text": f"The series peaks at {labels[hi_i]} before falling back.",
            })
    else:
        gap = values[hi_i] - values[lo_i]
        ratio = values[hi_i] / values[lo_i] if values[lo_i] else 0
        cmp_text = f"{labels[hi_i]} exceeds {labels[lo_i]} by {_fmt(gap, unit)}"
        if ratio >= 1.5:
            cmp_text += f" — about {ratio:.1f} times as much"
        facts.append({"key": "comparison", "importance": "essential", "text": cmp_text + "."})

    if kind == "pie":
        facts.append({
            "key": "share",
            "importance": "essential",
            "text": f"{labels[hi_i]} accounts for {values[hi_i]:g}% of the total.",
        })
        top2 = sorted(zip(values, labels), reverse=True)[:2]
        facts.append({
            "key": "top_two",
            "importance": "supporting",
            "text": (
                f"{top2[0][1]} and {top2[1][1]} together make up "
                f"{top2[0][0] + top2[1][0]:g}% of the total."
            ),
        })
    elif kind == "bar":
        facts.append({
            "key": "total",
            "importance": "supporting",
            "text": f"The categories total {_fmt(total, unit)}.",
        })

    facts.append({
        "key": "range",
        "importance": "supporting",
        "text": f"Values range from {_fmt(min(values), unit)} to {_fmt(max(values), unit)}.",
    })
    return facts


# --------------------------------------------------------------------------- #
# SVG rendering — from the same numbers, so image and facts cannot disagree.
# --------------------------------------------------------------------------- #

W, H = 640, 400
PAD_L, PAD_R, PAD_T, PAD_B = 64, 24, 48, 64
PALETTE = ["#0f766e", "#0891b2", "#7c3aed", "#c2410c", "#65a30d", "#be123c", "#4f46e5", "#0d9488"]


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def nice_scale(vmin: float, vmax: float, ticks: int = 4) -> tuple[float, float, float]:
    """Round axis bounds/step (1/2/5 x 10^n) so gridline labels are readable."""
    import math

    span = (vmax - vmin) or abs(vmax) or 1
    raw = span / ticks
    mag = 10 ** math.floor(math.log10(raw))
    norm = raw / mag
    step = (1 if norm <= 1 else 2 if norm <= 2 else 5 if norm <= 5 else 10) * mag
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    if hi == lo:
        hi = lo + step
    return lo, hi, step


def axis_bounds(values: list[float], kind: str) -> tuple[float, float, float]:
    """Bars must start at zero (truncating them misleads). Line charts may zoom
    when the range is narrow, otherwise the shape we ask learners to describe is
    invisible."""
    vmin, vmax = min(values), max(values)
    if kind == "line" and vmin > 0 and (vmax - vmin) < 0.35 * vmax:
        pad = (vmax - vmin) * 0.25 or vmax * 0.05
        return nice_scale(vmin - pad, vmax + pad)
    return nice_scale(0, vmax * 1.05)


def _axes_svg(spec, values, labels) -> list[str]:
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B
    lo, hi, step = axis_bounds(values, spec["chart_type"])
    parts = [
        f'<line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{PAD_T + plot_h}" stroke="#94a3b8"/>',
        f'<line x1="{PAD_L}" y1="{PAD_T + plot_h}" x2="{PAD_L + plot_w}" y2="{PAD_T + plot_h}" stroke="#94a3b8"/>',
    ]
    v = lo
    while v <= hi + step / 1000:
        y = PAD_T + plot_h - ((v - lo) / (hi - lo)) * plot_h
        parts.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{PAD_L + plot_w}" y2="{y:.1f}" stroke="#e2e8f0"/>')
        parts.append(
            f'<text x="{PAD_L - 8}" y="{y + 4:.1f}" font-size="11" fill="#64748b" text-anchor="end">{v:g}</text>'
        )
        v += step
    if lo > 0:  # be explicit that the axis is zoomed, as real charts are
        parts.append(
            f'<text x="{PAD_L - 8}" y="{PAD_T - 12}" font-size="10" fill="#94a3b8" text-anchor="end">axis starts at {lo:g}</text>'
        )
    if spec.get("y_label"):
        parts.append(
            f'<text x="16" y="{PAD_T + plot_h / 2:.0f}" font-size="12" fill="#475569" '
            f'text-anchor="middle" transform="rotate(-90 16 {PAD_T + plot_h / 2:.0f})">{_esc(spec["y_label"])}</text>'
        )
    if spec.get("x_label"):
        parts.append(
            f'<text x="{PAD_L + plot_w / 2:.0f}" y="{H - 12}" font-size="12" fill="#475569" '
            f'text-anchor="middle">{_esc(spec["x_label"])}</text>'
        )
    return parts


def render_svg(spec: dict[str, Any]) -> str:
    pts = spec["points"]
    labels = [p["label"] for p in pts]
    values = [float(p["value"]) for p in pts]
    kind = spec["chart_type"]
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    body: list[str] = [
        f'<text x="{W/2:.0f}" y="26" font-size="15" font-weight="600" fill="#0f172a" '
        f'text-anchor="middle">{_esc(spec["title"])}</text>'
    ]

    if kind == "pie":
        cx, cy, r = W / 2, H / 2 + 10, 120
        angle = -90.0
        for i, (lab, val) in enumerate(zip(labels, values)):
            sweep = val / sum(values) * 360
            a0, a1 = angle, angle + sweep
            import math

            x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
            x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
            large = 1 if sweep > 180 else 0
            body.append(
                f'<path d="M {cx:.1f} {cy:.1f} L {x0:.1f} {y0:.1f} A {r} {r} 0 {large} 1 {x1:.1f} {y1:.1f} Z" '
                f'fill="{PALETTE[i % len(PALETTE)]}" stroke="#fff" stroke-width="2"/>'
            )
            mid = math.radians((a0 + a1) / 2)
            lx, ly = cx + (r * 0.65) * math.cos(mid), cy + (r * 0.65) * math.sin(mid)
            body.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="12" fill="#fff" font-weight="600" '
                f'text-anchor="middle">{val:g}%</text>'
            )
            angle = a1
        for i, lab in enumerate(labels):  # legend
            ly = 60 + i * 18
            body.append(f'<rect x="{W-150}" y="{ly-9}" width="10" height="10" fill="{PALETTE[i % len(PALETTE)]}"/>')
            body.append(f'<text x="{W-134}" y="{ly}" font-size="11" fill="#334155">{_esc(lab)}</text>')
        return _svg(body)

    body += _axes_svg(spec, values, labels)

    if kind == "bar":
        lo, hi, _ = axis_bounds(values, kind)
        n = len(values)
        slot = plot_w / n
        bw = slot * 0.6
        for i, (lab, val) in enumerate(zip(labels, values)):
            h = ((val - lo) / (hi - lo)) * plot_h
            x = PAD_L + i * slot + (slot - bw) / 2
            y = PAD_T + plot_h - h
            body.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                f'fill="{PALETTE[i % len(PALETTE)]}" rx="3"/>'
            )
            body.append(
                f'<text x="{x + bw/2:.1f}" y="{y - 6:.1f}" font-size="11" fill="#0f172a" '
                f'text-anchor="middle">{val:g}</text>'
            )
            body.append(
                f'<text x="{x + bw/2:.1f}" y="{PAD_T + plot_h + 18:.0f}" font-size="11" fill="#475569" '
                f'text-anchor="middle">{_esc(lab)}</text>'
            )
    else:  # line
        lo, hi, _ = axis_bounds(values, kind)
        n = len(values)
        step = plot_w / max(1, n - 1)
        coords = [
            (PAD_L + i * step, PAD_T + plot_h - ((v - lo) / (hi - lo)) * plot_h)
            for i, v in enumerate(values)
        ]
        body.append(
            '<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
            + '" fill="none" stroke="#0f766e" stroke-width="2.5"/>'
        )
        for (x, y), lab, val in zip(coords, labels, values):
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#0f766e"/>')
            body.append(
                f'<text x="{x:.1f}" y="{y - 10:.1f}" font-size="11" fill="#0f172a" text-anchor="middle">{val:g}</text>'
            )
            body.append(
                f'<text x="{x:.1f}" y="{PAD_T + plot_h + 18:.0f}" font-size="11" fill="#475569" '
                f'text-anchor="middle">{_esc(lab)}</text>'
            )
    return _svg(body)


def _svg(body: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
        f'role="img" style="background:#fff">' + "".join(body) + "</svg>"
    )


# --------------------------------------------------------------------------- #
# Assemble + store
# --------------------------------------------------------------------------- #

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:28] or "item"


def build_item(spec: dict[str, Any], seq: int) -> dict[str, Any]:
    return {
        "id": f"{_slug(spec['subject'])}-{seq:02d}",
        "chart_type": spec["chart_type"],
        "title": spec["title"].strip(),
        "subject": spec["subject"].strip(),
        "x_label": (spec.get("x_label") or "").strip(),
        "y_label": (spec.get("y_label") or "").strip(),
        "unit": spec["unit"].strip(),
        "points": [{"label": p["label"].strip(), "value": p["value"]} for p in spec["points"]],
        "facts": compute_facts(spec),
        "svg": render_svg(spec),
        "prep_seconds": PREP_SECONDS,
        "speak_seconds": SPEAK_SECONDS,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    p = argparse.ArgumentParser(description="Generate Describe Image items with computed ground truth.")
    p.add_argument("--count", type=int, default=6)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--output", default=OUTPUT_FILE)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    print(f"Generating {args.count} chart specs…")
    specs = generate_specs(args.count, model=args.model)
    print(f"  model returned {len(specs)}\n")

    print("Contract validation (deterministic):")
    items, seq = [], 0
    for s in specs:
        ok, reason = contract_validate(s)
        name = (s.get("title") if isinstance(s, dict) else "?") or "?"
        if ok:
            seq += 1
            items.append(build_item(s, seq))
            print(f"  PASS  {s['chart_type']:5} {name[:44]}")
        else:
            print(f"  FAIL  {'?':5} {str(name)[:44]} — {reason}")
    print(f"  -> {len(items)}/{len(specs)} valid\n")

    for it in items:
        ess = [f["text"] for f in it["facts"] if f["importance"] == "essential"]
        print(f"[{it['id']}] {it['chart_type']} — {len(it['facts'])} facts ({len(ess)} essential)")
        for e in ess:
            print(f"    • {e}")

    if args.dry_run:
        print("\n--dry-run: not writing.")
        return 0
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps({"items": items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {len(items)} items to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
