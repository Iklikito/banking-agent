"""Synthetic bank database. All data is fake; PINs are hashed so the demo
doesn't normally carry plaintext secrets, but this is not production crypto."""
import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "bank.db"


def _h(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def init_db(force: bool = False) -> None:
    if DB_PATH.exists():
        if not force:
            return
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.executescript(
        """
        CREATE TABLE customers (
            id TEXT PRIMARY KEY, name TEXT, pin_hash TEXT,
            balance REAL, currency TEXT
        );
        CREATE TABLE cards (
            customer_id TEXT, last4 TEXT, status TEXT
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT, date TEXT, description TEXT, amount REAL
        );
        """
    )
    con.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?)",
        [
            ("C001", "Nino Beridze", _h("1234"), 2450.75, "GEL"),
            ("C002", "Giorgi Kapanadze", _h("5678"), 9120.00, "GEL"),
        ],
    )
    con.executemany(
        "INSERT INTO cards VALUES (?,?,?)",
        [("C001", "4421", "active"), ("C001", "8830", "active"), ("C002", "1105", "active")],
    )
    con.executemany(
        "INSERT INTO transactions (customer_id, date, description, amount) VALUES (?,?,?,?)",
        [
            ("C001", "2026-10-10", "Carrefour", -45.20),
            ("C001", "2026-10-09", "Wolt", -23.50),
            ("C001", "2026-10-05", "Salary", 1800.00),
            ("C001", "2026-10-03", "Georgian Water", -18.40),
            ("C001", "2026-10-01", "Magti", -30.00),
            ("C002", "2026-10-11", "Zara", -120.00),
            ("C002", "2026-10-07", "Salary", 3200.00),
        ],
    )
    con.commit()
    con.close()


if __name__ == "__main__":
    init_db(force=True)
    print(f"Seeded {DB_PATH}")
