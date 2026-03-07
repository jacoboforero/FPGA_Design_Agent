# UI Bridge Component

## Purpose
Document the FastAPI bridge used by the VS Code extension demo workflow.

## Audience
Engineers maintaining the extension bridge and local demo endpoints.

## Scope
Bridge endpoints and integration expectations.

## Endpoints
- `POST /run`
- `POST /reset`
- `GET /state`
- `GET /logs/{node_id}`
- `GET/POST /chat`

## Notes
- Bridge is optional and separate from CLI-first runtime workflows.
- Extension communicates over HTTP and does not connect directly to RabbitMQ.

## Source of Truth
- `/home/jacobo/school/FPGA_Design_Agent/apps/ui_backend/server.py`
- `/home/jacobo/school/FPGA_Design_Agent/apps/vscode-extension/README.md`

## Related Docs
- [../cli.md](../cli.md)
- [../architecture.md](../architecture.md)
