import * as vscode from "vscode";
import fetch from "node-fetch";

export interface NodeState {
  id: string;
  state: string;
  logTail?: string;
}

const DEMO_NODES: NodeState[] = [
  { id: "demo_module", state: "PENDING", logTail: "Awaiting orchestration (demo)." },
  { id: "demo_module.impl", state: "IMPLEMENTING" },
  { id: "demo_module.lint", state: "LINTING" },
  { id: "demo_module.tb", state: "TESTBENCHING" },
  { id: "demo_module.sim", state: "SIMULATING" },
  { id: "demo_module.distill", state: "DISTILLING" },
  { id: "demo_module.reflect", state: "REFLECTING" },
  { id: "demo_module.debug", state: "DEBUGGING" },
];

export class NodeItem extends vscode.TreeItem {
  constructor(public readonly info: NodeState) {
    super(info.id, vscode.TreeItemCollapsibleState.None);
    this.description = info.state;
    const tooltip = new vscode.MarkdownString(undefined, true);
    tooltip.appendMarkdown(`**${info.id}** — ${info.state}`);
    if (info.logTail) {
      tooltip.appendMarkdown(`\n\n\`\`\`\n${info.logTail}\n\`\`\``);
    }
    tooltip.isTrusted = false;
    this.tooltip = tooltip;
    this.iconPath = new vscode.ThemeIcon("circle-filled", new vscode.ThemeColor(getColor(info.state)));
    this.contextValue = "node";
  }
}

function getColor(state: string): string {
  switch (state) {
    case "DONE":
      return "charts.green";
    case "FAILED":
      return "charts.red";
    case "SIMULATING":
    case "LINTING":
    case "IMPLEMENTING":
    case "TESTBENCHING":
    case "DISTILLING":
    case "REFLECTING":
    case "DEBUGGING":
      return "charts.blue";
    default:
      return "foreground";
  }
}

export class NodeProvider implements vscode.TreeDataProvider<NodeItem> {
  private _onDidChangeTreeData: vscode.EventEmitter<NodeItem | undefined | void> = new vscode.EventEmitter();
  readonly onDidChangeTreeData: vscode.Event<NodeItem | undefined | void> = this._onDidChangeTreeData.event;

  constructor(private apiBaseUrl: () => string) {}

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: NodeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<NodeItem[]> {
    const base = this.apiBaseUrl();
    let nodes: NodeState[] = DEMO_NODES;
    try {
      const res = await fetch(`${base}/state`);
      if (res.ok) {
        const data = (await res.json()) as { nodes: NodeState[] };
        if (data.nodes && data.nodes.length > 0) {
          nodes = data.nodes;
        }
      }
    } catch {
      // stay on demo nodes
    }
    return nodes.map((n) => new NodeItem(n));
  }
}
