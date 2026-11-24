import os
from database import init_db, query_db

init_db()
user_id = query_db(
    "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
    ("localuser", "local@example.com", "hash", "patient"),
    commit=True,
)
row = query_db("SELECT COUNT(*) as count FROM users", one=True)
print("user_id:", user_id)
print("user_count:", row["count"])
print("db_exists:", os.path.exists("healthcare.db"))
