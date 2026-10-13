"""MCP server exposing the mock bank's tools over stdio.

Design note: the server only does data access. Who is *allowed* to call what
is decided in the agent graph (agent/graph.py), not here and not by the LLM.
"""
import json
import sqlite3

from mcp.server.fastmcp import FastMCP

from seed import DB_PATH, _h, init_db

init_db()  # creates the DB on first run only
mcp = FastMCP("bank")


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@mcp.tool()
def verify_pin(customer_id: str, pin: str) -> str:
    """Verify a customer's PIN. Returns 'VERIFIED' or 'FAILED'."""
    with _con() as con:
        row = con.execute(
            "SELECT pin_hash FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
    if row and row["pin_hash"] == _h(pin):
        return "VERIFIED"
    return "FAILED"


@mcp.tool()
def get_balance(customer_id: str) -> str:
    """Get the account balance of the customer."""
    with _con() as con:
        row = con.execute(
            "SELECT balance, currency FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
    if not row:
        return json.dumps({"error": "unknown customer"})
    return json.dumps({"balance": row["balance"], "currency": row["currency"]})


@mcp.tool()
def get_recent_transactions(customer_id: str, limit: int = 5) -> str:
    """Get the customer's most recent transactions (newest first)."""
    limit = max(1, min(int(limit), 20))
    with _con() as con:
        rows = con.execute(
            "SELECT date, description, amount FROM transactions "
            "WHERE customer_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (customer_id, limit),
        ).fetchall()
    return json.dumps([dict(r) for r in rows])


@mcp.tool()
def block_card(customer_id: str, card_last4: str) -> str:
    """Block one of the customer's cards, identified by its last 4 digits."""
    with _con() as con:
        row = con.execute(
            "SELECT status FROM cards WHERE customer_id = ? AND last4 = ?",
            (customer_id, card_last4),
        ).fetchone()
        if not row:
            return json.dumps({"error": "no such card for this customer"})
        if row["status"] == "blocked":
            return json.dumps({"result": "already blocked", "card": card_last4})
        con.execute(
            "UPDATE cards SET status = 'blocked' WHERE customer_id = ? AND last4 = ?",
            (customer_id, card_last4),
        )
    return json.dumps({"result": "blocked", "card": card_last4})


if __name__ == "__main__":
    mcp.run(transport="stdio")
