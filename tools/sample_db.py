"""Creates a small sample SQLite database and runs READ-ONLY queries on it."""
import re
import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, department TEXT,
                        salary INTEGER, hire_date TEXT);
CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT,
                       price REAL, stock INTEGER);
CREATE TABLE orders (id INTEGER PRIMARY KEY, product_id INTEGER, quantity INTEGER,
                     customer TEXT, order_date TEXT);
"""

EMPLOYEES = [
    (1, "Asha Rao", "Engineering", 95000, "2020-03-15"),
    (2, "Ravi Kumar", "Engineering", 88000, "2021-07-01"),
    (3, "Meera Nair", "Marketing", 72000, "2019-11-20"),
    (4, "John Smith", "Sales", 65000, "2022-01-10"),
    (5, "Priya Das", "HR", 60000, "2018-05-05"),
    (6, "Liam Chen", "Sales", 70000, "2023-02-14"),
]
PRODUCTS = [
    (1, "Laptop", "Electronics", 899.99, 25),
    (2, "Headphones", "Electronics", 59.50, 120),
    (3, "Desk Chair", "Furniture", 149.00, 40),
    (4, "Notebook", "Stationery", 3.25, 500),
    (5, "Monitor", "Electronics", 229.00, 60),
]
ORDERS = [
    (1, 1, 2, "Acme Corp", "2025-01-12"), (2, 2, 10, "Globex", "2025-02-03"),
    (3, 3, 5, "Initech", "2025-02-18"), (4, 4, 200, "Acme Corp", "2025-03-01"),
    (5, 5, 8, "Globex", "2025-03-22"),
]


def ensure_db(db_path: Path) -> None:
    """Create and fill the database the first time it is needed."""
    db_path = Path(db_path)
    if db_path.exists():
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.executemany("INSERT INTO employees VALUES (?,?,?,?,?)", EMPLOYEES)
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?)", PRODUCTS)
    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", ORDERS)
    conn.commit()
    conn.close()


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def get_schema(db_path: Path) -> str:
    conn = _connect_readonly(db_path)
    rows = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    return "\n".join(sql for _, sql in rows)


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum)\b", re.I)


def run_select(db_path: Path, sql: str, limit: int = 50) -> str:
    """Run a single SELECT statement and return a text table."""
    sql = sql.strip().rstrip(";")
    if not re.match(r"^(select|with)\b", sql, re.I):
        raise ValueError("Only SELECT queries are allowed.")
    if ";" in sql or _FORBIDDEN.search(sql):
        raise ValueError("Query contains forbidden statements.")
    conn = _connect_readonly(db_path)
    try:
        cur = conn.execute(sql)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchmany(limit)
    finally:
        conn.close()
    if not rows:
        return "Query returned no rows."
    lines = [" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in rows]
    return "\n".join(lines)
