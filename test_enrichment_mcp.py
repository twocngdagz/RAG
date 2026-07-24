"""Drive the MCP server over a real stdio client, exactly as Claude Desktop would.

Proves the tools are reachable over the wire and the pass/fix/escalate loop
behaves through the protocol, not just as in-process Python calls.
"""
import asyncio
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent


def _content_json(result):
    # FastMCP puts the return value in structuredContent; list returns are wrapped
    # under "result", dict returns come through directly.
    sc = result.structuredContent
    return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc


async def main() -> int:
    params = StdioServerParameters(
        command=str(ROOT / ".venv/bin/python"),
        args=[str(ROOT / "enrichment_mcp_server.py")],
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

            print("the model can discover the tools")
            tools = {t.name for t in (await session.list_tools()).tools}
            check("all four tools exposed",
                  {"list_evaluators", "check_health", "evaluate_lesson", "evaluate_with"} <= tools,
                  str(tools))

            print("\nthe model can read what each check does")
            listed = _content_json(await session.call_tool("list_evaluators", {}))
            check("descriptions present", all(e.get("description") for e in listed), str(listed))

            print("\nhealth self-test over the wire")
            health = _content_json(await session.call_tool("check_health", {}))
            check("all evaluators healthy", health["all_healthy"] is True, str(health))

            good = json.loads((ROOT / "output/pte.chapter07.enrichment.json").read_text())

            print("\na good lesson passes")
            res = _content_json(await session.call_tool("evaluate_lesson", {"lesson": good}))
            check("verdict pass + accepted", res["verdict"] == "pass" and res["accepted"], str(res["verdict"]))

            print("\na defective lesson comes back FIX with an actionable finding")
            bad = json.loads(json.dumps(good))
            for f in bad["overview"]["scoring_factors"]:
                if f["name"] == "Vocabulary range":
                    f["name"] = "Vocabulary"
            res = _content_json(await session.call_tool("evaluate_lesson", {"lesson": bad}))
            findings = [f for r in res["results"] for f in r["findings"]]
            check("verdict fix, not accepted", res["verdict"] == "fix" and not res["accepted"], str(res["verdict"]))
            check("finding names the fix", any("Vocabulary" in f["summary"] for f in findings), str(findings))

            print("\nsimulate the fix and re-check just that evaluator -> pass")
            res = _content_json(await session.call_tool(
                "evaluate_with", {"evaluator_name": "trait_names", "lesson": good}))
            check("re-check passes", res["verdict"] == "pass", str(res["verdict"]))

            print("\nunknown evaluator name is handled, not a crash")
            res = _content_json(await session.call_tool(
                "evaluate_with", {"evaluator_name": "nope", "lesson": good}))
            check("error + available list", "error" in res and "available" in res, str(res))

    print("\n" + "=" * 58)
    print(f"{len(fails)} FAILED: {fails}" if fails else "MCP server works end-to-end over stdio")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
