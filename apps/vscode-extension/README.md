# HW Agent VS Code Extension

## Purpose
Document extension setup for viewing DAG state and triggering demo runs.

## Audience
Developers using the VS Code UI extension.

## Scope
Extension-side setup and expected backend endpoints.

## Setup (from repo root)
```bash
cd apps/vscode-extension
npm install
```

## Required Backend Endpoints
- `GET /state`
- `POST /run`

## Notes
- API base URL setting: `hwAgent.apiBaseUrl` (default `http://localhost:8000`).
- Extension talks to HTTP bridge, not RabbitMQ directly.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/apps/vscode-extension/src/`
- `/home/jacobo/school/FPGA_Design_Agent/apps/ui_backend/server.py`

## Related Docs
- [/home/jacobo/school/FPGA_Design_Agent/docs/components/ui-bridge.md](/home/jacobo/school/FPGA_Design_Agent/docs/components/ui-bridge.md)
- [/home/jacobo/school/FPGA_Design_Agent/docs/cli.md](/home/jacobo/school/FPGA_Design_Agent/docs/cli.md)
