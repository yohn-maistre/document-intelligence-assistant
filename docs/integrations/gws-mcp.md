# Google Workspace MCP — opt-in agentic surface

> Not on the brief's MUST-have path. Documented here so reviewers see the
> shape of the advanced agentic surface without it being required to run
> `docker compose up`.

## What it does

`google_workspace_mcp` is a third-party MCP server that exposes
Google Workspace (Calendar / Gmail / Sheets / Drive) to any MCP-aware
client. When wired alongside klerk, the chat surface (or any external
Claude Desktop / Goose / Cursor client) can:

- Read calendar invites that reference a doc klerk has ingested →
  contextualise scheduling questions.
- Watch Drive folder activity beyond klerk's ingest path → catch
  changes klerk hasn't synced yet.
- Send Gmail drafts directly from klerk's Escalation Drafter (capability A)
  by piping `EscalationDraft.to` / `subject` / `body` through the MCP's
  Gmail tool.
- Push klerk's contradiction report (capability C) into a Google Sheet
  for the operator's weekly review.

## How klerk hooks it

Two integration points kept independent:

1. **Direct ingest** stays the official path. klerk's
   `klerk.drive.sync` module (Service Account auth + `changes.list`) is
   what `POST /ingest?source=drive` calls. No Workspace MCP involved.

2. **Agentic reach** is the opt-in path. Add the workspace MCP as a
   side-car container (already commented in `docker-compose.yml`) and
   point klerk's MCP gateway (`klerk-mcp`) at it. Then klerk's chat
   surface can call Gmail/Calendar/Sheets through the same tool
   protocol it already uses for retrieval + ingest.

## Why the split

- **Brief compliance**: `docker compose up` works without OAuth consent
  flows or Workspace MCP. The SDK path (`klerk.drive.sync`) is
  Service-Account-only.
- **Operator choice**: organisations that don't want klerk to read
  Gmail can simply not enable the side-car. Default is off.
- **Failure independence**: Workspace MCP being down doesn't break
  klerk's `/chat` or `/ingest`.

## How to enable

1. Uncomment the `gws-mcp` service block in `docker-compose.yml`.
2. Set `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` in `.env`
   (different from `GOOGLE_APPLICATION_CREDENTIALS` — Workspace MCP uses
   OAuth, not the Service Account path).
3. `docker compose up gws-mcp`.
4. Configure your MCP-aware client to connect to klerk's MCP gateway:
   ```jsonc
   {
     "mcpServers": {
       "klerk": {
         "command": "klerk-mcp",
         "transport": "stdio"
       }
     }
   }
   ```

## Reference

Upstream: <https://github.com/taylorwilsdon/google_workspace_mcp>
(verify the licence and the OAuth scopes match your organisation's
policy before enabling on a real Workspace).
