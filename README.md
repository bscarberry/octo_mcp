# octo-mcp-server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server built with Python and [FastMCP](https://github.com/jlowin/fastmcp), hosted on **Azure Functions** using the custom handler pattern. It exposes NWS weather tools over `streamable-http` transport and is designed for stateless, serverless deployment on the Flex Consumption plan.

## Available tools

| Tool | Description |
|------|-------------|
| `echo` | Returns a message unchanged — useful for testing connectivity |
| `get_weather_forecast` | 7-day or hourly NWS forecast for any US lat/lon |
| `get_current_conditions` | Live conditions from the nearest NWS observation station |
| `get_weather_alerts` | Active NWS alerts for a US state (two-letter abbreviation) |

All tools call the public [National Weather Service API](https://www.weather.gov/documentation/services-web-api) — no API key required. US locations only.

---

## Project structure

```
server.py                    # FastMCP server — all tools defined here
host.json                    # Azure Functions custom handler config (required)
local.settings.example.json  # Template — copy to local.settings.json for local dev
pyproject.toml               # Python project metadata and dependencies (uv)
azure.yaml                   # Azure Developer CLI (azd) project config
Dockerfile                   # Container image (optional; azd deploy preferred)
```

---

## Local development

### 1. Install prerequisites

All four tools below must be installed before continuing.

#### Python 3.11+

Verify: `python --version` should print `3.11.x` or higher.

- Windows: download from [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.11`
- macOS: `brew install python@3.11`

#### uv (Python package manager)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify: `uv --version`

#### Azure Functions Core Tools v4

```bash
# macOS
brew tap azure/functions && brew install azure-functions-core-tools@4

# Windows (winget)
winget install Microsoft.AzureFunctionsCoreTools

# npm (any platform)
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

Verify: `func --version` should print `4.x.x`

#### Azurite (local Azure Storage emulator)

```bash
npm install -g azurite
```

Verify: `azurite --version`

Node.js 18+ is required for both `npx` and Azurite. Download from [nodejs.org](https://nodejs.org/) if needed.

---

### 2. Clone and set up the project

```bash
git clone <repo-url>
cd octo_mcp
```

Copy the settings template:

```bash
# macOS / Linux
cp local.settings.example.json local.settings.json

# Windows (Command Prompt)
copy local.settings.example.json local.settings.json

# Windows (PowerShell)
Copy-Item local.settings.example.json local.settings.json
```

`local.settings.json` is git-ignored and never committed. It holds secrets and local environment configuration.

If you add tools that require API keys, add them under `Values` in `local.settings.json`:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "custom",
    "CUSTOM_HANDLER_PORT": "8000",
    "MY_API_KEY": "your_key_here"
  }
}
```

---

### 3. Start Azurite (storage emulator)

The Functions host requires a storage backend, even locally. Open a **separate terminal** and run:

```bash
azurite --silent --location .azurite --debug .azurite/debug.log
```

Leave this terminal running while you develop. The `.azurite/` directory is git-ignored.

---

### 4. Start the server

```bash
uv run func start
```

This command:
1. Creates/updates the `.venv` virtual environment automatically
2. Installs all dependencies from `pyproject.toml`
3. Starts the Azure Functions host on port 7071
4. Launches `server.py` as the custom handler on port 8000

**Expected startup output:**

```
Azure Functions Core Tools
Core Tools Version: 4.x.x
...
[2024-...] Host initialized (XXXms)
[2024-...] Host started (XXXms)
[2024-...] Job host started
```

You will also see red-colored log lines from the MCP SDK and a `404` on the root path — both are **expected and harmless**:

- Red log lines: the MCP SDK writes to `stderr`, which Functions renders in red. Cosmetic only.
- `404` on `/`: the Functions host pings `/` on startup. FastMCP doesn't implement `/`, so it returns 404. This is not an error.

The MCP endpoint is now live at: `http://localhost:7071/mcp`

---

### 5. Test the server

#### Option A — MCP Inspector (browser UI)

```bash
npx @modelcontextprotocol/inspector@latest http://localhost:7071/mcp
```

Open the URL printed by the inspector, click **Connect**, then **List Tools** to verify all four tools appear.

#### Option B — Claude Code (CLI)

```bash
claude mcp add --transport http octo-mcp-local http://localhost:7071/mcp
```

This registers the server at the project scope. Run it from inside the `octo_mcp` directory. Tools will be available in any Claude Code session started from this project.

#### Option C — Claude Desktop

Claude Desktop only supports stdio transport natively. Use `mcp-remote` (requires Node.js) as a bridge — it runs as a local stdio proxy that forwards to the HTTP server.

Edit the Claude Desktop config file:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the server under `mcpServers`:

```json
{
  "mcpServers": {
    "octo-mcp-local": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:7071/mcp"]
    }
  }
}
```

Restart Claude Desktop after saving. The tools will appear in the tool picker in any conversation. The MCP server must be running (`uv run func start`) before Claude Desktop can connect.

#### Option D — VS Code Copilot

Create or update `.vscode/mcp.json` in the repository root:

```json
{
  "servers": {
    "local-octo-mcp": {
      "type": "http",
      "url": "http://localhost:7071/mcp"
    }
  }
}
```

In VS Code, open the Copilot chat panel, switch to **Agent** mode, and the tools will appear in the tool picker.

#### Option E — curl (quick connectivity check)

```bash
curl -X POST http://localhost:7071/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

### 6. Add a new tool

All tools live in `server.py`. Add a decorated async function:

```python
@mcp.tool()
async def my_tool(input: str) -> str:
    """
    Description shown to the MCP client.

    Args:
        input: Description of the parameter.
    """
    result = await call_some_api(input)
    return str(result)
```

Rules:
- Always include a docstring with an `Args:` section — this becomes the tool's schema.
- Type-hint all parameters — they generate the JSON schema.
- Use `async def` for any I/O calls.
- Catch exceptions and return error strings — never let tools raise unhandled exceptions.
- Return `str` or a JSON-serializable type.

Restart `uv run func start` after adding tools.

---

## Deploy to Azure

### Prerequisites

- [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd):
  ```bash
  # macOS
  brew tap azure/azd && brew install azd

  # Windows (winget)
  winget install Microsoft.Azd

  # Script
  curl -fsSL https://aka.ms/install-azd.sh | bash   # macOS/Linux
  powershell -ex AllSigned -c "Invoke-RestMethod 'https://aka.ms/install-azd.ps1' | Invoke-Expression"  # Windows
  ```
  Verify: `azd version`

- An Azure subscription with permission to create resources (Contributor or Owner role)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) (optional but useful for post-deploy config):
  ```bash
  winget install Microsoft.AzureCLI   # Windows
  brew install azure-cli              # macOS
  ```

### Deploy

```bash
azd auth login
azd up
```

`azd up` will:
1. Prompt you to select an Azure subscription and region
2. Provision a **Flex Consumption** Function App, Storage Account, and App Service Plan
3. Deploy the application code

This takes 3–5 minutes on first run. You will see the deployed Function App URL at the end.

For code-only updates (after infrastructure is already provisioned):

```bash
azd deploy
```

### Required App Setting after deploy

The custom handler pattern requires `FUNCTIONS_WORKER_RUNTIME=custom` in Azure, not `python`. This is correct — it tells the Functions host to proxy HTTP to your process rather than use the built-in Python worker. Your Python code still runs; the host just doesn't manage it through the language worker.

Set this immediately after `azd up`:

```bash
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings FUNCTIONS_WORKER_RUNTIME=custom
```

### Set additional environment variables in Azure

For tools that require API keys or secrets, set them as App Settings:

```bash
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings MY_API_KEY=your_value
```

You can find `<function-app-name>` and `<resource-group>` in the `azd` output or in the Azure Portal.

Access them in `server.py` via `os.environ`:

```python
import os
MY_API_KEY = os.environ.get("MY_API_KEY", "")
```

### MCP endpoint URLs

| Context | URL |
|---------|-----|
| Local | `http://localhost:7071/mcp` |
| Azure | `https://<funcappname>.azurewebsites.net/mcp` |

### Connect MCP clients to the deployed server

Replace `<funcappname>` with your actual Function App name from the `azd up` output.

#### Claude Code (CLI)

```bash
claude mcp add --transport http octo-mcp-azure https://<funcappname>.azurewebsites.net/mcp
```

To switch between local and Azure within the same project, use different names (`octo-mcp-local` vs `octo-mcp-azure`) so both can coexist. List registered servers with:

```bash
claude mcp list
```

Remove a server with:

```bash
claude mcp remove octo-mcp-azure
```

#### Claude Desktop

Same bridge approach as local — `mcp-remote` proxies stdio to the Azure HTTP endpoint:

```json
{
  "mcpServers": {
    "octo-mcp-azure": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<funcappname>.azurewebsites.net/mcp"]
    }
  }
}
```

Restart Claude Desktop after saving. No local server needs to be running — `mcp-remote` connects directly to Azure.

#### VS Code Copilot

Update `.vscode/mcp.json`:

```json
{
  "servers": {
    "octo-mcp-azure": {
      "type": "http",
      "url": "https://<funcappname>.azurewebsites.net/mcp"
    }
  }
}
```

---

## Architecture

```
MCP Client (VS Code Copilot / Claude Desktop / MCP Inspector)
    │
    ▼ HTTP POST (streamable-http)
Azure Functions Host  (port 7071 locally)
    │  custom handler proxy
    ▼
FastMCP Server Process  (server.py on port 8000)
    │
    ▼
National Weather Service API (api.weather.gov)
```

Key design decisions:

- **Custom handler pattern**: Azure Functions acts as a managed HTTP host and proxies all requests to the FastMCP process. No Azure Functions triggers or bindings are used in `server.py`.
- **`configurationProfile: "mcp-custom-handler"`** in `host.json`: strips the `/api` prefix, enables full HTTP proxying, and sets auth to anonymous (EasyAuth handles auth at the platform layer in production).
- **`stateless_http=True`**: required for Flex Consumption plan scale-out. Do not remove this.
- **`transport="streamable-http"`**: required for Azure Functions hosting. Do not switch to `stdio` or `sse`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `404` on `/` at startup | Functions pings `/`; FastMCP doesn't implement it | Expected — not an error |
| Red log output on startup | MCP SDK logs to `stderr`; Functions colors it red | Expected — cosmetic only |
| `func: command not found` | Azure Functions Core Tools not installed | Install v4 (see prerequisites) |
| `uv: command not found` | uv not installed | Install uv (see prerequisites) |
| Port already in use (8000 or 7071) | Another process is running on those ports | Kill the process or change ports in `host.json` and `local.settings.json` |
| `Routes configuration is only allowed for worker runtime: custom` | `FUNCTIONS_WORKER_RUNTIME` set to `python` | Set to `custom` in `local.settings.json` (local) and Azure App Settings (deployed) |
| `AzureWebJobsStorage` connection error | Azurite not running | Start Azurite in a separate terminal |
| Claude Desktop: "not valid MCP server configurations" | Claude Desktop doesn't support `"type": "http"` directly | Use `mcp-remote` bridge — see Claude Desktop instructions above |
| Tools not appearing in client | Server not initialized or wrong URL | Check MCP Inspector → List Tools; verify URL ends in `/mcp` |
| `/api/mcp` returns 404 | Default `/api` prefix not stripped | Ensure `configurationProfile: "mcp-custom-handler"` is set in `host.json` |
| `azd up` fails on first run | Missing permissions or subscription not set | Run `azd auth login` and confirm the right subscription |
| Cold start timeouts (Azure) | Flex Consumption cold start | Keep `server.py` module-level init minimal |

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CUSTOM_HANDLER_PORT` | `8000` | Port the FastMCP server binds to — must match `host.json` |
| `AzureWebJobsStorage` | `UseDevelopmentStorage=true` | Storage connection string (Azurite locally; real account in Azure) |
| `FUNCTIONS_WORKER_RUNTIME` | `python` | Required by the Functions host |

Add tool-specific secrets (API keys, connection strings) to `local.settings.json` under `Values` for local dev, and as Azure App Settings for production. Never commit secrets to source control.
