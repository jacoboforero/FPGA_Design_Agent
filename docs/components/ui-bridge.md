# UI Bridge Component

The UI bridge is an optional FastAPI service used by the VS Code extension demo path.

## Endpoint Summary
- `POST /run`
- `POST /reset`
- `GET /state`
- `GET /logs/{node_id}`
- `GET/POST /chat`

## Notes
- This bridge is separate from the CLI-first workflow.
- Extension clients talk to the bridge over HTTP; they do not connect directly to RabbitMQ.

## Related Code
- `apps/ui_backend/server.py`
- `apps/vscode-extension/README.md`
