import sqlite3
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet
import os
import json

# Ensure database directory exists
DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / 'users.db'
ENCRYPTION_KEY_FILE = DB_DIR / '.encryption_key'

def get_encryption_key():
    """Get or create encryption key for cookie storage"""
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

def init_db():
    """Initialize database with all required tables"""
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
    
    # User configs table
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
    
    # Add missing columns if upgrading from older version
    try:
        cursor.execute('ALTER TABLE user_configs ADD COLUMN automation_running INTEGER DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE user_configs ADD COLUMN locked_group_name TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE user_configs ADD COLUMN locked_nicknames TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE user_configs ADD COLUMN lock_enabled INTEGER DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    # Create default admin user if not exists (username: ASHIQRAJ, password: ASHIQRAJ123)
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

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def encrypt_cookies(cookies):
    """Encrypt cookies for secure storage"""
    if not cookies:
        return None
    return cipher_suite.encrypt(cookies.encode()).decode()

def decrypt_cookies(encrypted_cookies):
    """Decrypt cookies"""
    if not encrypted_cookies:
        return ""
    try:
        return cipher_suite.decrypt(encrypted_cookies.encode()).decode()
    except:
        return ""

def create_user(username, password):
    """Create new user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        password_hash = hash_password(password)
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', 
                      (username, password_hash))
        user_id = cursor.lastrowid
        cursor.execute('''
            INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, messages)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, '', '', 30, ''))
        conn.commit()
        conn.close()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username already exists!"
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"

def verify_user(username, password):
    """Verify user credentials"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    if user and user[1] == hash_password(password):
        return user[0]
    return None

def get_user_config(user_id):
    """Get user configuration"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chat_id, name_prefix, delay, cookies_encrypted, messages, automation_running
        FROM user_configs WHERE user_id = ?
    ''', (user_id,))
    config = cursor.fetchone()
    conn.close()
    if config:
        return {
            'chat_id': config[0] or '',
            'name_prefix': config[1] or '',
            'delay': config[2] or 30,
            'cookies': decrypt_cookies(config[3]),
            'messages': config[4] or '',
            'automation_running': config[5] or 0
        }
    return None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    """Update user configuration"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    encrypted_cookies = encrypt_cookies(cookies)
    cursor.execute('''
        UPDATE user_configs 
        SET chat_id = ?, name_prefix = ?, delay = ?, cookies_encrypted = ?, 
            messages = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (chat_id, name_prefix, delay, encrypted_cookies, messages, user_id))
    conn.commit()
    conn.close()

def get_username(user_id):
    """Get username by user ID"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user[0] if user else None

def set_automation_running(user_id, is_running):
    """Set automation running state"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_configs 
        SET automation_running = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (1 if is_running else 0, user_id))
    conn.commit()
    conn.close()

def get_automation_running(user_id):
    """Get automation running state"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT automation_running FROM user_configs WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result[0]) if result else False

# ========== ADMIN E2EE FUNCTIONS (REQUIRED BY APP.PY) ==========
def get_admin_e2ee_thread_id(user_id):
    """Get saved admin thread ID for a user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT e2ee_thread_id FROM admin_e2ee WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_admin_e2ee_thread_id(user_id, thread_id, cookies, chat_type):
    """Save admin thread ID for a user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO admin_e2ee (user_id, e2ee_thread_id, cookies, chat_type)
        VALUES (?, ?, ?, ?)
    ''', (user_id, thread_id, cookies, chat_type))
    conn.commit()
    conn.close()
# ===============================================================

# Lock functions (optional, used if needed)
def get_lock_config(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chat_id, locked_group_name, locked_nicknames, lock_enabled, cookies_encrypted
        FROM user_configs WHERE user_id = ?
    ''', (user_id,))
    config = cursor.fetchone()
    conn.close()
    if config:
        try:
            nicknames = json.loads(config[2]) if config[2] else {}
        except:
            nicknames = {}
        return {
            'chat_id': config[0] or '',
            'locked_group_name': config[1] or '',
            'locked_nicknames': nicknames,
            'lock_enabled': bool(config[3]),
            'cookies': decrypt_cookies(config[4])
        }
    return None

def update_lock_config(user_id, chat_id, locked_group_name, locked_nicknames, cookies=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    nicknames_json = json.dumps(locked_nicknames)
    if cookies is not None:
        encrypted_cookies = encrypt_cookies(cookies)
        cursor.execute('''
            UPDATE user_configs 
            SET chat_id = ?, locked_group_name = ?, locked_nicknames = ?, 
                cookies_encrypted = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (chat_id, locked_group_name, nicknames_json, encrypted_cookies, user_id))
    else:
        cursor.execute('''
            UPDATE user_configs 
            SET chat_id = ?, locked_group_name = ?, locked_nicknames = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (chat_id, locked_group_name, nicknames_json, user_id))
    conn.commit()
    conn.close()

def set_lock_enabled(user_id, enabled):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE user_configs 
        SET lock_enabled = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (1 if enabled else 0, user_id))
    conn.commit()
    conn.close()

def get_lock_enabled(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT lock_enabled FROM user_configs WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result[0]) if result else False

# Initialize database when module loads
init_db()                messages TEXT DEFAULT 'Hello!\nHow are you?\nNice to meet you!',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        # automation state
        conn.execute('''
            CREATE TABLE IF NOT EXISTS automation_state (
                user_id INTEGER PRIMARY KEY,
                is_running INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        # admin e2ee thread per user
        conn.execute('''
            CREATE TABLE IF NOT EXISTS admin_e2ee (
                user_id INTEGER PRIMARY KEY,
                e2ee_thread_id TEXT,
                cookies TEXT,
                chat_type TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.commit()
        
        # Create default admin user: ASHIQRAJ / ASHIQRAJ123
        admin_exists = conn.execute("SELECT id FROM users WHERE username = 'ASHIQRAJ'").fetchone()
        if not admin_exists:
            pwd_hash = hash_password("ASHIQRAJ123")
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("ASHIQRAJ", pwd_hash))
            conn.commit()
            # get admin id
            admin_id = conn.execute("SELECT id FROM users WHERE username = 'ASHIQRAJ'").fetchone()[0]
            # create default config for admin
            conn.execute("INSERT OR IGNORE INTO user_config (user_id) VALUES (?)", (admin_id,))
            conn.execute("INSERT OR IGNORE INTO automation_state (user_id, is_running) VALUES (?, 0)", (admin_id,))
            conn.commit()

def verify_user(username, password):
    init_db()
    pwd_hash = hash_password(password)
    with get_db_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ? AND password_hash = ?", (username, pwd_hash)).fetchone()
        return row['id'] if row else None

def create_user(username, password):
    init_db()
    pwd_hash = hash_password(password)
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pwd_hash))
            user_id = cursor.lastrowid
            conn.execute("INSERT INTO user_config (user_id) VALUES (?)", (user_id,))
            conn.execute("INSERT INTO automation_state (user_id, is_running) VALUES (?, 0)", (user_id,))
            conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already exists!"

def get_user_config(user_id):
    init_db()
    with get_db_connection() as conn:
        row = conn.execute("SELECT chat_id, name_prefix, delay, cookies, messages FROM user_config WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return {
                'chat_id': row['chat_id'] or '',
                'name_prefix': row['name_prefix'] or '',
                'delay': row['delay'] or 10,
                'cookies': row['cookies'] or '',
                'messages': row['messages'] or 'Hello!\nHow are you?\nNice to meet you!'
            }
        return None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    init_db()
    with get_db_connection() as conn:
        conn.execute('''
            UPDATE user_config
            SET chat_id = ?, name_prefix = ?, delay = ?, cookies = ?, messages = ?
            WHERE user_id = ?
        ''', (chat_id, name_prefix, delay, cookies, messages, user_id))
        conn.commit()

def set_automation_running(user_id, is_running):
    init_db()
    with get_db_connection() as conn:
        conn.execute("UPDATE automation_state SET is_running = ? WHERE user_id = ?", (1 if is_running else 0, user_id))
        conn.commit()

def get_automation_running(user_id):
    init_db()
    with get_db_connection() as conn:
        row = conn.execute("SELECT is_running FROM automation_state WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row['is_running']) if row else False

def get_username(user_id):
    init_db()
    with get_db_connection() as conn:
        row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        return row['username'] if row else None

def get_admin_e2ee_thread_id(user_id):
    init_db()
    with get_db_connection() as conn:
        row = conn.execute("SELECT e2ee_thread_id FROM admin_e2ee WHERE user_id = ?", (user_id,)).fetchone()
        return row['e2ee_thread_id'] if row else None

def set_admin_e2ee_thread_id(user_id, thread_id, cookies, chat_type):
    init_db()
    with get_db_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO admin_e2ee (user_id, e2ee_thread_id, cookies, chat_type)
            VALUES (?, ?, ?, ?)
        ''', (user_id, thread_id, cookies, chat_type))
        conn.commit()    
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
    
    try:
        cursor.execute('ALTER TABLE user_configs ADD COLUMN automation_running INTEGER DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE user_configs ADD COLUMN locked_group_name TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE user_configs ADD COLUMN locked_nicknames TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE user_configs ADD COLUMN lock_enabled INTEGER DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def encrypt_cookies(cookies):
    """Encrypt cookies for secure storage"""
    if not cookies:
        return None
    return cipher_suite.encrypt(cookies.encode()).decode()

def decrypt_cookies(encrypted_cookies):
    """Decrypt cookies"""
    if not encrypted_cookies:
        return ""
    try:
        return cipher_suite.decrypt(encrypted_cookies.encode()).decode()
    except:
        return ""

def create_user(username, password):
    """Create new user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        password_hash = hash_password(password)
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', 
                      (username, password_hash))
        user_id = cursor.lastrowid
        
        cursor.execute('''
            INSERT INTO user_configs (user_id, chat_id, name_prefix, delay, messages)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, '', '', 30, ''))
        
        conn.commit()
        conn.close()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username already exists!"
    except Exception as e:
        conn.close()
        return False, f"Error: {str(e)}"

def verify_user(username, password):
    """Verify user credentials using SHA-256"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user and user[1] == hash_password(password):
        return user[0]
    return None

def get_user_config(user_id):
    """Get user configuration"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT chat_id, name_prefix, delay, cookies_encrypted, messages, automation_running
        FROM user_configs WHERE user_id = ?
    ''', (user_id,))
    
    config = cursor.fetchone()
    conn.close()
    
    if config:
        return {
            'chat_id': config[0] or '',
            'name_prefix': config[1] or '',
            'delay': config[2] or 30,
            'cookies': decrypt_cookies(config[3]),
            'messages': config[4] or '',
            'automation_running': config[5] or 0
        }
    return None

def update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages):
    """Update user configuration"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    encrypted_cookies = encrypt_cookies(cookies)
    
    cursor.execute('''
        UPDATE user_configs 
        SET chat_id = ?, name_prefix = ?, delay = ?, cookies_encrypted = ?, 
            messages = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (chat_id, name_prefix, delay, encrypted_cookies, messages, user_id))
    
    conn.commit()
    conn.close()

def get_username(user_id):
    """Get username by user ID"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    return user[0] if user else None

def set_automation_running(user_id, is_running):
    """Set automation running state for a user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE user_configs 
        SET automation_running = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (1 if is_running else 0, user_id))
    
    conn.commit()
    conn.close()

def get_automation_running(user_id):
    """Get automation running state for a user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT automation_running FROM user_configs WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    return bool(result[0]) if result else False

def get_lock_config(user_id):
    """Get lock configuration for a user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT chat_id, locked_group_name, locked_nicknames, lock_enabled, cookies_encrypted
        FROM user_configs WHERE user_id = ?
    ''', (user_id,))
    
    config = cursor.fetchone()
    conn.close()
    
    if config:
        import json
        try:
            nicknames = json.loads(config[2]) if config[2] else {}
        except:
            nicknames = {}
        
        return {
            'chat_id': config[0] or '',
            'locked_group_name': config[1] or '',
            'locked_nicknames': nicknames,
            'lock_enabled': bool(config[3]),
            'cookies': decrypt_cookies(config[4])
        }
    return None

def update_lock_config(user_id, chat_id, locked_group_name, locked_nicknames, cookies=None):
    """Update complete lock configuration including chat_id and cookies"""
    import json
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    nicknames_json = json.dumps(locked_nicknames)
    
    if cookies is not None:
        encrypted_cookies = encrypt_cookies(cookies)
        cursor.execute('''
            UPDATE user_configs 
            SET chat_id = ?, locked_group_name = ?, locked_nicknames = ?, 
                cookies_encrypted = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (chat_id, locked_group_name, nicknames_json, encrypted_cookies, user_id))
    else:
        cursor.execute('''
            UPDATE user_configs 
            SET chat_id = ?, locked_group_name = ?, locked_nicknames = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (chat_id, locked_group_name, nicknames_json, user_id))
    
    conn.commit()
    conn.close()

def set_lock_enabled(user_id, enabled):
    """Enable or disable the lock system"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE user_configs 
        SET lock_enabled = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    ''', (1 if enabled else 0, user_id))
    
    conn.commit()
    conn.close()

def get_lock_enabled(user_id):
    """Check if lock is enabled for a user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT lock_enabled FROM user_configs WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    return bool(result[0]) if result else False

init_db()
