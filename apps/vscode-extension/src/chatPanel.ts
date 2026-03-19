import * as vscode from "vscode";
import fetch from "node-fetch";

export function openChatPanel(context: vscode.ExtensionContext, apiBaseUrl: string) {
  const panel = vscode.window.createWebviewPanel("hwAgentChat", "Spec Chat", vscode.ViewColumn.One, {
    enableScripts: true,
    retainContextWhenHidden: true,
  });

  const nonce = getNonce();
  panel.webview.html = getHtml(apiBaseUrl, nonce);

  panel.webview.onDidReceiveMessage(async (msg) => {
    if (msg.type === "send") {
      panel.webview.postMessage({ type: "sending" });
      try {
        const res = await fetch(`${apiBaseUrl}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: msg.payload }),
        });
        const data: any = await res.json();
        panel.webview.postMessage({ type: "history", payload: data.history });
      } catch (err) {
        vscode.window.showErrorMessage(`HW Agent chat error: ${err}`);
      }
    } else if (msg.type === "load") {
      try {
        const res = await fetch(`${apiBaseUrl}/chat`);
        const data: any = await res.json();
        panel.webview.postMessage({ type: "history", payload: data.history });
      } catch (err) {
        vscode.window.showErrorMessage(`HW Agent chat load error: ${err}`);
      }
    } else if (msg.type === "reset") {
      try {
        await fetch(`${apiBaseUrl}/chat/reset`, { method: "POST" });
      } catch {
        // ignore; backend may not implement reset yet
      }
      panel.webview.postMessage({ type: "history", payload: [] });
    }
  });
}

export class ChatViewProvider implements vscode.WebviewViewProvider {
  constructor(private context: vscode.ExtensionContext, private apiBaseUrl: () => string) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void | Thenable<void> {
    const nonce = getNonce();
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = getHtml(this.apiBaseUrl(), nonce);
    webviewView.webview.onDidReceiveMessage(async (msg) => {
      if (msg.type === "send") {
        webviewView.webview.postMessage({ type: "sending" });
        try {
          const res = await fetch(`${this.apiBaseUrl()}/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: msg.payload }),
          });
          const data: any = await res.json();
          webviewView.webview.postMessage({ type: "history", payload: data.history });
        } catch (err) {
          webviewView.webview.postMessage({ type: "history", payload: [] });
          vscode.window.showErrorMessage(`HW Agent chat error: ${err}`);
        }
      } else if (msg.type === "load") {
        try {
          const res = await fetch(`${this.apiBaseUrl()}/chat`);
          const data: any = await res.json();
          webviewView.webview.postMessage({ type: "history", payload: data.history });
        } catch (err) {
          vscode.window.showErrorMessage(`HW Agent chat load error: ${err}`);
        }
      } else if (msg.type === "reset") {
        try {
          await fetch(`${this.apiBaseUrl()}/chat/reset`, { method: "POST" });
        } catch {
          // ignore; backend may not implement reset yet
        }
        webviewView.webview.postMessage({ type: "history", payload: [] });
      }
    });
  }
}

function getHtml(apiBaseUrl: string, nonce: string): string {
  return /* html */ `<!DOCTYPE html>
  <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: data:; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}';" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <style nonce="${nonce}">
        :root {
          --bg: #0f1116;
          --panel: #131722;
          --panel-strong: #0f172a;
          --border: #222c3d;
          --accent: #4fd1c5;
          --accent-2: #7c3aed;
          --text: #ecf0f8;
          --muted: #9ba6bb;
          --shadow: 0 15px 50px rgba(0, 0, 0, 0.35);
        }
        body {
          font-family: "IBM Plex Sans", "SF Pro Display", "Segoe UI", system-ui, sans-serif;
          padding: 0;
          margin: 0;
          background: radial-gradient(circle at 20% 20%, rgba(79, 209, 197, 0.12), transparent 30%),
            radial-gradient(circle at 80% 0%, rgba(124, 58, 237, 0.14), transparent 25%),
            var(--bg);
          color: var(--text);
        }
        .wrapper { display: flex; flex-direction: column; height: 100vh; }
        .header {
          padding: 14px 16px 10px 16px;
          border-bottom: 1px solid var(--border);
          background: linear-gradient(135deg, rgba(79, 209, 197, 0.14), rgba(124, 58, 237, 0.12));
        }
        .title {
          margin: 0;
          font-size: 15px;
          letter-spacing: 0.4px;
          display: flex;
          gap: 8px;
          align-items: center;
          font-weight: 600;
        }
        .pill {
          padding: 2px 10px;
          border-radius: 999px;
          font-size: 11px;
          background: rgba(236, 240, 248, 0.08);
          border: 1px solid rgba(236, 240, 248, 0.18);
          color: var(--text);
        }
        .meta {
          font-size: 12px;
          color: var(--muted);
          margin-top: 4px;
        }
        .messages {
          flex: 1;
          min-height: 160px;
          overflow-y: auto;
          padding: 14px 14px 4px 14px;
          gap: 10px;
          display: flex;
          flex-direction: column;
          background: linear-gradient(180deg, rgba(19, 23, 34, 0.75), rgba(15, 17, 22, 0.92));
        }
        .toolbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px 14px 8px 14px;
          border-bottom: 1px solid var(--border);
          background: rgba(19, 23, 34, 0.72);
        }
        .empty {
          margin: 40px auto 0 auto;
          text-align: center;
          color: var(--muted);
          font-size: 13px;
          padding: 12px 16px;
          border: 1px dashed var(--border);
          border-radius: 12px;
          background: rgba(19, 23, 34, 0.6);
        }
        .bubble {
          padding: 12px 14px;
          border-radius: 12px;
          max-width: 92%;
          white-space: pre-wrap;
          position: relative;
          border: 1px solid var(--border);
          box-shadow: var(--shadow);
        }
        .bubble .label {
          display: inline-block;
          font-size: 10px;
          letter-spacing: 0.4px;
          text-transform: uppercase;
          color: var(--muted);
          margin-bottom: 6px;
        }
        .user {
          align-self: flex-end;
          background: linear-gradient(135deg, rgba(79, 209, 197, 0.3), rgba(124, 58, 237, 0.3));
          border-color: rgba(79, 209, 197, 0.5);
        }
        .agent {
          align-self: flex-start;
          background: var(--panel);
          border-color: rgba(236, 240, 248, 0.06);
        }
        .input-area {
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 12px;
          border-top: 1px solid var(--border);
          background: var(--panel-strong);
        }
        .dag {
          margin: 10px 14px 0 14px;
          padding: 12px;
          border-radius: 12px;
          border: 1px solid var(--border);
          background: rgba(19, 23, 34, 0.6);
        }
        .dag h3 {
          margin: 0 0 10px 0;
          font-size: 13px;
          color: var(--muted);
        }
        .dag-timeline {
          display: flex;
          align-items: center;
          gap: 8px;
          overflow-x: auto;
          padding-bottom: 4px;
        }
        .dag-node {
          min-width: 110px;
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 8px;
          font-size: 12px;
          background: rgba(79, 209, 197, 0.08);
          box-shadow: var(--shadow);
        }
        .dag-node .state { color: var(--muted); font-size: 11px; }
        .dag-connector {
          flex: 1;
          min-width: 30px;
          height: 2px;
          background: linear-gradient(90deg, rgba(79, 209, 197, 0.6), rgba(124, 58, 237, 0.6));
          border-radius: 2px;
        }
        .chips {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .chip {
          border: 1px solid var(--border);
          background: rgba(236, 240, 248, 0.04);
          color: var(--text);
          padding: 6px 10px;
          border-radius: 999px;
          cursor: pointer;
          font-size: 12px;
        }
        .chip:hover { border-color: rgba(79, 209, 197, 0.7); }
        .input-row {
          display: flex;
          gap: 10px;
          align-items: center;
        }
        textarea {
          flex: 1;
          resize: none;
          border-radius: 12px;
          border: 1px solid var(--border);
          background: #0d1018;
          color: var(--text);
          padding: 10px 12px;
          height: 80px;
          font-size: 13px;
          transition: border 0.15s ease;
        }
        textarea:focus { outline: none; border-color: rgba(79, 209, 197, 0.8); }
        button {
          border: none;
          border-radius: 12px;
          background: linear-gradient(135deg, var(--accent), var(--accent-2));
          color: white;
          padding: 10px 14px;
          cursor: pointer;
          min-width: 80px;
          font-weight: 600;
          box-shadow: var(--shadow);
        }
        button:disabled { opacity: 0.6; cursor: not-allowed; box-shadow: none; }
        .ghost {
          background: rgba(236, 240, 248, 0.05);
          color: var(--text);
          border: 1px solid var(--border);
          box-shadow: none;
        }
        .status {
          font-size: 12px;
          color: var(--muted);
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .dot {
          width: 8px;
          height: 8px;
          border-radius: 999px;
          background: var(--accent);
          box-shadow: 0 0 0 3px rgba(79, 209, 197, 0.2);
        }
        .sending { opacity: 0.6; }
      </style>
    </head>
    <body>
      <div class="wrapper">
        <div class="header">
          <div class="title">
            HW Spec Chat
            <span class="pill">L1–L5 planning helper</span>
          </div>
          <div class="meta">Backend: ${apiBaseUrl}</div>
        </div>
        <div class="toolbar">
          <div class="status"><span class="dot"></span><span id="agentLabel"></span></div>
          <div style="display:flex; gap:8px;">
            <button id="showDag" class="ghost">Show Demo DAG</button>
            <button id="reset" class="ghost">New Chat</button>
          </div>
        </div>
        <div id="dag" class="dag">
          <h3>Demo DAG</h3>
          <div id="dagGrid" class="dag-timeline"></div>
        </div>
        <div id="messages" class="messages"></div>
        <div class="input-area">
          <div class="input-row">
            <textarea id="input" placeholder="Describe your spec, constraints, interfaces... (Shift+Enter for newline)"></textarea>
            <button id="send">Send</button>
          </div>
        </div>
      </div>
      <script nonce="${nonce}">
        const vscode = acquireVsCodeApi();
        const messagesEl = document.getElementById("messages");
        const inputEl = document.getElementById("input");
        const sendBtn = document.getElementById("send");
        const resetBtn = document.getElementById("reset");
        const dagBtn = document.getElementById("showDag");
        const dagEl = document.getElementById("dag");
        const dagGrid = document.getElementById("dagGrid");
        const agentLabel = document.getElementById("agentLabel");
        let sending = false;
        const agentName = "Spec Helper"; // can be swapped when routing to other agents
        const demoDag = [
          { id: "demo_module", state: "PENDING" },
          { id: "demo_module.impl", state: "IMPLEMENTING" },
          { id: "demo_module.lint", state: "LINTING" },
          { id: "demo_module.tb", state: "TESTBENCHING" },
          { id: "demo_module.sim", state: "SIMULATING" },
          { id: "demo_module.distill", state: "DISTILLING" },
          { id: "demo_module.reflect", state: "REFLECTING" },
        ];

        agentLabel.textContent = "Chatting with: " + agentName;

        function render(history) {
          messagesEl.innerHTML = "";
          if (!history || history.length === 0) {
            const empty = document.createElement("div");
            empty.className = "empty";
            empty.textContent = "Start by providing your design specification.";
            messagesEl.appendChild(empty);
            return;
          }
          history.forEach(m => {
            const div = document.createElement("div");
            div.className = "bubble " + (m.role === "user" ? "user" : "agent");
            const label = document.createElement("div");
            label.className = "label";
            label.textContent = m.role === "user" ? "You" : agentName;
            const body = document.createElement("div");
            body.textContent = m.content;
            div.appendChild(label);
            div.appendChild(body);
            messagesEl.appendChild(div);
          });
          messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        window.addEventListener("message", event => {
          const { type, payload } = event.data;
          if (type === "history") {
            render(payload || []);
            sending = false;
            sendBtn.disabled = false;
            messagesEl.classList.remove("sending");
          } else if (type === "sending") {
            sending = true;
            sendBtn.disabled = true;
            messagesEl.classList.add("sending");
          }
        });

        function sendMessage(text) {
          if (sending) return;
          sendBtn.disabled = true;
          sending = true;
          messagesEl.classList.add("sending");
          vscode.postMessage({ type: "send", payload: text });
        }

        resetBtn.onclick = () => {
          vscode.postMessage({ type: "reset" });
          render([]);
          inputEl.value = "";
        };

        dagBtn.onclick = () => {
          dagEl.style.display = dagEl.style.display === "none" ? "block" : "none";
          if (dagEl.style.display === "block") {
            renderDag();
          }
        };

        function renderDag() {
          dagGrid.innerHTML = "";
          demoDag.forEach((n, idx) => {
            const div = document.createElement("div");
            div.className = "dag-node";
            div.innerHTML = "<div><strong>" + n.id + "</strong></div><div class='state'>" + n.state + "</div>";
            dagGrid.appendChild(div);
            if (idx !== demoDag.length - 1) {
              const conn = document.createElement("div");
              conn.className = "dag-connector";
              dagGrid.appendChild(conn);
            }
          });
        }

        // Render the demo DAG on load so it is always visible even without backend data.
        renderDag();

        sendBtn.onclick = () => {
          const text = inputEl.value.trim();
          if (!text) return;
          sendMessage(text);
          inputEl.value = "";
        };

        inputEl.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            sendBtn.click();
          }
        });

        vscode.postMessage({ type: "load" });
      </script>
    </body>
  </html>`;
}

function getNonce() {
  let text = "";
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
