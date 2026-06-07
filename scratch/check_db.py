import sqlite3
import os

db_path = "data/assest_dev.db"
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, slug FROM workspaces;")
        workspaces = cursor.fetchall()
        print(f"Workspaces in database: {workspaces}")
    except Exception as e:
        print(f"Error querying workspaces: {e}")
    conn.close()
