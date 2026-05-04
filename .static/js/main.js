let pollInterval = null;

async function loadUserInfo() {
    const res = await fetch('/api/user/info');
    const data = await res.json();
    document.getElementById('username').innerText = data.username;
    document.getElementById('user-id').innerText = data.user_id;
}

async function loadConfig() {
    const res = await fetch('/api/config');
    const cfg = await res.json();
    document.getElementById('chat-id').value = cfg.chat_id || '';
    document.getElementById('name-prefix').value = cfg.name_prefix || '';
    document.getElementById('delay').value = cfg.delay || 10;
    document.getElementById('cookies').value = cfg.cookies || '';
    document.getElementById('messages').value = cfg.messages || 'Hello!';
    document.getElementById('chat-id-display').innerText = cfg.chat_id ? cfg.chat_id.slice(0,8)+'...' : 'NOT SET';
}

async function saveConfig() {
    const data = {
        chat_id: document.getElementById('chat-id').value,
        name_prefix: document.getElementById('name-prefix').value,
        delay: parseInt(document.getElementById('delay').value),
        cookies: document.getElementById('cookies').value,
        messages: document.getElementById('messages').value
    };
    await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    alert('Configuration saved!');
    loadConfig();
}

async function startAutomation() {
    await fetch('/api/automation/start', {method: 'POST'});
    refreshStatus();
}

async function stopAutomation() {
    await fetch('/api/automation/stop', {method: 'POST'});
    refreshStatus();
}

async function refreshStatus() {
    const res = await fetch('/api/automation/status');
    const data = await res.json();
    document.getElementById('msg-count').innerText = data.message_count;
    const statusElem = document.getElementById('status');
    if (data.running) {
        statusElem.innerHTML = '🟢 RUNNING';
        statusElem.style.color = '#00ff88';
    } else {
        statusElem.innerHTML = '🔴 STOPPED';
        statusElem.style.color = '#ff4444';
    }
    // update console logs
    const consoleDiv = document.getElementById('console');
    if (data.logs && data.logs.length) {
        consoleDiv.innerHTML = data.logs.map(log => `<div class="console-line">${log}</div>`).join('');
        consoleDiv.scrollTop = consoleDiv.scrollHeight;
    }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(refreshStatus, 2000);
}

// Tab handling
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.getElementById(`${tab}-tab`).classList.add('active');
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    });
});

document.getElementById('save-config').addEventListener('click', saveConfig);
document.getElementById('start-btn').addEventListener('click', startAutomation);
document.getElementById('stop-btn').addEventListener('click', stopAutomation);
document.getElementById('logout-btn').addEventListener('click', () => window.location.href = '/logout');

loadUserInfo();
loadConfig();
refreshStatus();
startPolling();
