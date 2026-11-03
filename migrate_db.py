import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "application.db")
con = sqlite3.connect(db_path)

def add_col_if_missing(table, col, col_def):
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        print(f"Added {col} to {table}")
    else:
        print(f"{col} already exists in {table}")

add_col_if_missing("emails", "label", "VARCHAR(50)")
add_col_if_missing("chat_messages", "reply_to_id", "INTEGER")
add_col_if_missing("user_profiles", "notification_preferences", "VARCHAR(255) DEFAULT 'email,chat,sound'")
add_col_if_missing("email_attachments", "mimetype", "VARCHAR(150) DEFAULT 'application/octet-stream'")

con.commit()
con.close()
print("Database schema migration completed successfully!")

