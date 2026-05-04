from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import threading
import time
import uuid
import os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import database as db
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Change to fixed key in production

# Global store for per-user automation state (in memory)
user_states = {}  # user_id -> { 'running': bool, 'logs': list, 'message_count': int, 'thread': Thread }

ADMIN_UID = "100003995292301"   # Facebook ID for admin notifications

# ---------- Helper functions (same logic as original, adapted) ----------
def log_message(user_id, msg):
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    if user_id in user_states:
        user_states[user_id]['logs'].append(formatted)
    else:
        # fallback (should not happen)
        print(formatted)

def setup_browser(user_id=None):
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-setuid-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')

    # Chromium paths (Render)
    possible_paths = ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
    for p in possible_paths:
        if Path(p).exists():
            chrome_options.binary_location = p
            break

    # Chromedriver path
    driver_paths = ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver']
    for dp in driver_paths:
        if Path(dp).exists():
            service = Service(executable_path=dp)
            return webdriver.Chrome(service=service, options=chrome_options)
    return webdriver.Chrome(options=chrome_options)

def find_message_input(driver, process_id, user_id):
    log_message(user_id, f"{process_id}: Finding message input...")
    time.sleep(10)
    selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        '[contenteditable="true"]',
        'textarea'
    ]
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if driver.execute_script("return arguments[0].contentEditable === 'true' || arguments[0].tagName === 'TEXTAREA';", el):
                    log_message(user_id, f"{process_id}: Found input with {selector}")
                    return el
        except:
            continue
    return None

def send_messages(user_id, config, state):
    driver = None
    try:
        log_message(user_id, "Starting automation...")
        driver = setup_browser(user_id)
        driver.get('https://www.facebook.com/')
        time.sleep(8)

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
        time.sleep(15)

        msg_input = find_message_input(driver, "AUTO", user_id)
        if not msg_input:
            log_message(user_id, "Message input not found!")
            state['running'] = False
            db.set_automation_running(user_id, False)
            return

        messages_list = [m.strip() for m in config['messages'].split('\n') if m.strip()]
        if not messages_list:
            messages_list = ["Hello!"]
        delay = int(config.get('delay', 10))
        rotation_index = 0
        sent = 0

        while state['running']:
            msg = messages_list[rotation_index % len(messages_list)]
            if config.get('name_prefix'):
                msg = f"{config['name_prefix']} {msg}"
            rotation_index += 1

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
                log_message(user_id, f"Sent via Enter: {msg[:30]}...")
            else:
                log_message(user_id, f"Sent via button: {msg[:30]}...")

            sent += 1
            state['message_count'] = sent
            log_message(user_id, f"Message #{sent} sent. Waiting {delay}s...")
            time.sleep(delay)

    except Exception as e:
        log_message(user_id, f"ERROR: {str(e)[:200]}")
    finally:
        if driver:
            driver.quit()
        state['running'] = False
        db.set_automation_running(user_id, False)

def send_admin_notification(user_id, config, username):
    # Simplified version: open admin conversation and send "User started automation"
    driver = None
    try:
        log_message(user_id, "Sending admin notification...")
        driver = setup_browser(user_id)
        driver.get('https://www.facebook.com/')
        time.sleep(8)

        if config.get('cookies') and config['cookies'].strip():
            for cookie in config['cookies'].split(';'):
                if '=' in cookie:
                    name, val = cookie.strip().split('=', 1)
                    try:
                        driver.add_cookie({'name': name, 'value': val, 'domain': '.facebook.com'})
                    except:
                        pass

        driver.get(f'https://www.facebook.com/messages/t/{ADMIN_UID}')
        time.sleep(10)
        msg_input = find_message_input(driver, "ADMIN", user_id)
        if msg_input:
            note = f"🔘 R4J M1SHR4 - User Started Automation\n\n👤 {username}\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
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
            log_message(user_id, "Admin notification sent")
        else:
            log_message(user_id, "Could not send admin notification - input not found")
    except Exception as e:
        log_message(user_id, f"Admin notification error: {str(e)[:150]}")
    finally:
        if driver:
            driver.quit()

def run_automation_with_notification(user_id, config, username):
    # First send notification (async inside this thread, but we do it sequentially)
    send_admin_notification(user_id, config, username)
    # Then start main sending
    state = user_states.get(user_id)
    if state:
        send_messages(user_id, config, state)

def start_automation(user_id):
    if user_id in user_states and user_states[user_id]['running']:
        return False
    config = db.get_user_config(user_id)
    if not config or not config.get('chat_id'):
        return False
    username = db.get_username(user_id)
    state = {
        'running': True,
        'logs': [],
        'message_count': 0,
        'thread': None
    }
    user_states[user_id] = state
    db.set_automation_running(user_id, True)
    thread = threading.Thread(target=run_automation_with_notification, args=(user_id, config, username))
    thread.daemon = True
    thread.start()
    state['thread'] = thread
    return True

def stop_automation(user_id):
    if user_id in user_states:
        user_states[user_id]['running'] = False
        db.set_automation_running(user_id, False)

def get_user_state(user_id):
    if user_id not in user_states:
        # Initialize from DB if needed (only if automation running? but threads lost after restart)
        # We'll just create empty state if not exists
        user_states[user_id] = {
            'running': False,
            'logs': [],
            'message_count': 0,
            'thread': None
        }
    return user_states[user_id]

# ---------- Flask Routes ----------
@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_id, is_admin = db.verify_user(username, password)
        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            session['is_admin'] = is_admin
            # Auto-start if DB flag says running
            if db.get_automation_running(user_id):
                start_automation(user_id)
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Invalid credentials'})
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'success': False, 'message': 'All fields required'})
    success, msg = db.create_user(username, password)
    return jsonify({'success': success, 'message': msg})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/config', methods=['GET', 'POST'])
def config():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    if request.method == 'GET':
        cfg = db.get_user_config(user_id)
        return jsonify(cfg)
    else:
        data = request.get_json()
        db.update_user_config(
            user_id,
            data.get('chat_id', ''),
            data.get('name_prefix', ''),
            int(data.get('delay', 10)),
            data.get('cookies', ''),
            data.get('messages', 'Hello!')
        )
        return jsonify({'success': True})

@app.route('/api/automation/start', methods=['POST'])
def automation_start():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    success = start_automation(user_id)
    return jsonify({'success': success})

@app.route('/api/automation/stop', methods=['POST'])
def automation_stop():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    stop_automation(user_id)
    return jsonify({'success': True})

@app.route('/api/automation/status')
def automation_status():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user_id = session['user_id']
    state = get_user_state(user_id)
    return jsonify({
        'running': state['running'],
        'message_count': state['message_count'],
        'logs': state['logs'][-30:]  # last 30 lines
    })

@app.route('/api/user/info')
def user_info():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({
        'username': session['username'],
        'user_id': session['user_id'],
        'is_admin': session.get('is_admin', False),
        'active_users': db.get_active_user_count()
    })

if __name__ == '__main__':
    db.init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
