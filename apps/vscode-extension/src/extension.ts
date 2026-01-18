import * as vscode from "vscode";
import fetch from "node-fetch";
import { NodeProvider } from "./treeData";
import { openChatPanel, ChatViewProvider } from "./chatPanel";

export function activate(context: vscode.ExtensionContext) {
  console.log("HW Agent extension activating...");
  const config = () => vscode.workspace.getConfiguration("hwAgent").get<string>("apiBaseUrl", "http://localhost:8000");
  const nodeProvider = new NodeProvider(config);
  const chatViewProvider = new ChatViewProvider(context, config);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("hwAgent.nodes", nodeProvider),
    vscode.window.registerWebviewViewProvider("hwAgent.chat", chatViewProvider),
    vscode.commands.registerCommand("hwAgent.refresh", () => nodeProvider.refresh()),
    vscode.commands.registerCommand("hwAgent.runDemo", () => runDemo(config())),
    vscode.commands.registerCommand("hwAgent.openChat", () => openChatPanel(context, config())),
  );
}

async function runDemo(apiBaseUrl: string) {
  try {
    const res = await fetch(`${apiBaseUrl}/run`, { method: "POST" });
    if (!res.ok) {
      const text = await res.text();
      vscode.window.showErrorMessage(`HW Agent: run failed (${res.status}) ${text}`);
      return;
    }
    vscode.window.showInformationMessage("HW Agent: demo run started.");
  } catch (err) {
    vscode.window.showErrorMessage(`HW Agent: error starting run (${err})`);
  }
}

export function deactivate() {
  // noop
}
