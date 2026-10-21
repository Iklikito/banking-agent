"""Shared offline test helpers: a scripted fake model and in-process bank tools.

Nothing here needs Ollama, an API key or a GPU. The tools are the real functions from
bank/mcp_server.py running on a temporary SQLite file, so your bank.db is never touched.
"""
import sqlite3
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bank"))

import mcp_server as srv  # noqa: E402
import seed  # noqa: E402
from agent.graph import build_graph, handoff_to_human  # noqa: E402


class ScriptedLLM:
    """Stands in for the chat model: returns the prepared replies in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0  # how many times the graph asked the model for a reply

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages):
        self.calls += 1
        return self.replies.pop(0) if self.replies else AIMessage("done")


def call(name, **args):
    """An AIMessage in which the model asks for one tool call."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{name}"}])


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setattr(seed, "DB_PATH", path)
    monkeypatch.setattr(srv, "DB_PATH", path)
    seed.init_db(force=True)
    return path


@pytest.fixture()
def make_graph(db):
    """make_graph(replies) -> (compiled graph, fake llm), wired to the temporary database."""
    tools = {
        t.name: t
        for t in (
            StructuredTool.from_function(srv.verify_pin, name="verify_pin"),
            StructuredTool.from_function(srv.get_balance, name="get_balance"),
            StructuredTool.from_function(srv.get_recent_transactions,
                                         name="get_recent_transactions"),
            StructuredTool.from_function(srv.block_card, name="block_card"),
            handoff_to_human,
        )
    }

    async def _make(replies):
        llm = ScriptedLLM(replies)
        return await build_graph(llm=llm, tools=tools), llm

    return _make


def card_status(db_path, last4):
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT status FROM cards WHERE last4 = ?", (last4,)).fetchone()[0]
    finally:
        con.close()


def attempts_rows(db_path):
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT COUNT(*) FROM pin_attempts").fetchone()[0]
    except sqlite3.OperationalError:  # table not created: no attempt ever reached the server
        return 0
    finally:
        con.close()


async def run(graph, *turns, thread="t"):
    res = None
    for turn in turns:
        res = await graph.ainvoke({"messages": [("user", turn)]},
                                  {"configurable": {"thread_id": thread}})
    return res


def tool_results(res):
    return [m.content for m in res["messages"] if m.type == "tool"]
