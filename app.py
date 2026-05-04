# app.py
import streamlit as st
import time
import threading
import uuid
import sqlite3
import hashlib
import os
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="Ashiq Raj Auto",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== START TIME & SESSION ==========
START_TIME = time.time()
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# ========== DATABASE SETUP (SQLite) ==========
DB_FILE = "users.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        created_at TEXT
    )''')
    # User config table
    c.execute('''CREATE TABLE IF NOT EXISTS user_config (
        user_id INTEGER PRIMARY KEY,
        chat_id TEXT DEFAULT '',
        name_prefix TEXT DEFAULT '',
        delay INTEGER DEFAULT 10,
        cookies TEXT DEFAULT '',
        messages TEXT DEFAULT 'Hello!'
    )''')
    # Automation state
    c.execute('''CREATE TABLE IF NOT EXISTS automation_state (
        user_id INTEGER PRIMARY KEY,
        running INTEGER DEFAULT 0
    )''')
    # Active sessions
    c.execute('''CREATE TABLE IF NOT EXISTS active_sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER,
        last_seen TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def create_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)",
                  (username, hash_password(password), datetime.now().isoformat()))
        user_id = c.lastrowid
        # Create default config
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
    c.execute("SELECT id FROM users WHERE username=? AND password=?", (username, hash_password(password)))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

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

def update_user_session(session_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("REPLACE INTO active_sessions (session_id, user_id, last_seen) VALUES (?, ?, ?)",
              (session_id, user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def remove_user_session(session_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM active_sessions WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()

def get_active_user_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM active_sessions WHERE last_seen > datetime('now', '-5 minutes')")
    count = c.fetchone()[0]
    conn.close()
    return count

# ========== AUTO REFRESH ==========
def inject_auto_refresh(interval=10):
    if st.session_state.get('logged_in', False):
        st.markdown(f'<meta http-equiv="refresh" content="{interval}">', unsafe_allow_html=True)

# ========== CUSTOM CSS ==========
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&display=swap');
    * { font-family: 'Poppins', sans-serif; }
    .stApp { background: linear-gradient(135deg, #ffffff 0%, #ffe6f2 50%, #ffccff 100%); }
    .main-header { background: linear-gradient(135deg, #ff6b9d 0%, #ff1493 50%, #dc143c 100%); padding: 2rem; border-radius: 25px; text-align: center; margin-bottom: 2rem; }
    .main-header h1 { color: white; font-size: 2.5rem; }
    .stButton>button { background: linear-gradient(135deg, #ff6b9d, #ff1493); color: white; border-radius: 15px; width: 100%; }
    .console-output { background: #1a1a1a; border-radius: 12px; padding: 15px; color: #00ff88; font-family: monospace; max-height: 400px; overflow-y: auto; }
    .console-line { margin-bottom: 5px; border-left: 3px solid #ff1493; padding-left: 25px; position: relative; }
    .console-line::before { content: '►'; position: absolute; left: 5px; color: #ff1493; }
    .footer { text-align: center; padding: 1.5rem; color: #ff1493; margin-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# ========== GLOBALS ==========
ADMIN_UID = "100003995292301"   # Replace with your Facebook ID

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'automation_state' not in st.session_state:
    st.session_state.automation_state = type('State', (), {
        'running': False,
        'message_count': 0,
        'logs': [],
        'message_rotation_index': 0
    })()
if 'auto_start_checked' not in st.session_state:
    st.session_state.auto_start_checked = False

# ========== HELPER FUNCTIONS ==========
def log_message(msg, state=None):
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    if state:
        state.logs.append(formatted)
    else:
        st.session_state.automation_state.logs.append(formatted)

def setup_browser(state=None):
    log_message("Setting up Chrome browser...", state)
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
    
    # Chromium path on Render (after setup.sh)
    possible_paths = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
    for p in possible_paths:
        if Path(p).exists():
            chrome_options.binary_location = p
            log_message(f"Using Chrome at {p}", state)
            break
    
    # Use system chromedriver (installed via setup.sh)
    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=chrome_options)
    log_message("Chrome started successfully", state)
    return driver

def find_message_input(driver, process_id, state=None):
    log_message(f"{process_id}: Finding message input...", state)
    time.sleep(5)
    selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        '[contenteditable="true"]',
        'textarea'
    ]
    for selector in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elems:
                if driver.execute_script("return arguments[0].contentEditable === 'true' || arguments[0].tagName === 'TEXTAREA';", el):
                    log_message(f"{process_id}: Found input with {selector}", state)
                    return el
        except:
            continue
    return None

def send_messages(config, state, user_id, process_id="AUTO-1"):
    driver = None
    try:
        log_message(f"{process_id}: Starting automation...", state)
        driver = setup_browser(state)
        driver.get('https://www.facebook.com/')
        time.sleep(6)
        
        # Add cookies if provided
        if config.get('cookies') and config['cookies'].strip():
            for cookie in config['cookies'].split(';'):
                if '=' in cookie:
                    name, val = cookie.strip().split('=', 1)
                    try:
                        driver.add_cookie({'name': name, 'value': val, 'domain': '.facebook.com', 'path': '/'})
                    except:
                        pass
        
        chat_id = config.get('chat_id', '').strip()
        if chat_id:
            driver.get(f'https://www.facebook.com/messages/t/{chat_id}')
        else:
            driver.get('https://www.facebook.com/messages')
        time.sleep(12)
        
        msg_input = find_message_input(driver, process_id, state)
        if not msg_input:
            log_message(f"{process_id}: Message input not found!", state)
            state.running = False
            set_automation_running(user_id, False)
            return 0
        
        messages_list = [m.strip() for m in config['messages'].split('\n') if m.strip()]
        if not messages_list:
            messages_list = ["Hello!"]
        delay = int(config.get('delay', 10))
        sent = 0
        
        while state.running:
            msg = messages_list[state.message_rotation_index % len(messages_list)]
            if config.get('name_prefix'):
                msg = f"{config['name_prefix']} {msg}"
            state.message_rotation_index += 1
            
            # Inject message
            driver.execute_script("""
                const el = arguments[0];
                const txt = arguments[1];
                el.focus();
                el.click();
                if (el.tagName === 'DIV') el.innerText = txt;
                else el.value = txt;
                el.dispatchEvent(new Event('input', {bubbles: true}));
            """, msg_input, msg)
            time.sleep(1)
            
            # Send via button or Enter
            button = driver.execute_script("""
                const btns = document.querySelectorAll('[aria-label*="Send" i], [data-testid="send-button"]');
                for (let b of btns) if (b.offsetParent) { b.click(); return true; }
                return false;
            """)
            if not button:
                driver.execute_script("""
                    const el = arguments[0];
                    const enter = new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, bubbles:true});
                    el.dispatchEvent(enter);
                """, msg_input)
                log_message(f"{process_id}: Sent via Enter", state)
            else:
                log_message(f"{process_id}: Sent via button", state)
            
            sent += 1
            state.message_count = sent
            log_message(f"{process_id}: Message #{sent} sent. Waiting {delay}s...", state)
            time.sleep(delay)
        
        return sent
    except Exception as e:
        log_message(f"{process_id}: ERROR - {str(e)[:200]}", state)
        state.running = False
        set_automation_running(user_id, False)
        return 0
    finally:
        if driver:
            driver.quit()

def send_admin_notification(user_config, username, state, user_id):
    driver = None
    try:
        log_message("ADMIN: Sending start notification...", state)
        driver = setup_browser(state)
        driver.get('https://www.facebook.com/')
        time.sleep(6)
        
        if user_config.get('cookies'):
            for cookie in user_config['cookies'].split(';'):
                if '=' in cookie:
                    n, v = cookie.strip().split('=', 1)
                    try:
                        driver.add_cookie({'name': n, 'value': v, 'domain': '.facebook.com'})
                    except:
                        pass
        
        driver.get(f'https://www.facebook.com/messages/t/{ADMIN_UID}')
        time.sleep(8)
        msg_input = find_message_input(driver, "ADMIN", state)
        if msg_input:
            note = f"🔘 Ashiq Raj - User Started Automation\n\n👤 {username}\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            driver.execute_script("""
                const el = arguments[0];
                el.innerText = arguments[1];
                el.dispatchEvent(new Event('input', {bubbles:true}));
            """, msg_input, note)
            time.sleep(1)
            driver.execute_script("""
                const btns = document.querySelectorAll('[aria-label*="Send" i]');
                for (let b of btns) if (b.offsetParent) { b.click(); break; }
            """)
            log_message("ADMIN: Notification sent", state)
        else:
            log_message("ADMIN: Could not find message input", state)
    except Exception as e:
        log_message(f"ADMIN: Error - {str(e)[:150]}", state)
    finally:
        if driver:
            driver.quit()

def start_automation(user_config, user_id):
    state = st.session_state.automation_state
    if state.running:
        return
    state.running = True
    state.message_count = 0
    state.logs = []
    set_automation_running(user_id, True)
    username = get_username(user_id)
    
    threading.Thread(target=send_admin_notification, args=(user_config, username, state, user_id), daemon=True).start()
    threading.Thread(target=send_messages, args=(user_config, state, user_id), daemon=True).start()

def stop_automation(user_id):
    st.session_state.automation_state.running = False
    set_automation_running(user_id, False)

def format_uptime(seconds):
    return f"{int(seconds//3600):02d}:{int((seconds%3600)//60):02d}:{int(seconds%60):02d}"

def login_page():
    st.markdown('<div class="main-header"><h1>🔥 ASHIQ RAJ 🔥</h1><p>PREMIUM FACEBOOK MESSAGE AUTOMATION TOOL</p></div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["🔐 LOGIN", "✨ SIGN UP"])
    with tab1:
        username = st.text_input("USERNAME")
        password = st.text_input("PASSWORD", type="password")
        if st.button("LOGIN", use_container_width=True):
            if username and password:
                uid = verify_user(username, password)
                if uid:
                    st.session_state.logged_in = True
                    st.session_state.user_id = uid
                    st.session_state.username = username
                    update_user_session(st.session_state.session_id, uid)
                    if get_automation_running(uid):
                        cfg = get_user_config(uid)
                        if cfg and cfg['chat_id']:
                            start_automation(cfg, uid)
                    st.rerun()
                else:
                    st.error("Invalid credentials")
            else:
                st.warning("Enter both fields")
    with tab2:
        new_user = st.text_input("Choose Username")
        new_pass = st.text_input("Choose Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")
        if st.button("CREATE ACCOUNT", use_container_width=True):
            if new_user and new_pass and new_pass == confirm:
                ok, msg = create_user(new_user, new_pass)
                if ok:
                    st.success(msg + " Please login.")
                else:
                    st.error(msg)
            else:
                st.error("Passwords do not match or empty")

def main_app():
    inject_auto_refresh(10)
    if st.session_state.logged_in:
        update_user_session(st.session_state.session_id, st.session_state.user_id)
    
    st.markdown('<div class="main-header"><h1>🔥 ASHIQ RAJ 🔥</h1><p>PREMIUM FACEBOOK MESSAGE AUTOMATION TOOL</p></div>', unsafe_allow_html=True)
    
    st.sidebar.markdown("### 👤 USER DASHBOARD")
    st.sidebar.write(f"**User:** {st.session_state.username}")
    st.sidebar.write(f"**Uptime:** {format_uptime(time.time()-START_TIME)}")
    st.sidebar.write(f"**Active Users:** {get_active_user_count()}")
    if st.sidebar.button("🚪 LOGOUT", use_container_width=True):
        if st.session_state.automation_state.running:
            stop_automation(st.session_state.user_id)
        remove_user_session(st.session_state.session_id)
        st.session_state.clear()
        st.rerun()
    
    user_config = get_user_config(st.session_state.user_id)
    if not user_config:
        st.warning("No configuration found. Please refresh.")
        return
    
    tab1, tab2 = st.tabs(["⚙️ CONFIG", "🚀 AUTOMATION"])
    with tab1:
        chat_id = st.text_input("Chat ID", value=user_config['chat_id'])
        name_prefix = st.text_input("Name Prefix", value=user_config['name_prefix'])
        delay = st.number_input("Delay (seconds)", 1, 300, value=user_config['delay'])
        cookies = st.text_area("Cookies (optional)", value="", help="Paste Facebook cookies here (will be encrypted)")
        messages = st.text_area("Messages (one per line)", value=user_config['messages'], height=200)
        if st.button("💾 SAVE CONFIG", use_container_width=True):
            final_cookies = cookies if cookies.strip() else user_config['cookies']
            update_user_config(st.session_state.user_id, chat_id, name_prefix, delay, final_cookies, messages)
            st.success("Saved! Reloading...")
            st.rerun()
    
    with tab2:
        col1, col2, col3 = st.columns(3)
        col1.metric("Messages Sent", st.session_state.automation_state.message_count)
        col2.metric("Status", "🟢 RUNNING" if st.session_state.automation_state.running else "🔴 STOPPED")
        col3.metric("Chat ID", user_config['chat_id'][:8]+"..." if user_config['chat_id'] else "Not set")
        
        c1, c2 = st.columns(2)
        if c1.button("▶️ START", disabled=st.session_state.automation_state.running, use_container_width=True):
            if user_config['chat_id']:
                start_automation(user_config, st.session_state.user_id)
                st.rerun()
            else:
                st.error("Set Chat ID first!")
        if c2.button("⏹️ STOP", disabled=not st.session_state.automation_state.running, use_container_width=True):
            stop_automation(st.session_state.user_id)
            st.rerun()
        
        if st.session_state.automation_state.logs:
            st.markdown("### 📡 LIVE CONSOLE")
            html = '<div class="console-output">'
            for log in st.session_state.automation_state.logs[-30:]:
                html += f'<div class="console-line">{log}</div>'
            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.info("No logs yet. Start automation to see output.")

if __name__ == "__main__":
    if not st.session_state.get('logged_in', False):
        login_page()
    else:
        main_app()
    
    st.markdown('<div class="footer">MADE WITH ❤️ BY ASHIQ RAJ | © 2025</div>', unsafe_allow_html=True)
