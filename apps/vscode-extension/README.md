# HW Agent VS Code Extension

This extension connects to the optional HTTP UI bridge for viewing state and triggering demo actions.

## Setup
From repo root:

```bash
cd apps/vscode-extension
npm install
```

## Required Backend Endpoints
- `GET /state`
- `POST /run`

## Notes
- API base URL setting: `hwAgent.apiBaseUrl` (default `http://localhost:8000`).
- The extension talks to the HTTP bridge, not RabbitMQ directly.

## Related Files
- `apps/vscode-extension/src/`
- `apps/ui_backend/server.py`
- `docs/components/ui-bridge.md`
