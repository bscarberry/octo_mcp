# octo-mcp-server

A production-ready [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server built with Node.js, TypeScript, and Express. It uses HTTP + SSE (Server-Sent Events) as the transport so it can be deployed remotely and serve multiple clients concurrently.

## Project structure

```
src/
  index.ts        # Entry point — creates Express app, mounts /sse and /message routes
  server.ts       # MCP server factory, session registry, message routing
  tools/
    echo.ts       # Example tool: returns its input unchanged
Dockerfile
tsconfig.json
package.json
.env.example
```

## Adding a new tool

1. Create `src/tools/my-tool.ts` and export a `registerMyTool(server: McpServer)` function:

```ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import * as z from 'zod/v4';

export function registerMyTool(server: McpServer): void {
  server.tool(
    'my-tool',
    'Description shown to the LLM',
    { input: z.string() },
    async ({ input }) => ({
      content: [{ type: 'text', text: `Result: ${input}` }],
    }),
  );
}
```

2. Import and call it in `src/server.ts`:

```ts
import { registerMyTool } from './tools/my-tool.js';
// inside createMcpServer:
registerMyTool(server);
```

That's it.

## Local development

### Prerequisites

- Node.js ≥ 18
- npm

### Setup

```bash
cp .env.example .env          # edit PORT or add API keys as needed
npm install
npm run build
npm start
```

The server starts on `http://localhost:3000` (or whatever `PORT` is set to).

### Verify with curl

```bash
# Health check
curl http://localhost:3000/health

# Open an SSE stream (keep this terminal open)
curl -N http://localhost:3000/sse
# You will see: event: endpoint\ndata: /message?sessionId=<ID>

# In another terminal, call the echo tool (replace <SESSION_ID>)
curl -X POST "http://localhost:3000/message?sessionId=<SESSION_ID>" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "echo",
      "arguments": { "message": "hello world" }
    }
  }'
```

### Available npm scripts

| Script        | Description                       |
|---------------|-----------------------------------|
| `npm run build` | Compile TypeScript → `dist/`    |
| `npm start`     | Run the compiled server          |
| `npm run dev`   | Run with ts-node (no compile)    |
| `npm run clean` | Delete `dist/`                   |

## Docker

```bash
# Build
docker build -t octo-mcp-server .

# Run (pass environment variables with -e or --env-file)
docker run -p 3000:3000 --env-file .env octo-mcp-server
```

## Deploy to Azure Web App

### Option A — Deploy a Docker container (recommended)

1. **Push your image to a container registry** (Azure Container Registry, Docker Hub, etc.):

```bash
az acr build --registry <your-registry> --image octo-mcp-server:latest .
```

2. **Create the Web App** (Linux, Docker):

```bash
az group create --name rg-octo-mcp --location eastus

az appservice plan create \
  --name plan-octo-mcp \
  --resource-group rg-octo-mcp \
  --is-linux \
  --sku B1

az webapp create \
  --name octo-mcp-server \
  --resource-group rg-octo-mcp \
  --plan plan-octo-mcp \
  --deployment-container-image-name <your-registry>.azurecr.io/octo-mcp-server:latest
```

3. **Set environment variables**:

```bash
az webapp config appsettings set \
  --name octo-mcp-server \
  --resource-group rg-octo-mcp \
  --settings PORT=3000 MY_API_KEY=...
```

4. **Enable Always On** so the server stays warm:

```bash
az webapp config set \
  --name octo-mcp-server \
  --resource-group rg-octo-mcp \
  --always-on true
```

> **SSE note:** Azure App Service by default has a 230-second idle request timeout. For long-lived SSE connections you may need to send keep-alive comments or configure the timeout via `az webapp config set --http20-enabled true`.

### Option B — Deploy from source with Oryx build

1. Zip the source (exclude `node_modules` and `dist`):

```bash
zip -r deploy.zip . --exclude "node_modules/*" "dist/*" ".git/*"
```

2. Deploy:

```bash
az webapp deployment source config-zip \
  --name octo-mcp-server \
  --resource-group rg-octo-mcp \
  --src deploy.zip
```

Azure will run `npm install && npm run build && npm start` automatically via the Oryx build system.

## Environment variables

| Variable | Default | Description                    |
|----------|---------|--------------------------------|
| `PORT`   | `3000`  | TCP port the server listens on |

Add any tool-specific secrets (API keys, connection strings) here as well.

## API endpoints

| Method | Path       | Description                                           |
|--------|------------|-------------------------------------------------------|
| GET    | `/health`  | Returns `{"status":"ok","timestamp":"…"}`             |
| GET    | `/sse`     | Opens an SSE stream; emits the POST endpoint + session ID |
| POST   | `/message` | Receives JSON-RPC 2.0 messages (`?sessionId=<id>`)    |
