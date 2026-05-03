import sqlite3
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet
import json

# Database and encryption key paths
DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / 'users.db'
ENCRYPTION_KEY_FILE = DB_DIR / '.encryption_key'

def get_encryption_key():
    if ENCRYPTION_KEY_FILE.exists():
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, 'wb') as f:
            f.write(key)
        return key

ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

# Helper functions for password and cookies
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def encrypt_cookies(cookies: str) -> str:
    if not cookies:
        return None
    return cipher_suite.encrypt(cookies.encode()).decode()

def decrypt_cookies(encrypted_cookies: str) -> str:
    if not encrypted_cookies:
        return ""
    try:
        return cipher_suite.decrypt(encrypted_cookies.encode()).decode()
    except:
        return ""

# Database initialization – creates all tables
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # User configs table (includes lock columns)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id TEXT,
            name_prefix TEXT,
            delay INTEGER DEFAULT 30,
            cookies_encrypted TEXT,
            messages TEXT,
            automation_running INTEGER DEFAULT 0,
            locked_group_name TEXT,
            locked_nicknames TEXT,
            lock_enabled INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Admin E2EE thread table (required by app.py)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_e2ee (
            user_id INTEGER PRIMARY KEY,
            e2ee_thread_id TEXT,
            cookies TEXT,
            chat_type TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Add missing columns for existing databases (safety upgrades)
    for col in ['automation_running', 'locked_group_name', 'locked_nicknames', 'lock_enabled']:
        try:
            cursor.execute(f'ALTER TABLE user_configs ADD COLUMN {col} TEXT')
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Create default admin user: ASHIQRAJ / ASHIQRAJ123
    admin_username = "ASHIQRAJ"
    admin_password = "ASHIQRAJ123"
    cursor.execute("SELECT id FROM users WHERE username = ?", (admin_username,))
    if not cursor.fetchone():
        pwd_hash = hash_password(admin_password)
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                       (admin_username, pwd_hash))
        admin_id = cursor.lastrowid
        cursor.execute('''
            INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, messages)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, '', '', 30, ''))
        conn.commit()

    conn.commit()
    conn.close()

# ------------------- User management -------------------
def create_user(username: str, password: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        pwd_hash = hash_password(password)
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                       (username, pwd_hash))
        user_id = cursor.lastrowid
        cursor.execute('''
            INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, messages)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, '', '', 30, ''))
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already exists!"
    except Exception as e:
        return False, f"Error: {str(e)}"
    finally:
        conn.close()

def verify_user(username: str, password: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row and row[1] == hash_password(password):
        return row[0]
    return None

def get_username(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# ------------------- Config management -------------------
def get_user_config(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chat_id, name_prefix, delay, cookies_encrypted, messages, automation_running
        FROM user_configs WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'chat_id': row[0] or '',
            'name_prefix': row[1] or '',
            'delay': row[2] or 30,
            'cookies': decrypt_cookies(row[3]),
            'messages': row[4] or '',
            'automation_running': row[5] or 0
        }
    return None

def update_user_config(user_id: int, chat_id: str, name_prefix: str, delay: int, cookies: str, messages: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    enc_cookies = encrypt_cookies(cookies)
    cursor.execute('''
        UPDATE user_configs
        SET chat_id = ?, name_prefix = ?, delay = ?, cookies_encrypted = ?,
            messages = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (chat_id, name_prefix, delay, enc_cookies, messages, user_id))
    conn.commit()
    conn.close()

# ------------------- Automation state -------------------
def set_automation_running(user_id: int, is_running: bool):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_configs
        SET automation_running = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (1 if is_running else 0, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT automation_running FROM user_configs WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False

# ------------------- Lock system -------------------
def get_lock_config(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chat_id, locked_group_name, locked_nicknames, lock_enabled, cookies_encrypted
        FROM user_configs WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        try:
            nicknames = json.loads(row[2]) if row[2] else {}
        except:
            nicknames = {}
        return {
            'chat_id': row[0] or '',
            'locked_group_name': row[1] or '',
            'locked_nicknames': nicknames,
            'lock_enabled': bool(row[3]),
            'cookies': decrypt_cookies(row[4])
        }
    return None

def update_lock_config(user_id: int, chat_id: str, locked_group_name: str, locked_nicknames: dict, cookies=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    nicknames_json = json.dumps(locked_nicknames)
    if cookies is not None:
        enc_cookies = encrypt_cookies(cookies)
        cursor.execute('''
            UPDATE user_configs
            SET chat_id = ?, locked_group_name = ?, locked_nicknames = ?,
                cookies_encrypted = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (chat_id, locked_group_name, nicknames_json, enc_cookies, user_id))
    else:
        cursor.execute('''
            UPDATE user_configs
            SET chat_id = ?, locked_group_name = ?, locked_nicknames = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (chat_id, locked_group_name, nicknames_json, user_id))
    conn.commit()
    conn.close()

def set_lock_enabled(user_id: int, enabled: bool):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_configs
        SET lock_enabled = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (1 if enabled else 0, user_id))
    conn.commit()
    conn.close()

def get_lock_enabled(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT lock_enabled FROM user_configs WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False

# ------------------- Admin E2EE functions -------------------
def get_admin_e2ee_thread_id(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT e2ee_thread_id FROM admin_e2ee WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_admin_e2ee_thread_id(user_id: int, thread_id: str, cookies: str, chat_type: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO admin_e2ee (user_id, e2ee_thread_id, cookies, chat_type)
        VALUES (?, ?, ?, ?)
    ''', (user_id, thread_id, cookies, chat_type))
    conn.commit()
    conn.close()

# Initialize database on module load
init_db()
