"""Interactive CLI: python chat.py"""
import asyncio
import uuid

from agent.graph import build_graph
from agent.llm import as_text


async def main():
    graph = await build_graph()
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    print("Bank assistant (Ctrl+C to quit). Try: I'm C001, PIN 1234, what's my balance?")
    while True:
        text = input("you> ").strip()
        if not text:
            continue
        res = await graph.ainvoke({"messages": [("user", text)]}, cfg)
        print("bot>", as_text(res["messages"][-1].content))


if __name__ == "__main__":
    asyncio.run(main())
