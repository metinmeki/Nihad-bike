import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nihadbike.db")

print(f"Using database: {DB_PATH}")

username = "Nihad"
password = "Nihad@1212"
role = "admin"

conn = sqlite3.connect(DB_PATH)
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'cashier',
        created_at TEXT NOT NULL
    )
    """
)

existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
if existing:
    conn.execute(
        "UPDATE users SET password_hash=?, role=? WHERE username=?",
        (generate_password_hash(password), role, username),
    )
    print(f"Updated existing user '{username}' -> password reset, role set to '{role}'.")
else:
    conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (username, generate_password_hash(password), role, datetime.now().isoformat()),
    )
    print(f"Created new user '{username}' with role '{role}'.")

conn.commit()

print("")
print("All users currently in the database:")
for row in conn.execute("SELECT id, username, role FROM users"):
    print(f"  id={row[0]}  username={row[1]!r}  role={row[2]}")

conn.close()
print("Done.")