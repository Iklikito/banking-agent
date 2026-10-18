"""Offline tests for the server-side PIN lockout. No Ollama, no API, no GPU needed.

Run from the project root:  python -m pytest -q
Each test gets its own temporary database, so your real bank/bank.db is never touched.
"""
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bank"))
import mcp_server as srv  # noqa: E402
import seed  # noqa: E402


@pytest.fixture()
def clock(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(seed, "DB_PATH", db)
    monkeypatch.setattr(srv, "DB_PATH", db)
    seed.init_db(force=True)
    t = {"now": 1_000_000.0}
    monkeypatch.setattr(srv, "_now", lambda: t["now"])
    return t


def test_correct_pin_works(clock):
    assert srv.verify_pin("C001", "1234") == "VERIFIED"


def test_wrong_pin_reports_remaining_attempts(clock):
    assert srv.verify_pin("C001", "0000") == "FAILED: 2 attempt(s) remaining."
    assert srv.verify_pin("C001", "0001") == "FAILED: 1 attempt(s) remaining."


def test_third_wrong_pin_locks(clock):
    srv.verify_pin("C001", "0000")
    srv.verify_pin("C001", "0001")
    assert srv.verify_pin("C001", "0002").startswith("LOCKED")


def test_correct_pin_refused_while_locked(clock):
    for pin in ("0000", "0001", "0002"):
        srv.verify_pin("C001", pin)
    assert srv.verify_pin("C001", "1234").startswith("LOCKED")  # the pin_guessing case


def test_lock_expires_after_five_minutes(clock):
    for pin in ("0000", "0001", "0002"):
        srv.verify_pin("C001", pin)
    clock["now"] += 299
    assert srv.verify_pin("C001", "1234").startswith("LOCKED")
    clock["now"] += 2
    assert srv.verify_pin("C001", "1234") == "VERIFIED"


def test_failure_count_restarts_after_lock_expires(clock):
    for pin in ("0000", "0001", "0002"):
        srv.verify_pin("C001", pin)
    clock["now"] += 301
    assert srv.verify_pin("C001", "0000") == "FAILED: 2 attempt(s) remaining."


def test_success_resets_counter(clock):
    srv.verify_pin("C001", "0000")
    srv.verify_pin("C001", "0001")
    assert srv.verify_pin("C001", "1234") == "VERIFIED"
    assert srv.verify_pin("C001", "0000") == "FAILED: 2 attempt(s) remaining."


def test_customers_are_independent(clock):
    for pin in ("0000", "0001", "0002"):
        srv.verify_pin("C001", pin)
    assert srv.verify_pin("C002", "5678") == "VERIFIED"


def test_unknown_id_is_plain_failed_and_leaves_no_row(clock):
    for _ in range(5):
        assert srv.verify_pin("C999", "1234") == "FAILED"
    con = sqlite3.connect(srv.DB_PATH)
    assert con.execute("SELECT COUNT(*) FROM pin_attempts").fetchone()[0] == 0
    con.close()


def test_old_database_without_attempts_table_still_works(clock):
    con = sqlite3.connect(srv.DB_PATH)
    con.execute("DROP TABLE IF EXISTS pin_attempts")
    con.commit()
    con.close()
    assert srv.verify_pin("C001", "0000") == "FAILED: 2 attempt(s) remaining."


def test_parallel_guesses_cannot_beat_the_limit(clock):
    # 12 simultaneous wrong guesses: exactly 2 get "FAILED", the rest see LOCKED.
    results, lock = [], threading.Lock()

    def guess(i):
        r = srv.verify_pin("C001", f"{i:04d}")
        with lock:
            results.append(r)

    threads = [threading.Thread(target=guess, args=(i,)) for i in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(r.startswith("FAILED") for r in results) == 2
    assert sum(r.startswith("LOCKED") for r in results) == 10
    assert srv.verify_pin("C001", "1234").startswith("LOCKED")


def test_lock_does_not_block_other_tools(clock):
    # The lock only guards authentication; data tools are gated by the agent graph.
    for pin in ("0000", "0001", "0002"):
        srv.verify_pin("C001", pin)
    assert "balance" in srv.get_balance("C001")
