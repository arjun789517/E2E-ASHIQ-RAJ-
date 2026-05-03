import sqlite3
import hashlib
import os
from datetime import datetime, timedelta

DB_PATH = "data/ashiq_raj.db"

def get_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_config (
            user_id INTEGER PRIMARY KEY,
            chat_id TEXT DEFAULT '',
            name_prefix TEXT DEFAULT '',
            delay INTEGER DEFAULT 10,
            cookies TEXT DEFAULT '',
            messages TEXT DEFAULT 'Hello!\nHow are you?',
            automation_running INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    # Table for admin thread IDs (needed for missing functions)
    c.execute('''
        CREATE TABLE IF NOT EXISTS admin_threads (
            user_id INTEGER PRIMARY KEY,
            thread_id TEXT,
            chat_type TEXT DEFAULT 'REGULAR',
            cookies_snapshot TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    conn = get_db()
    c = conn.cursor()
    try:
        pwd_hash = hash_password(password)
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pwd_hash))
        user_id = c.lastrowid
        c.execute("INSERT INTO user_config (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True, "Account created successfully."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        conn.close()

def verify_user(username, password):
    conn = get_db()
    c = conn.cursor()
    pwd_hash = hash_password(password)
    c.execute("SELECT id FROM users WHERE username = ? AND password_hash = ?", (username, pwd_hash))
    row = c.fetchone()
    conn.close()
    return row['id'] if row else None

def get_username(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row['username'] if row else None

def get_user_config(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT chat_id, name_prefix, delay, cookies, messages FROM user_config WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE user_config 
        SET chat_id = ?, name_prefix = ?, delay = ?, cookies = ?, messages = ?
        WHERE user_id = ?
    ''', (chat_id, name_prefix, delay, cookies, messages, user_id))
    conn.commit()
    conn.close()

def set_automation_running(user_id, running):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE user_config SET automation_running = ? WHERE user_id = ?", (1 if running else 0, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT automation_running FROM user_config WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row['automation_running']) if row else False

def update_user_session(session_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("REPLACE INTO user_sessions (session_id, user_id, last_active) VALUES (?, ?, ?)",
              (session_id, user_id, datetime.now()))
    conn.commit()
    conn.close()

def remove_user_session(session_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

def get_active_user_count():
    conn = get_db()
    c = conn.cursor()
    cutoff = datetime.now() - timedelta(minutes=5)
    c.execute("SELECT COUNT(DISTINCT user_id) FROM user_sessions WHERE last_active > ?", (cutoff,))
    count = c.fetchone()[0]
    conn.close()
    return count

# ========== MISSING FUNCTIONS FROM ORIGINAL CODE ==========
def get_admin_e2ee_thread_id(user_id):
    """Return stored admin thread ID for this user"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT thread_id FROM admin_threads WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row['thread_id'] if row else None

def set_admin_e2ee_thread_id(user_id, thread_id, cookies_snapshot, chat_type="REGULAR"):
    """Save admin thread ID for future notifications"""
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO admin_threads (user_id, thread_id, chat_type, cookies_snapshot)
        VALUES (?, ?, ?, ?)
    ''', (user_id, thread_id, chat_type, cookies_snapshot))
    conn.commit()
    conn.close()
