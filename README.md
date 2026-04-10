# octo-mcp-server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server built with Python and [FastMCP](https://github.com/anthropics/python-sdk), hosted on **Azure Functions** using the custom handler pattern. It uses the `streamable-http` transport and is designed for stateless, serverless deployment on the Flex Consumption plan.

## Project structure

```
server.py              # FastMCP server — all tools defined here
host.json              # Azure Functions custom handler config (required)
pyproject.toml         # Python project metadata and dependencies (uv)
azure.yaml             # Azure Developer CLI (azd) project config
.env.example           # Template for local.settings.json
Dockerfile             # Container image (optional; azd deploy preferred)
infra/                 # Bicep IaC for provisioning Azure resources (optional)
```

## Adding a new tool

Add a decorated function to `server.py`:

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

That's it — FastMCP registers the tool automatically.

## Local development

### Prerequisites

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local)
- (Optional) [Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite) for local storage emulation

### Setup

1. Create `local.settings.json` from the example:

```bash
cp .env.example local.settings.json
```

`local.settings.json` is gitignored and never committed.

2. Start the server:

```bash
uv run func start
```

The MCP server starts on `http://localhost:7071`. The Azure Functions host proxies all requests to the FastMCP process on port 8000.

### Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector@latest http://localhost:7071/mcp
```

### Configure VS Code Copilot

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "local-mcp-server": {
      "type": "http",
      "url": "http://localhost:7071/mcp"
    }
  }
}
```

## Deploy to Azure

### Prerequisites

- [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
- An Azure subscription

### Deploy

```bash
azd auth login
azd up
```

`azd up` provisions all infrastructure and deploys the Function App code. For code-only updates:

```bash
azd deploy
```

### Set environment variables in Azure

```bash
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings MY_API_KEY=your_value
```

### MCP endpoint URLs

| Context | URL |
|---------|-----|
| Local | `http://localhost:7071/mcp` |
| Azure | `https://<funcappname>.azurewebsites.net/mcp` |

## Docker

The Dockerfile is provided for cases where a container image is needed. For standard Azure Functions deployment, use `azd up` instead.

```bash
docker build -t octo-mcp-server .
docker run -p 8000:8000 octo-mcp-server
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CUSTOM_HANDLER_PORT` | `8000` | Port the FastMCP server listens on — must match `host.json` |

Add tool-specific secrets (API keys, connection strings) to `local.settings.json` under `Values` for local dev, and as Azure App Settings for production.

## Architecture notes

- Azure Functions acts as a managed host — it proxies all HTTP traffic to the FastMCP process running on port 8000.
- The `configurationProfile: "mcp-custom-handler"` in `host.json` configures route proxying, removes the `/api` prefix, and sets auth to anonymous (auth is handled by EasyAuth at the platform layer).
- A `404` on the root `/` at startup is expected — the Functions host pings `/` but FastMCP doesn't implement it.
- Red log output from the MCP SDK on startup is cosmetic — it writes to `stderr`, which Functions renders in red.
- `stateless_http=True` is required for compatibility with the Flex Consumption plan's scale-out behavior.
