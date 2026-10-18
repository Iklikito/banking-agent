"""MCP server exposing the mock bank's tools over stdio.

Design note: the server only does data access. Who is *allowed* to call what
is decided in the agent graph (agent/graph.py), not here and not by the LLM.
"""
import json
import sqlite3
import time

from mcp.server.fastmcp import FastMCP

from seed import DB_PATH, _h, init_db

init_db()  # creates the DB on first run only
mcp = FastMCP("bank")


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


MAX_ATTEMPTS = 3          # wrong PINs allowed before the account is locked
LOCK_SECONDS = 300        # how long the lock lasts (even the correct PIN is refused)


def _now() -> float:
    return time.time()  # separate function so tests can control the clock


def _verify(customer_id: str, pin: str) -> str:
    # isolation_level=None: we issue BEGIN IMMEDIATE ourselves. It takes the write lock up
    # front, so two simultaneous guesses can't both read "2 failures" and both be allowed.
    con = sqlite3.connect(DB_PATH, isolation_level=None, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        # Created here, not at startup: the eval runner deletes and re-seeds the DB between
        # dialogues, and old DBs from before this feature have no such table.
        con.execute(
            "CREATE TABLE IF NOT EXISTS pin_attempts ("
            "customer_id TEXT PRIMARY KEY, failures INTEGER NOT NULL, locked_until REAL NOT NULL)"
        )
        con.execute("BEGIN IMMEDIATE")
        try:
            cust = con.execute(
                "SELECT pin_hash FROM customers WHERE id = ?", (customer_id,)
            ).fetchone()
            if not cust:
                # Unknown IDs get a plain FAILED and no row, so the reply doesn't reveal
                # which IDs exist and junk IDs can't fill the table.
                con.execute("COMMIT")
                return "FAILED"
            st = con.execute(
                "SELECT failures, locked_until FROM pin_attempts WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
            failures, locked_until = (st["failures"], st["locked_until"]) if st else (0, 0.0)
            now = _now()
            if locked_until > now:
                con.execute("COMMIT")  # locked: the PIN is not even checked
                minutes = int((locked_until - now) // 60) + 1
                return f"LOCKED: too many wrong PINs. Try again in about {minutes} minute(s)."
            if locked_until:  # a lock that has expired starts a fresh count
                failures = 0
            if cust["pin_hash"] == _h(pin):
                con.execute("DELETE FROM pin_attempts WHERE customer_id = ?", (customer_id,))
                con.execute("COMMIT")
                return "VERIFIED"
            failures += 1
            if failures >= MAX_ATTEMPTS:
                con.execute(
                    "INSERT OR REPLACE INTO pin_attempts VALUES (?, 0, ?)",
                    (customer_id, now + LOCK_SECONDS),
                )
                con.execute("COMMIT")
                return (f"LOCKED: too many wrong PINs. Try again in about "
                        f"{LOCK_SECONDS // 60} minute(s).")
            con.execute(
                "INSERT OR REPLACE INTO pin_attempts VALUES (?, ?, 0)", (customer_id, failures)
            )
            con.execute("COMMIT")
            return f"FAILED: {MAX_ATTEMPTS - failures} attempt(s) remaining."
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


@mcp.tool()
def verify_pin(customer_id: str, pin: str) -> str:
    """Verify a customer's PIN. Returns 'VERIFIED', or FAILED/LOCKED with a reason.
    Three wrong PINs lock the account for 5 minutes."""
    return _verify(customer_id, pin)


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
