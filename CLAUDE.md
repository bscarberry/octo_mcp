# CLAUDE.md — MCP Server on Azure Functions (Custom Handler Pattern)

This file provides context and guidance for working with this repository. It is intended to help
an LLM understand the architecture, constraints, and conventions used when porting or tuning a
Python MCP server for hosting on Azure Functions as a **custom handler**.

---

## Project Overview

This repo hosts a Python MCP server built with the **official Anthropic MCP Python SDK** (FastMCP)
and deploys it to **Azure Functions** using the **custom handler** pattern. It does NOT use the
Azure Functions MCP extension or triggers/bindings. The MCP server is a self-contained HTTP
process; Azure Functions acts as a managed, scalable host around it.

Reference architecture: [Azure-Samples/mcp-sdk-functions-hosting-python](https://github.com/Azure-Samples/mcp-sdk-functions-hosting-python)  
Official docs: [Host MCP SDK servers on Azure Functions](https://learn.microsoft.com/en-us/azure/azure-functions/scenario-host-mcp-server-sdks)

---

## Architecture

```
MCP Client (Copilot Studio / VS Code / Claude Desktop)
    │
    ▼ HTTPS (streamable-http transport)
Azure API Management  ←─ optional; used for auth, rate limiting, VNET exposure
    │
    ▼
Azure Functions Host  (custom handler bridge)
    │  pings / on startup → 404 (expected, not an error)
    ▼
FastMCP Server Process  (server.py on port 8000)
    │
    ▼
Downstream APIs / Services (Panther, Graph, Defender, etc.)
```

**Key facts about the custom handler pattern:**
- The Azure Functions host proxies HTTP requests to the MCP server's local HTTP port.
- The MCP server runs as a normal Python web process (FastMCP + streamable-http).
- On startup, Functions pings `GET /`. Since MCP servers don't implement `/`, a `404` is returned
  and logged in red — **this is expected behavior, not a bug**.
- MCP SDK info logs may appear red in the Functions log output because they write to `stderr` by
  default. This is cosmetic only.
- No Azure Functions triggers, bindings, or decorators are used in the MCP server code itself.

---

## Repository Structure

```
.
├── server.py                  # FastMCP server — all tools defined here
├── host.json                  # Azure Functions custom handler config (REQUIRED)
├── local.settings.json        # Local dev env vars (NOT committed to source control)
├── pyproject.toml             # Python project metadata and uv dependencies
└── uv.lock                    # Locked dependencies for reproducible builds
```

---

## Critical Configuration Files

### `host.json` — Custom Handler Declaration

This is the **minimum required file** to run the MCP server on Azure Functions.
It must live at the project root. Do not move or rename it.

```json
{
  "version": "2.0",
  "configurationProfile": "mcp-custom-handler",
  "customHandler": {
    "description": {
      "defaultExecutablePath": "python",
      "arguments": ["server.py"]
    },
    "port": "8000"
  }
}
```

#### What `configurationProfile: "mcp-custom-handler"` actually sets

Using this profile is shorthand. It automatically applies the following settings to the Functions
host — **you do not need to add these manually**, but understanding them is important:

```json
{
  "version": "2.0",
  "extensions": {
    "http": {
      "routePrefix": ""
    }
  },
  "customHandler": {
    "http": {
      "enableProxying": true,
      "defaultAuthorizationLevel": "anonymous",
      "routes": [
        {
          "route": "{*route}"
        },
        {
          "route": "admin/{*route}",
          "authorizationLevel": "admin"
        }
      ]
    }
  }
}
```

Key behaviors this configures:

| Setting | Value | Effect |
|---|---|---|
| `enableProxying` | `true` | Functions host acts as a **reverse proxy** — forwards the full HTTP request (headers, body, query params) unchanged to the MCP server. Without this, Functions would transform the request into its own format before passing it along. |
| `defaultAuthorizationLevel` | `anonymous` | MCP endpoints are not gated by a Functions API key by default. Auth is instead handled by EasyAuth / APIM at the platform layer. |
| `routePrefix` | `""` | Removes the default `/api` prefix. Requests hit paths like `/mcp` directly, not `/api/mcp`. |
| `routes[0].route` | `{*route}` | Catches **all paths** (`/`, `/mcp`, `/anything/nested`) and forwards them to the MCP server. This is what allows the `/mcp` endpoint to work. |
| `routes[1].route` | `admin/{*route}` | Admin paths require admin-level auth. Do not expose admin routes publicly. |

**Rules for modifying `host.json`:**
- `arguments` must point to the main Python entry point (e.g., `server.py`, `main.py`).
- `port` must match the port the FastMCP server binds to in `server.py`.
- `configurationProfile: "mcp-custom-handler"` is required for the MCP routing to work — do not
  remove it or replace it with manual settings unless you fully understand the above.
- Do NOT add MCP extension config (`extensions.mcp`) — that is only for the Functions MCP
  extension pattern, which is a different approach entirely.

### `local.settings.json` — Local Environment Variables

Used by `func start` for local development only. Never committed to source control.

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "CUSTOM_HANDLER_PORT": "8000"
  }
}
```

**Important:** `CUSTOM_HANDLER_PORT` must match the port in `host.json` and the port the
FastMCP server listens on.

---

## Server Entry Point (`server.py`)

The MCP server uses **FastMCP** with `streamable-http` transport.

### Required Pattern

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("your-server-name", stateless_http=True)

@mcp.tool()
async def your_tool(param: str) -> str:
    """Tool description exposed to MCP clients."""
    ...

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

### Key Constraints

| Setting | Value | Why |
|---|---|---|
| `transport` | `"streamable-http"` | Required for Azure Functions hosting; do NOT use `"stdio"` or `"sse"` |
| `stateless_http` | `True` | Required for scalability in serverless/Flex Consumption environments |
| Default port | `8000` | Must match `host.json` and `local.settings.json` |
| Tool decorators | `@mcp.tool()` | Standard FastMCP pattern; all tool logic lives inside decorated functions |

### Adding Tools

All tools go in `server.py` (or imported modules). Follow this pattern:

```python
@mcp.tool()
async def get_data(query: str) -> str:
    """
    Brief description of what this tool does.
    
    Args:
        query: Description of the parameter for the MCP client.
    """
    result = await call_some_api(query)
    return str(result)
```

**Rules:**
- Always include a docstring — it becomes the tool's description for MCP clients.
- Parameter type hints are required; they generate the JSON schema exposed to clients.
- Prefer `async def` for all tools that make I/O calls.
- Return type should be `str` or a JSON-serializable type.
- Never raise unhandled exceptions from tools — catch and return error strings instead.

---

## Authentication

### EasyAuth (App Service Built-in Auth)

Authentication is handled at the Azure Functions / App Service layer using **Entra ID EasyAuth**
(App Service built-in authentication). The MCP server code itself does NOT need to validate
tokens — the platform does this before the request reaches `server.py`.

This platform-level auth implements the requirements of the
[MCP authorization specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization),
including:
- Issuing proper **`401` challenge** responses to unauthenticated clients.
- Exposing the **Protected Resource Metadata (PRM)** document at `/.well-known/oauth-protected-resource`.
- Redirecting unauthenticated clients to the configured identity provider (Entra ID).

MCP clients that implement the MCP auth spec (e.g., VS Code Copilot, Claude Desktop with auth
support) will automatically handle the OAuth flow when they receive the 401 challenge.

**How it works:**
1. Client sends request without or with an invalid Bearer token.
2. EasyAuth returns `401` with a `WWW-Authenticate` header pointing to the PRM document.
3. Client follows the OAuth flow against Entra ID and obtains a token.
4. Client resends request with valid Bearer token — EasyAuth validates and forwards to MCP server.

**Pre-authorized client IDs** are configured at deployment time:
```bash
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings PRE_AUTHORIZED_CLIENT_IDS=<client-id>
```

This allows specific apps (e.g., VS Code `aebc6443-996d-45c2-90f0-388ff96faa56`, Copilot Studio)
to authenticate without additional consent prompts.

### APIM (Optional — Internal VNET Mode)

If API Management sits in front of the Function App (internal VNET mode):
- APIM handles the public-facing auth, rate limiting, and routing.
- The Function App is not publicly accessible.
- Pass `x-functions-key` as an internal header for Function-level auth between APIM and Functions.
- The MCP server code is unaware of APIM — all of this is infrastructure configuration.

### Azure API Center (Optional)

MCP servers hosted on Azure Functions can be registered in **Azure API Center** to create a
private organizational tool catalog. This enables consistent governance and discoverability of
MCP servers across your organization. Registration is done separately from deployment — it does
not affect `server.py` or `host.json`.

---

## Dependency Management

This project uses **uv** for Python package management (not pip directly).

### Adding a dependency

```bash
uv add <package-name>
```

Always run `uv lock` after adding dependencies to update `uv.lock`.

### Running locally

```bash
uv run func start
```

This command:
1. Creates/updates the virtual environment.
2. Installs all dependencies from `pyproject.toml`.
3. Starts the Azure Functions host, which in turn launches `server.py`.

### `pyproject.toml` requirements

```toml
[project]
requires-python = ">=3.11"

[tool.uv]
# Dependencies should include at minimum:
dependencies = [
  "mcp[cli]",         # Anthropic MCP Python SDK (includes FastMCP)
  "httpx",            # Async HTTP client for outbound API calls
  "azure-identity",   # For Managed Identity / credential chaining
]
```

---

## Deployment

### Deploy to Azure

```bash
az login
az group create --name <resource-group> --location <region>
az storage account create \
  --name <storage-account> \
  --resource-group <resource-group> \
  --location <region> \
  --sku Standard_LRS \
  --allow-blob-public-access false
az functionapp create \
  --resource-group <resource-group> \
  --name <function-app-name> \
  --storage-account <storage-account> \
  --flexconsumption-location <region> \
  --runtime python \
  --runtime-version 3.11
```

Configure the custom handler settings:

```bash
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings \
    AzureWebJobsFeatureFlags=EnableMcpCustomHandlerPreview \
    CUSTOM_HANDLER_PORT=8000 \
    PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages
```

Do not add `FUNCTIONS_WORKER_RUNTIME` to Azure app settings on Flex Consumption. The runtime is set when the app is created with `--runtime python --runtime-version 3.11`. Keep `FUNCTIONS_WORKER_RUNTIME=python` only in `local.settings.json` for local `func start`.
Do not add `SCM_DO_BUILD_DURING_DEPLOYMENT` or `ENABLE_ORYX_BUILD` to Azure app settings on Flex Consumption. Request remote build with the deployment command's `--build-remote true` flag instead.

Deploy code from the repository root:

```bash
git archive --format zip --output deploy.zip HEAD
az functionapp deployment source config-zip \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --src deploy.zip \
  --build-remote true
```

Subsequent code-only updates can recreate `deploy.zip` and rerun the same deployment command.

### Flex Consumption Plan

The Function App runs on the **Flex Consumption plan**:
- Pay-per-execution billing model.
- Supports bursty, serverless scale.
- Required for the streamable-http MCP transport pattern.
- Cold starts are possible — design tools to be stateless and tolerant of cold starts.

### Environment Variables in Azure

Set app settings via:
```bash
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings KEY=VALUE
```

Keep production settings in Azure App Settings. Keep local-only settings in `local.settings.json`.

---

## MCP Endpoint URLs

| Context | URL Pattern |
|---|---|
| Local development | `http://localhost:7071/mcp` |
| Remote (Azure) | `https://<funcappname>.azurewebsites.net/mcp` |
| Remote with APIM | `https://<apim-name>.azure-api.net/<api-path>/mcp` |

The `/mcp` path is the default streamable-http mount point for FastMCP.

---

## Local Development Workflow

1. Copy `local.settings.json` from template and fill in secrets.
2. Start Azurite if needed for local storage emulation:
   ```bash
   azurite --silent --location .azurite --debug .azurite/debug.log
   ```
3. Start the server:
   ```bash
   uv run func start
   ```
4. Test with MCP Inspector:
   ```bash
   npx @modelcontextprotocol/inspector@latest http://localhost:7071/mcp
   ```
5. Or configure `.vscode/mcp.json` with the `local-mcp-server` block and test via VS Code Copilot.

---

## Platform Limitations (Public Preview)

Be aware of these constraints — do not attempt workarounds that conflict with them:

| Limitation | Detail |
|---|---|
| **Stateless only** | Only stateless MCP servers are supported. Do not attempt to add session state or persistent in-memory state across requests. If you need stateful servers, use the Functions MCP extension instead. |
| **streamable-http only** | SSE transport is not supported for custom handlers on Flex Consumption. |
| **No F5 / debugger launch** | You cannot start the server with `F5` in VS Code. You must use `uv run func start` in the terminal. Breakpoint debugging via the VS Code debugger launch config will not work. |
| **Flex Consumption plan required** | The server must be hosted on a Flex Consumption plan. Consumption, Premium, and Dedicated plans are not supported for this pattern. |
| **No Java quickstart yet** | Java MCP SDK hosting on Functions is not yet available in this pattern. |



## Common Issues and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Red log output on startup | MCP SDK logs to stderr; Functions shows it red | Expected behavior — ignore |
| `404` on root `/` at startup | FastMCP doesn't implement `/` | Expected behavior — the Functions host ping is non-fatal |
| Port mismatch errors | `host.json` port ≠ server listen port | Ensure both are set to `8000` |
| `401` from remote server | EasyAuth rejects client | Verify client app ID is in `PRE_AUTHORIZED_CLIENT_IDS` |
| Client gets `401` but never prompts for login | Client doesn't implement MCP auth spec | Use a compliant client; inspect PRM doc at `/.well-known/oauth-protected-resource` |
| Tools not appearing in client | Server not initialized | Check MCP Inspector → List Tools to verify tool registration |
| `uv: command not found` | uv not installed | Install via `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Cold start timeouts | Flex Consumption cold start | Keep server startup lean; avoid heavy init in module scope |
| F5 / debugger does nothing | VS Code debugger launch not supported in preview | Use `uv run func start` in terminal — F5 is not supported |
| `/api/mcp` returns 404 | Default `/api` prefix not stripped | Confirm `configurationProfile: "mcp-custom-handler"` is set in `host.json` |

---

## What NOT to Change

These patterns must be preserved when modifying or extending the server:

1. **Do not change `configurationProfile`** in `host.json` — it must remain `"mcp-custom-handler"`.
2. **Do not switch transport** in `server.py` — `streamable-http` is required; `stdio` will break
   Azure Functions hosting.
3. **Do not add Azure Functions triggers/bindings** to server code — this is not the Functions MCP
   extension pattern. This repo uses the custom handler (self-hosted SDK) pattern exclusively.
4. **Do not remove `stateless_http=True`** from `FastMCP(...)` — stateful sessions are not
   compatible with the Flex Consumption plan's scale-out behavior.
5. **Do not hardcode secrets** in `server.py` — use environment variables loaded from
   `local.settings.json` locally and Azure App Settings in production. Use `azure-identity`
   with `DefaultAzureCredential` or `ManagedIdentityCredential` for service-to-service auth.

---

## Conventions for This Codebase

- All tools are defined in `server.py` or imported from a `tools/` subpackage.
- All outbound API calls use `httpx.AsyncClient` with appropriate timeouts.
- Credentials are never stored in code — use `DefaultAzureCredential` or environment variables.
- Tool names use `snake_case` matching the Python function name.
- Tool docstrings follow Google-style with an `Args:` section for parameter documentation.
- Logging uses Python's `logging` module (not `print`) with a named logger per module.
- Error responses from tools return a human-readable error string, not exceptions.
