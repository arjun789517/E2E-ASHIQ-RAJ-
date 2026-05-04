import sqlite3
import hashlib
from datetime import datetime

DB_FILE = "users.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_config (
        user_id INTEGER PRIMARY KEY,
        chat_id TEXT DEFAULT '',
        name_prefix TEXT DEFAULT '',
        delay INTEGER DEFAULT 10,
        cookies TEXT DEFAULT '',
        messages TEXT DEFAULT 'Hello!'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS automation_state (
        user_id INTEGER PRIMARY KEY,
        running INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_threads (
        user_id INTEGER PRIMARY KEY,
        e2ee_thread_id TEXT,
        chat_type TEXT DEFAULT 'REGULAR'
    )''')
    conn.commit()
    conn.close()

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def create_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        is_admin = 1 if username.upper() == "ASHIQRAJ" else 0
        c.execute("INSERT INTO users (username, password, is_admin, created_at) VALUES (?, ?, ?, ?)",
                  (username, hash_password(password), is_admin, datetime.now().isoformat()))
        user_id = c.lastrowid
        c.execute("INSERT INTO user_config (user_id) VALUES (?)", (user_id,))
        c.execute("INSERT INTO automation_state (user_id, running) VALUES (?, 0)", (user_id,))
        conn.commit()
        return True, "Account created"
    except sqlite3.IntegrityError:
        return False, "Username already exists"
    finally:
        conn.close()

def verify_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, is_admin FROM users WHERE username=? AND password=?", (username, hash_password(password)))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], row[1]   # user_id, is_admin
    return None, None

def get_username(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_user_config(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chat_id, name_prefix, delay, cookies, messages FROM user_config WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'chat_id': row[0] or '',
            'name_prefix': row[1] or '',
            'delay': row[2] or 10,
            'cookies': row[3] or '',
            'messages': row[4] or 'Hello!'
        }
    return None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE user_config SET chat_id=?, name_prefix=?, delay=?, cookies=?, messages=? WHERE user_id=?",
              (chat_id, name_prefix, delay, cookies, messages, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT running FROM automation_state WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row[0]) if row else False

def set_automation_running(user_id, running):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE automation_state SET running=? WHERE user_id=?", (1 if running else 0, user_id))
    conn.commit()
    conn.close()

def get_admin_e2ee_thread_id(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT e2ee_thread_id, chat_type FROM admin_threads WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None, row[1] if row else None

def set_admin_e2ee_thread_id(user_id, thread_id, chat_type='REGULAR'):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("REPLACE INTO admin_threads (user_id, e2ee_thread_id, chat_type) VALUES (?, ?, ?)",
              (user_id, thread_id, chat_type))
    conn.commit()
    conn.close()

def get_active_user_count():
    # Simple approximation: count distinct sessions? We'll not implement full session table,
    # but return total users for demo. Original used active sessions with 5 min timeout.
    # For simplicity, return count of users who have running automation or just total users.
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count
