# HW Agent UI (VS Code Extension)

Developer-facing extension to drive the hardware agent demo:
- View DAG nodes and states
- Refresh status
- Start a demo run

## Setup

1. Install dependencies:
   ```bash
   cd vscode-extension
   npm install
   ```
2. Ensure the backend bridge is running and exposes:
   - `GET /state` → `{ nodes: [{ id, state, logTail? }] }`
   - `POST /run` → starts a demo run
3. Adjust the API base URL in settings (`hwAgent.apiBaseUrl`, default `http://localhost:8000`).

## Development

- Compile: `npm run compile`
- Watch: `npm run watch`
- Launch Extension Host from VS Code (Run > Launch Extension).

## Commands

- `HW Agent: Refresh State` — refresh the DAG view
- `HW Agent: Run Demo` — trigger a run via backend `/run`

## Views

- Explorer: **HW Agent DAG** shows nodes and their states (colors by state).

## Notes

- The extension calls the backend bridge over HTTP; it does not talk to RabbitMQ directly.
