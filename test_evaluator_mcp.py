"""Drive the unified evaluator MCP server over real stdio, as a client would.

Proves every stage's tool is reachable over the protocol and the pass/fix/escalate
verdicts behave end to end — not just as in-process calls.

    python test_evaluator_mcp.py
"""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent


def _json(result):
    sc = result.structuredContent
    return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc


def _load(path):
    data = json.loads((ROOT / path).read_text())
    if isinstance(data, dict):
        for k in ("items", "passages", "prompts"):
            if k in data:
                return data[k]
    return data


async def main() -> int:
    params = StdioServerParameters(
        command=str(ROOT / ".venv/bin/python"),
        args=[str(ROOT / "evaluator_mcp_server.py")],
        cwd=str(ROOT),
    )
    fails = []

    def check(label, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
        if not cond:
            fails.append(label)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("discovery")
            tools = {t.name for t in (await session.list_tools()).tools}
            want = {"list_evaluators", "check_health", "check_extraction",
                    "check_reading_item", "check_describe_image_item",
                    "evaluate_enrichment_lesson", "evaluate_with"}
            check("all stage tools exposed", want <= tools, str(want - tools))
            listed = _json(await session.call_tool("list_evaluators", {}))
            arts = {e["artifact"] for e in listed}
            check("all four artifacts represented",
                  {"clean_chunks", "reading_item", "describe_image_item", "enrichment_lesson"} <= arts,
                  str(arts))

            print("\nfast health over the wire")
            h = _json(await session.call_tool("check_health", {}))
            check("deterministic checks healthy", h["all_healthy"] is True, str(h))

            print("\nextraction: garbled source escalates, clean source passes")
            bad = _json(await session.call_tool("check_extraction",
                        {"chunks": [{"node_id": "n", "text": "the  quick  brown fox and the  lazy dog"}]}))
            check("garbled -> escalate", bad["verdict"] == "escalate", str(bad["verdict"]))
            good = _json(await session.call_tool("check_extraction",
                         {"chunks": [{"node_id": "n", "text": "The quick brown fox jumps over the lazy dog."}]}))
            check("clean -> pass", good["verdict"] == "pass", str(good["verdict"]))

            print("\nreading item: real passes, malformed fixes")
            bank = _load("output/reading_mcq_items.json")
            r = _json(await session.call_tool("check_reading_item", {"item": bank[0]}))
            check("real question -> pass", r["verdict"] == "pass", str(r["verdict"]))
            broken = json.loads(json.dumps(bank[0]))
            broken["options"] = broken["options"][:2]
            r = _json(await session.call_tool("check_reading_item", {"item": broken}))
            check("too few options -> fix", r["verdict"] == "fix", str(r["verdict"]))

            print("\ndescribe image item: real passes, malformed fixes")
            di = _load("output/describe_image_items.json")
            r = _json(await session.call_tool("check_describe_image_item", {"item": di[0]}))
            check("real chart -> pass", r["verdict"] == "pass", str(r["verdict"]))
            broken = json.loads(json.dumps(di[0]))
            broken["points"] = [broken["points"][0]]
            r = _json(await session.call_tool("check_describe_image_item", {"item": broken}))
            check("one point -> fix", r["verdict"] == "fix", str(r["verdict"]))

            print("\nenrichment: good lesson passes, wrong trait name fixes")
            essay = _load("output/pte.chapter07.enrichment.json")
            r = _json(await session.call_tool("evaluate_enrichment_lesson", {"lesson": essay}))
            check("good essay -> pass", r["verdict"] == "pass", str(r["verdict"]))
            bad = json.loads(json.dumps(essay))
            for f in bad["overview"]["scoring_factors"]:
                if f["name"] == "Vocabulary range":
                    f["name"] = "Vocabulary"
            r = _json(await session.call_tool("evaluate_enrichment_lesson", {"lesson": bad}))
            check("wrong trait name -> fix", r["verdict"] == "fix", str(r["verdict"]))

            print("\nunknown evaluator handled")
            r = _json(await session.call_tool("evaluate_with", {"evaluator_name": "nope", "payload": {}}))
            check("error + available list", "error" in r and "available" in r, str(r))

    print("\n" + "=" * 58)
    print(f"{len(fails)} FAILED: {fails}" if fails else "unified evaluator server works end-to-end over stdio")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
