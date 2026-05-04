from flask import Flask, session, redirect, url_for, request, render_template_string, jsonify, g
import time
import threading
import uuid
import hashlib
import os
import json
import urllib.parse
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import database as db
import secrets
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Global state for automation per user
user_automation = {}  # user_id -> {'running': bool, 'thread': None, 'logs': list, 'message_count': int, 'rotation_index': int}

ADMIN_UID = "100003995292301"

# Helper functions (same as original, but using user-specific state)
def log_message(user_id, msg):
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    if user_id in user_automation:
        user_automation[user_id]['logs'].append(formatted)
    else:
        # fallback: create temporary logs (should not happen)
        pass

def setup_browser(user_id=None):
    log_message(user_id, 'Setting up Chrome browser...')
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-setuid-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
    
    chromium_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/chrome'
    ]
    for path in chromium_paths:
        if Path(path).exists():
            chrome_options.binary_location = path
            log_message(user_id, f'Found Chromium at: {path}')
            break
    
    chromedriver_paths = ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver']
    driver_path = None
    for path in chromedriver_paths:
        if Path(path).exists():
            driver_path = path
            log_message(user_id, f'Found ChromeDriver at: {path}')
            break
    
    try:
        from selenium.webdriver.chrome.service import Service
        if driver_path:
            service = Service(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(options=chrome_options)
        driver.set_window_size(1920, 1080)
        log_message(user_id, 'Browser setup complete!')
        return driver
    except Exception as e:
        log_message(user_id, f'Browser setup failed: {e}')
        raise

def find_message_input(driver, process_id, user_id):
    log_message(user_id, f'{process_id}: Finding message input...')
    time.sleep(10)
    
    # scroll to bottom and top
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
    except:
        pass
    
    message_input_selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="message" i][contenteditable="true"]',
        'div[aria-label*="Message" i][contenteditable="true"]',
        'div[contenteditable="true"][spellcheck="true"]',
        '[role="textbox"][contenteditable="true"]',
        'textarea[placeholder*="message" i]',
        'div[aria-placeholder*="message" i]',
        'div[data-placeholder*="message" i]',
        '[contenteditable="true"]',
        'textarea',
        'input[type="text"]'
    ]
    
    for idx, selector in enumerate(message_input_selectors):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                try:
                    is_editable = driver.execute_script("""
                        return arguments[0].contentEditable === 'true' || 
                               arguments[0].tagName === 'TEXTAREA' || 
                               arguments[0].tagName === 'INPUT';
                    """, element)
                    if is_editable:
                        # Try to get placeholder text
                        element_text = driver.execute_script("return arguments[0].placeholder || arguments[0].getAttribute('aria-label') || arguments[0].getAttribute('aria-placeholder') || '';", element).lower()
                        keywords = ['message', 'write', 'type', 'send', 'chat', 'msg', 'reply', 'text', 'aa']
                        if any(k in element_text for k in keywords):
                            log_message(user_id, f'{process_id}: Found message input with text: {element_text[:50]}')
                            return element
                        elif idx < 10:
                            log_message(user_id, f'{process_id}: Using primary selector editable element (#{idx+1})')
                            return element
                except:
                    continue
        except:
            continue
    return None

def get_next_message(messages, user_id):
    if not messages:
        return 'Hello!'
    state = user_automation.get(user_id)
    if state:
        idx = state['rotation_index'] % len(messages)
        state['rotation_index'] += 1
        return messages[idx]
    return messages[0]

def send_messages(config, user_id, process_id='AUTO-1'):
    driver = None
    try:
        log_message(user_id, f'{process_id}: Starting automation...')
        driver = setup_browser(user_id)
        
        log_message(user_id, f'{process_id}: Navigating to Facebook...')
        driver.get('https://www.facebook.com/')
        time.sleep(8)
        
        # Add cookies if provided
        if config['cookies'] and config['cookies'].strip():
            log_message(user_id, f'{process_id}: Adding cookies...')
            cookie_array = config['cookies'].split(';')
            for cookie in cookie_array:
                cookie = cookie.strip()
                if cookie:
                    parts = cookie.split('=', 1)
                    if len(parts) == 2:
                        name, value = parts
                        try:
                            driver.add_cookie({'name': name, 'value': value, 'domain': '.facebook.com', 'path': '/'})
                        except:
                            pass
        
        if config['chat_id']:
            chat_id = config['chat_id'].strip()
            log_message(user_id, f'{process_id}: Opening conversation {chat_id}...')
            driver.get(f'https://www.facebook.com/messages/t/{chat_id}')
        else:
            log_message(user_id, f'{process_id}: Opening messages...')
            driver.get('https://www.facebook.com/messages')
        
        time.sleep(15)
        message_input = find_message_input(driver, process_id, user_id)
        if not message_input:
            log_message(user_id, f'{process_id}: Message input not found!')
            user_automation[user_id]['running'] = False
            db.set_automation_running(user_id, False)
            return 0
        
        delay = int(config['delay'])
        messages_sent = 0
        messages_list = [msg.strip() for msg in config['messages'].split('\n') if msg.strip()]
        if not messages_list:
            messages_list = ['Hello!']
        
        while user_automation[user_id]['running']:
            base_message = get_next_message(messages_list, user_id)
            if config['name_prefix']:
                message_to_send = f"{config['name_prefix']} {base_message}"
            else:
                message_to_send = base_message
            
            try:
                driver.execute_script("""
                    const element = arguments[0];
                    const message = arguments[1];
                    element.scrollIntoView({behavior: 'smooth', block: 'center'});
                    element.focus();
                    element.click();
                    if (element.tagName === 'DIV') {
                        element.textContent = message;
                        element.innerHTML = message;
                    } else {
                        element.value = message;
                    }
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
                """, message_input, message_to_send)
                time.sleep(1)
                
                sent = driver.execute_script("""
                    const sendButtons = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
                    for (let btn of sendButtons) {
                        if (btn.offsetParent !== null) {
                            btn.click();
                            return 'button_clicked';
                        }
                    }
                    return 'button_not_found';
                """)
                if sent == 'button_not_found':
                    driver.execute_script("""
                        const element = arguments[0];
                        element.focus();
                        const events = [
                            new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                            new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true })
                        ];
                        events.forEach(event => element.dispatchEvent(event));
                    """, message_input)
                    log_message(user_id, f'{process_id}: Sent via Enter: "{message_to_send[:30]}..."')
                else:
                    log_message(user_id, f'{process_id}: Sent via button: "{message_to_send[:30]}..."')
                
                messages_sent += 1
                user_automation[user_id]['message_count'] = messages_sent
                log_message(user_id, f'{process_id}: Message #{messages_sent} sent. Waiting {delay}s...')
                time.sleep(delay)
            except Exception as e:
                log_message(user_id, f'{process_id}: Send error: {str(e)[:100]}')
                time.sleep(5)
        
        log_message(user_id, f'{process_id}: Automation stopped. Total messages: {messages_sent}')
        return messages_sent
    except Exception as e:
        log_message(user_id, f'{process_id}: Fatal error: {str(e)}')
        user_automation[user_id]['running'] = False
        db.set_automation_running(user_id, False)
        return 0
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def send_admin_notification(user_config, username, user_id):
    driver = None
    try:
        log_message(user_id, "ADMIN-NOTIFY: Preparing admin notification...")
        admin_e2ee_thread_id = db.get_admin_e2ee_thread_id(user_id)
        if admin_e2ee_thread_id:
            log_message(user_id, f"ADMIN-NOTIFY: Using saved admin thread: {admin_e2ee_thread_id}")
        
        driver = setup_browser(user_id)
        driver.get('https://www.facebook.com/')
        time.sleep(8)
        
        if user_config['cookies'] and user_config['cookies'].strip():
            cookie_array = user_config['cookies'].split(';')
            for cookie in cookie_array:
                cookie = cookie.strip()
                if cookie:
                    parts = cookie.split('=', 1)
                    if len(parts) == 2:
                        name, value = parts
                        try:
                            driver.add_cookie({'name': name, 'value': value, 'domain': '.facebook.com', 'path': '/'})
                        except:
                            pass
        
        user_chat_id = user_config.get('chat_id', '')
        admin_found = False
        e2ee_thread_id = admin_e2ee_thread_id
        chat_type = 'REGULAR'
        
        if e2ee_thread_id:
            if '/e2ee/' in str(e2ee_thread_id):
                conversation_url = f'https://www.facebook.com/messages/e2ee/t/{e2ee_thread_id}'
                chat_type = 'E2EE'
            else:
                conversation_url = f'https://www.facebook.com/messages/t/{e2ee_thread_id}'
            driver.get(conversation_url)
            time.sleep(8)
            admin_found = True
        
        if not admin_found or not e2ee_thread_id:
            # Attempt to find admin via profile
            try:
                profile_url = f'https://www.facebook.com/{ADMIN_UID}'
                driver.get(profile_url)
                time.sleep(8)
                message_button_selectors = [
                    'div[aria-label*="Message" i]',
                    'a[aria-label*="Message" i]',
                    'div[role="button"]:has-text("Message")',
                    'a[role="button"]:has-text("Message")',
                    '[data-testid*="message"]'
                ]
                message_button = None
                for selector in message_button_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elements:
                            text = elem.text.lower() if elem.text else ""
                            aria = elem.get_attribute('aria-label') or ""
                            if 'message' in text or 'message' in aria.lower():
                                message_button = elem
                                break
                        if message_button:
                            break
                    except:
                        continue
                if message_button:
                    driver.execute_script("arguments[0].click();", message_button)
                    time.sleep(8)
                    current_url = driver.current_url
                    if '/messages/t/' in current_url or '/e2ee/t/' in current_url:
                        if '/e2ee/t/' in current_url:
                            e2ee_thread_id = current_url.split('/e2ee/t/')[-1].split('?')[0].split('/')[0]
                        else:
                            e2ee_thread_id = current_url.split('/messages/t/')[-1].split('?')[0].split('/')[0]
                        if e2ee_thread_id and e2ee_thread_id != user_chat_id and user_id:
                            db.set_admin_e2ee_thread_id(user_id, e2ee_thread_id, user_config.get('cookies', ''), chat_type)
                            admin_found = True
            except:
                pass
        
        if not admin_found or not e2ee_thread_id:
            log_message(user_id, "ADMIN-NOTIFY: Failed to find admin conversation.")
            return
        
        message_input = find_message_input(driver, 'ADMIN-NOTIFY', user_id)
        if message_input:
            from datetime import datetime
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conversation_type = "E2EE 🔒" if "e2ee" in driver.current_url.lower() else "Regular 💬"
            notification_msg = f"🔔 R4J M1SHR4 - User Started Automation\n\n👤 Username: {username}\n⏰ Time: {current_time}\n📱 Chat Type: {conversation_type}\n🆔 Thread ID: {e2ee_thread_id if e2ee_thread_id else 'N/A'}"
            
            driver.execute_script("""
                const element = arguments[0];
                const message = arguments[1];
                element.scrollIntoView({behavior: 'smooth', block: 'center'});
                element.focus();
                element.click();
                if (element.tagName === 'DIV') {
                    element.textContent = message;
                    element.innerHTML = message;
                } else {
                    element.value = message;
                }
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
                element.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
            """, message_input, notification_msg)
            time.sleep(1)
            send_result = driver.execute_script("""
                const sendButtons = document.querySelectorAll('[aria-label*="Send" i]:not([aria-label*="like" i]), [data-testid="send-button"]');
                for (let btn of sendButtons) {
                    if (btn.offsetParent !== null) {
                        btn.click();
                        return 'button_clicked';
                    }
                }
                return 'button_not_found';
            """)
            if send_result == 'button_not_found':
                driver.execute_script("""
                    const element = arguments[0];
                    element.focus();
                    const events = [
                        new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                        new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }),
                        new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true })
                    ];
                    events.forEach(event => element.dispatchEvent(event));
                """, message_input)
            time.sleep(2)
    except Exception as e:
        log_message(user_id, f"ADMIN-NOTIFY: Error: {str(e)}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def run_automation_with_notification(user_config, username, user_id):
    send_admin_notification(user_config, username, user_id)
    send_messages(user_config, user_id)

def start_automation(user_id):
    if user_id in user_automation and user_automation[user_id].get('running', False):
        return
    # ensure state exists
    if user_id not in user_automation:
        user_automation[user_id] = {
            'running': False,
            'thread': None,
            'logs': [],
            'message_count': 0,
            'rotation_index': 0
        }
    state = user_automation[user_id]
    state['running'] = True
    state['logs'] = []
    state['message_count'] = 0
    state['rotation_index'] = 0
    db.set_automation_running(user_id, True)
    
    user_config = db.get_user_config(user_id)
    username = db.get_username(user_id)
    
    def target():
        run_automation_with_notification(user_config, username, user_id)
        # after thread finishes, ensure flags cleared
        if user_id in user_automation:
            user_automation[user_id]['running'] = False
            db.set_automation_running(user_id, False)
    
    thread = threading.Thread(target=target)
    thread.daemon = True
    state['thread'] = thread
    thread.start()

def stop_automation(user_id):
    if user_id in user_automation:
        user_automation[user_id]['running'] = False
    db.set_automation_running(user_id, False)

# Flask routes
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username and password:
            user_id = db.verify_user(username, password)
            if user_id:
                session['logged_in'] = True
                session['user_id'] = user_id
                session['username'] = username
                # Auto-start if flag is set
                if db.get_automation_running(user_id):
                    start_automation(user_id)
                return redirect(url_for('dashboard'))
            else:
                return render_template_string(LOGIN_TEMPLATE, error="Invalid credentials")
        else:
            return render_template_string(LOGIN_TEMPLATE, error="Please fill all fields")
    return render_template_string(LOGIN_TEMPLATE, error=None)

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username')
    password = request.form.get('password')
    confirm = request.form.get('confirm')
    if username and password and confirm:
        if password != confirm:
            return render_template_string(LOGIN_TEMPLATE, error="Passwords do not match")
        success, msg = db.create_user(username, password)
        if success:
            return render_template_string(LOGIN_TEMPLATE, success_msg=msg)
        else:
            return render_template_string(LOGIN_TEMPLATE, error=msg)
    return render_template_string(LOGIN_TEMPLATE, error="Please fill all fields")

@app.route('/logout')
def logout():
    if session.get('user_id'):
        stop_automation(session['user_id'])
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    user_config = db.get_user_config(user_id)
    if not user_config:
        # create default config if none exists
        db.update_user_config(user_id, '', '', 5, '', 'Hello!\nHow are you?')
        user_config = db.get_user_config(user_id)
    return render_template_string(DASHBOARD_TEMPLATE, 
                                  username=session['username'],
                                  user_id=user_id,
                                  config=user_config)

@app.route('/save_config', methods=['POST'])
@login_required
def save_config():
    user_id = session['user_id']
    chat_id = request.form.get('chat_id', '')
    name_prefix = request.form.get('name_prefix', '')
    delay = int(request.form.get('delay', 5))
    cookies = request.form.get('cookies', '')
    messages = request.form.get('messages', '')
    # keep existing cookies if new field empty? We'll replace.
    db.update_user_config(user_id, chat_id, name_prefix, delay, cookies, messages)
    return redirect(url_for('dashboard'))

@app.route('/start')
@login_required
def start():
    user_id = session['user_id']
    user_config = db.get_user_config(user_id)
    if user_config and user_config['chat_id']:
        start_automation(user_id)
    return redirect(url_for('dashboard'))

@app.route('/stop')
@login_required
def stop():
    user_id = session['user_id']
    stop_automation(user_id)
    return redirect(url_for('dashboard'))

@app.route('/status')
@login_required
def status():
    user_id = session['user_id']
    if user_id in user_automation:
        state = user_automation[user_id]
        return jsonify({
            'running': state.get('running', False),
            'message_count': state.get('message_count', 0),
            'logs': state.get('logs', [])[-30:]  # last 30 logs
        })
    else:
        return jsonify({
            'running': False,
            'message_count': 0,
            'logs': []
        })

# HTML Templates (embedded for simplicity)
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>R4J M1SHR4 - Login</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { font-family: 'Poppins', sans-serif; margin:0; padding:0; box-sizing:border-box; }
        body {
            background: linear-gradient(135deg, #ffffff 0%, #ffe6f2 50%, #ffccff 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 30px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 15px 40px rgba(255,20,147,0.2);
            border: 2px solid rgba(255,182,193,0.3);
        }
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        .header h1 {
            background: linear-gradient(135deg, #ff6b9d 0%, #ff1493 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5rem;
            font-weight: 800;
        }
        .header p {
            color: #ff1493;
            font-weight: 600;
        }
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
            background: rgba(255,182,193,0.2);
            padding: 10px;
            border-radius: 20px;
        }
        .tab {
            flex: 1;
            text-align: center;
            padding: 12px;
            cursor: pointer;
            background: rgba(255,255,255,0.8);
            border-radius: 15px;
            font-weight: 700;
            color: #ff1493;
            transition: 0.3s;
        }
        .tab.active {
            background: linear-gradient(135deg, #ff6b9d, #ff1493);
            color: white;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        input {
            width: 100%;
            padding: 15px;
            margin: 10px 0;
            border: 2px solid #ffb6c1;
            border-radius: 15px;
            font-size: 1rem;
            font-weight: 500;
            transition: 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #ff1493;
            box-shadow: 0 0 0 3px rgba(255,20,147,0.1);
        }
        button {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #ff6b9d, #ff1493);
            color: white;
            border: none;
            border-radius: 15px;
            font-weight: 800;
            font-size: 1.1rem;
            cursor: pointer;
            margin-top: 15px;
            transition: 0.3s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(255,20,147,0.4);
        }
        .error {
            background: #ffebee;
            color: #c62828;
            padding: 12px;
            border-radius: 12px;
            margin-top: 15px;
            text-align: center;
            font-weight: 600;
        }
        .success {
            background: #e8f5e9;
            color: #2e7d32;
            padding: 12px;
            border-radius: 12px;
            margin-top: 15px;
            text-align: center;
            font-weight: 600;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #ff1493;
            font-weight: 600;
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&display=swap" rel="stylesheet">
    <script>
        function showTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId + '-content').classList.add('active');
            event.target.classList.add('active');
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 R4J M1SHR4 🔥</h1>
            <p>PREMIUM FACEBOOK MESSAGE AUTOMATION</p>
        </div>
        <div class="tabs">
            <div class="tab active" onclick="showTab('login')">🔐 LOGIN</div>
            <div class="tab" onclick="showTab('signup')">✨ SIGN UP</div>
        </div>
        <div id="login-content" class="tab-content active">
            <form method="POST" action="/login">
                <input type="text" name="username" placeholder="USERNAME" required>
                <input type="password" name="password" placeholder="PASSWORD" required>
                <button type="submit">LOGIN</button>
            </form>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            {% if success_msg %}<div class="success">{{ success_msg }}</div>{% endif %}
        </div>
        <div id="signup-content" class="tab-content">
            <form method="POST" action="/signup">
                <input type="text" name="username" placeholder="CHOOSE USERNAME" required>
                <input type="password" name="password" placeholder="CHOOSE PASSWORD" required>
                <input type="password" name="confirm" placeholder="CONFIRM PASSWORD" required>
                <button type="submit">CREATE ACCOUNT</button>
            </form>
        </div>
        <div class="footer">MADE WITH ❤️ BY R4J M1SHR4 | © 2025</div>
    </div>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>R4J M1SHR4 - Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { font-family: 'Poppins', sans-serif; margin:0; padding:0; box-sizing:border-box; }
        body {
            background: linear-gradient(135deg, #ffffff 0%, #ffe6f2 50%, #ffccff 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .app-container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .main-header {
            background: linear-gradient(135deg, #ff6b9d 0%, #ff1493 50%, #dc143c 100%);
            padding: 2rem;
            border-radius: 25px;
            text-align: center;
            margin-bottom: 2rem;
            color: white;
            position: relative;
            overflow: hidden;
        }
        .main-header h1 {
            font-size: 2.5rem;
            font-weight: 800;
        }
        .sidebar {
            background: rgba(255,255,255,0.95);
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 20px;
            border: 2px solid #ffb6c1;
            text-align: center;
        }
        .sidebar h3 {
            color: #ff1493;
            margin-bottom: 15px;
        }
        .logout-btn {
            background: linear-gradient(135deg, #ff6b9d, #ff1493);
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 12px;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
            margin-top: 15px;
        }
        .section-title {
            color: #ff1493;
            font-weight: 800;
            font-size: 1.8rem;
            margin-bottom: 1.5rem;
            border-bottom: 3px solid #ffb6c1;
            padding-bottom: 0.5rem;
        }
        .config-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            background: rgba(255,255,255,0.95);
            padding: 25px;
            border-radius: 20px;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            color: #ff1493;
            font-weight: 700;
            display: block;
            margin-bottom: 8px;
        }
        input, textarea, select {
            width: 100%;
            padding: 12px;
            border: 2px solid #ffb6c1;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 500;
        }
        textarea {
            resize: vertical;
        }
        input:focus, textarea:focus {
            outline: none;
            border-color: #ff1493;
        }
        button {
            background: linear-gradient(135deg, #ff6b9d, #ff1493);
            color: white;
            border: none;
            border-radius: 15px;
            padding: 12px 25px;
            font-weight: 800;
            font-size: 1rem;
            cursor: pointer;
            transition: 0.3s;
        }
        button:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(255,20,147,0.3);
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: rgba(255,255,255,0.95);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            border: 2px solid #ffb6c1;
        }
        .metric-value {
            font-size: 2.2rem;
            font-weight: 800;
            color: #ff1493;
        }
        .metric-label {
            color: #ff6b9d;
            font-weight: 700;
        }
        .console {
            background: #1a1a1a;
            border-radius: 15px;
            padding: 20px;
            margin-top: 20px;
            max-height: 400px;
            overflow-y: auto;
            font-family: monospace;
        }
        .console-line {
            color: #00ff88;
            font-family: monospace;
            padding: 5px 10px;
            border-left: 3px solid #ff1493;
            margin-bottom: 5px;
            background: rgba(255,20,147,0.05);
        }
        .footer {
            text-align: center;
            padding: 2rem;
            color: #ff1493;
            font-weight: 800;
            margin-top: 2rem;
        }
        .action-buttons {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
        }
        @media (max-width: 768px) {
            .config-grid { grid-template-columns: 1fr; }
            .metrics { grid-template-columns: 1fr; }
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&display=swap" rel="stylesheet">
    <script>
        function fetchStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status-badge').innerHTML = data.running ? '🟢 RUNNING' : '🔴 STOPPED';
                    document.getElementById('message-count').innerText = data.message_count;
                    const consoleDiv = document.getElementById('console-logs');
                    if (data.logs && data.logs.length > 0) {
                        consoleDiv.innerHTML = data.logs.map(log => `<div class="console-line">${escapeHtml(log)}</div>`).join('');
                    } else {
                        consoleDiv.innerHTML = '<div class="console-line">[INFO] No logs yet. Start automation to see output.</div>';
                    }
                })
                .catch(err => console.error('Status fetch error:', err));
        }
        function escapeHtml(str) {
            return str.replace(/[&<>]/g, function(m) {
                if (m === '&') return '&amp;';
                if (m === '<') return '&lt;';
                if (m === '>') return '&gt;';
                return m;
            });
        }
        setInterval(fetchStatus, 2000);
        window.onload = fetchStatus;
    </script>
</head>
<body>
<div class="app-container">
    <div class="main-header">
        <h1>🔥 R4J M1SHR4 🔥</h1>
        <p>PREMIUM FACEBOOK MESSAGE AUTOMATION TOOL</p>
    </div>
    
    <div class="sidebar">
        <h3>👤 USER DASHBOARD</h3>
        <p><strong>USERNAME:</strong> {{ username }}</p>
        <p><strong>USER ID:</strong> {{ user_id }}</p>
        <div style="background: linear-gradient(135deg, #84fab0, #8fd3f4); padding: 10px; border-radius: 12px; margin: 15px 0;">✅ PREMIUM ACCESS</div>
        <form action="/logout" method="get">
            <button type="submit" class="logout-btn">🚪 LOGOUT</button>
        </form>
    </div>
    
    <div class="section-title">⚙️ CONFIGURATION SETTINGS</div>
    <form action="/save_config" method="post">
        <div class="config-grid">
            <div>
                <div class="form-group">
                    <label>CHAT/CONVERSATION ID</label>
                    <input type="text" name="chat_id" value="{{ config.chat_id }}" placeholder="e.g., 1362400298935018">
                </div>
                <div class="form-group">
                    <label>NAME PREFIX</label>
                    <input type="text" name="name_prefix" value="{{ config.name_prefix }}" placeholder="e.g., [R4J M1SHR4]">
                </div>
                <div class="form-group">
                    <label>DELAY (SECONDS)</label>
                    <input type="number" name="delay" value="{{ config.delay }}" min="1" max="300">
                </div>
            </div>
            <div>
                <div class="form-group">
                    <label>FACEBOOK COOKIES (OPTIONAL)</label>
                    <textarea name="cookies" rows="4" placeholder="Paste cookies here (will be encrypted on server)"></textarea>
                </div>
                <div class="form-group">
                    <label>MESSAGES (ONE PER LINE)</label>
                    <textarea name="messages" rows="6" placeholder="Hello!&#10;How are you?">{{ config.messages }}</textarea>
                </div>
            </div>
        </div>
        <div style="display: flex; justify-content: center;">
            <button type="submit">💾 SAVE CONFIGURATION</button>
        </div>
    </form>
    
    <div class="section-title">🚀 AUTOMATION CONTROL</div>
    <div class="metrics">
        <div class="metric-card">
            <div class="metric-value" id="message-count">0</div>
            <div class="metric-label">MESSAGES SENT</div>
        </div>
        <div class="metric-card">
            <div class="metric-value" id="status-badge">🔴 STOPPED</div>
            <div class="metric-label">STATUS</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{{ config.chat_id[:8] if config.chat_id else 'NOT SET' }}{% if config.chat_id and config.chat_id|length > 8 %}...{% endif %}</div>
            <div class="metric-label">CHAT ID</div>
        </div>
    </div>
    
    <div class="action-buttons">
        <form action="/start" method="get" style="flex:1">
            <button type="submit" style="width:100%" id="startBtn">▶️ START AUTOMATION</button>
        </form>
        <form action="/stop" method="get" style="flex:1">
            <button type="submit" style="width:100%" id="stopBtn">⏹️ STOP AUTOMATION</button>
        </form>
    </div>
    
    <div class="section-title">📡 LIVE CONSOLE OUTPUT</div>
    <div class="console" id="console-logs">
        <div class="console-line">[INFO] Waiting for automation...</div>
    </div>
    
    <div class="footer">MADE WITH ❤️ BY R4J M1SHR4 | © 2025</div>
</div>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
