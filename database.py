import sqlite3
import hashlib
import os
from datetime import datetime, timedelta

# ✅ Ensure the data directory exists
DB_PATH = "data/users.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User config table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_config (
            user_id INTEGER PRIMARY KEY,
            chat_id TEXT DEFAULT '',
            name_prefix TEXT DEFAULT '',
            delay INTEGER DEFAULT 5,
            cookies TEXT DEFAULT '',
            messages TEXT DEFAULT 'Hello!\\nHow are you?',
            automation_running INTEGER DEFAULT 0,
            admin_e2ee_thread_id TEXT DEFAULT '',
            admin_e2ee_chat_type TEXT DEFAULT 'REGULAR',
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    
    # Sessions table for active users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password):
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                       (username, hash_password(password)))
        user_id = cursor.lastrowid
        cursor.execute("INSERT INTO user_config (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already exists!"
    finally:
        conn.close()

def verify_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ? AND password = ?", 
                   (username, hash_password(password)))
    row = cursor.fetchone()
    conn.close()
    return row['id'] if row else None

def get_username(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row['username'] if row else None

def get_user_config(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_config WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'chat_id': row['chat_id'],
            'name_prefix': row['name_prefix'],
            'delay': row['delay'],
            'cookies': row['cookies'],
            'messages': row['messages']
        }
    return None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_config 
        SET chat_id = ?, name_prefix = ?, delay = ?, cookies = ?, messages = ?
        WHERE user_id = ?
    ''', (chat_id, name_prefix, delay, cookies, messages, user_id))
    conn.commit()
    conn.close()

def set_automation_running(user_id, running):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE user_config SET automation_running = ? WHERE user_id = ?", 
                   (1 if running else 0, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT automation_running FROM user_config WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row['automation_running']) if row else False

def get_admin_e2ee_thread_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT admin_e2ee_thread_id, admin_e2ee_chat_type FROM user_config WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row['admin_e2ee_thread_id']:
        thread_id = row['admin_e2ee_thread_id']
        chat_type = row['admin_e2ee_chat_type'] or 'REGULAR'
        if chat_type == 'E2EE' and '/e2ee/' not in thread_id:
            return thread_id  # just the ID
        return thread_id
    return None

def set_admin_e2ee_thread_id(user_id, thread_id, cookies, chat_type='REGULAR'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_config 
        SET admin_e2ee_thread_id = ?, admin_e2ee_chat_type = ?, cookies = ?
        WHERE user_id = ?
    ''', (thread_id, chat_type, cookies, user_id))
    conn.commit()
    conn.close()

# --- Session Management ---
def update_user_session(session_id, user_id):
    """Insert or update session activity."""
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO user_sessions (session_id, user_id, last_active, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET last_active = ?
    ''', (session_id, user_id, now, now, now))
    conn.commit()
    conn.close()

def remove_user_session(session_id):
    """Delete session on logout."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    # Also clean old sessions
    cleanup_old_sessions()

def cleanup_old_sessions():
    """Remove sessions older than 5 minutes."""
    conn = get_db_connection()
    cursor = conn.cursor()
    expire_time = datetime.now() - timedelta(minutes=5)
    cursor.execute("DELETE FROM user_sessions WHERE last_active < ?", (expire_time.isoformat(),))
    conn.commit()
    conn.close()

def get_active_user_count():
    """Get number of unique users with recent activity (last 5 minutes)."""
    cleanup_old_sessions()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_sessions")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

# Initialize DB when module loads
init_db()init_db()
