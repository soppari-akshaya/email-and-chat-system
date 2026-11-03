import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "application.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. users table
cols_users = [c[1] for c in cur.execute("PRAGMA table_info(users)").fetchall()]
if "online_status" not in cols_users:
    cur.execute("ALTER TABLE users ADD COLUMN online_status VARCHAR(20) DEFAULT 'offline'")
    print("Added online_status to users")

# 2. chat_messages table
cols_msgs = [c[1] for c in cur.execute("PRAGMA table_info(chat_messages)").fetchall()]
if "delivery_status" not in cols_msgs:
    cur.execute("ALTER TABLE chat_messages ADD COLUMN delivery_status VARCHAR(20) DEFAULT 'sent'")
    print("Added delivery_status to chat_messages")
if "delivered_at" not in cols_msgs:
    cur.execute("ALTER TABLE chat_messages ADD COLUMN delivered_at DATETIME")
    print("Added delivered_at to chat_messages")
if "seen_at" not in cols_msgs:
    cur.execute("ALTER TABLE chat_messages ADD COLUMN seen_at DATETIME")
    print("Added seen_at to chat_messages")

conn.commit()
cur.close()
conn.close()
print("Migration completed successfully.")

