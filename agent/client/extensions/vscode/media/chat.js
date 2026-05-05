const vscode = acquireVsCodeApi();
const msgs = document.getElementById('messages');
const input = document.getElementById('input');
const status = document.getElementById('status');
const session = document.getElementById('session');
const send = document.getElementById('send');
const clear = document.getElementById('clear');
const refresh = document.getElementById('refresh');
const sessions = document.getElementById('sessions');

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderMarkdown(text) {
  const source = String(text ?? '');
  const safeSource = escapeHtml(source);

  if (!window.marked || typeof window.marked.parse !== 'function') {
    return '<p>' + safeSource.replace(/\n/g, '<br>') + '</p>';
  }

  return window.marked.parse(safeSource, {
    gfm: true,
    breaks: true,
  });
}

function renderMarkdownSafe(text) {
  try {
    return renderMarkdown(text);
  } catch (error) {
    return '<p>' + escapeHtml(String(text ?? '')).replace(/\n/g, '<br>') + '</p>';
  }
}

window.addEventListener('message', event => {
  try {
    const data = event && event.data ? event.data : {};
    const messages = Array.isArray(data.messages) ? data.messages : [];
    const statusText = typeof data.status === 'string' ? data.status : '';
    const sessionLabel = typeof data.sessionLabel === 'string' ? data.sessionLabel : '';
    const isLoading = Boolean(data.isLoading);

    if (statusText) {
      status.textContent = statusText;
    }

    if (session && sessionLabel) {
      session.textContent = sessionLabel;
    }

    send.disabled = isLoading;
    input.disabled = isLoading;
    msgs.innerHTML = '';

    messages.forEach(message => {
      if (!message || typeof message !== 'object') {
        return;
      }

      const div = document.createElement('div');
      const sender = message.sender === 'user' ? 'user' : 'assistant';
      const text = typeof message.text === 'string' ? message.text : String(message.text ?? '');

      div.className = 'msg ' + sender;
      div.innerHTML = renderMarkdownSafe(text);
      msgs.appendChild(div);
    });

    msgs.scrollTop = msgs.scrollHeight;
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    msgs.innerHTML = '';

    const div = document.createElement('div');
    div.className = 'msg assistant';
    div.textContent = 'Rendering error: ' + message;
    msgs.appendChild(div);

    vscode.postMessage({ action: 'webview-error', text: message });
  }
});

window.addEventListener('error', event => {
  const message = event && event.message ? event.message : 'Unknown webview error';
  vscode.postMessage({ action: 'webview-error', text: message });
});

vscode.postMessage({ action: 'webview-ready' });

input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    send.click();
  }
});

send.addEventListener('click', () => {
  const text = input.value.trim();
  if (text) {
    vscode.postMessage({ type: 'send', text });
    input.value = '';
  }
});

clear.addEventListener('click', () => {
  vscode.postMessage({ action: 'clear-chat' });
});

refresh.addEventListener('click', () => {
  vscode.postMessage({ action: 'refresh-health' });
});

if (sessions) {
  sessions.addEventListener('click', () => {
    vscode.postMessage({ action: 'open-sessions' });
  });
}
