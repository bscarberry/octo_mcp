# octo-mcp-server

A Python MCP server hosted with the Azure Functions MCP extension. The app exposes National Weather Service tools through Azure Functions MCP tool triggers.

This repository follows the Azure Functions MCP extension model, not the self-hosted custom-handler model.

## Tools

| Tool | Description |
|------|-------------|
| `echo` | Returns a message unchanged |
| `get_weather_forecast` | Gets a NWS forecast for a US latitude and longitude |
| `get_current_conditions` | Gets current NWS observations for a US latitude and longitude |
| `get_weather_alerts` | Gets active NWS alerts for a two-letter US state |

The weather tools use the public National Weather Service API. No API key is required, but locations must be in the United States.

## Project Structure

```text
function_app.py              # Azure Functions MCP tool triggers
host.json                    # Azure Functions host config with experimental MCP extension bundle
local.settings.example.json  # Local settings template; copy to local.settings.json
requirements.txt             # Azure deployment dependencies
pyproject.toml               # Local uv project metadata
.funcignore                  # Files excluded from deployment packages
README.md
```

The important files for this deployment model are:

- `function_app.py`
- `host.json`
- `local.settings.json`
- `requirements.txt`
- `.funcignore`

## Azure Setup

Create the Function App in the Azure Portal.

Use these settings:

| Setting | Value |
|---------|-------|
| Hosting plan | Flex Consumption |
| Operating system | Linux |
| Instance memory | 512 MB is fine for this sample |
| Runtime stack | Python |
| Python version | 3.11 or 3.12 |
| Storage | Create or select an Azure Storage account |
| Application Insights | Recommended |
| Authentication level | Function |

After creating the app, confirm the Overview page shows:

- A domain like `<your-function-name>.azurewebsites.net`
- Linux as the operating system
- Flex Consumption as the plan

## Local Setup

Install prerequisites:

- Python 3.11 or 3.12
- Azure Functions Core Tools v4
- Azure CLI
- uv
- Node.js
- Podman or Docker

Copy local settings:

```powershell
Copy-Item local.settings.example.json local.settings.json
```

Create the Python environment:

```powershell
uv venv
uv pip install -r requirements.txt
```

If you prefer to add packages through uv:

```powershell
uv add azure-functions httpx
```

## Run Local Storage

Azure Functions needs storage even when running locally. This example uses Azurite through Podman.

Start the Podman machine:

```powershell
podman machine start
```

Run Azurite:

```powershell
podman run -d --name azurite `
  -p 10000:10000 `
  -p 10001:10001 `
  -p 10002:10002 `
  mcr.microsoft.com/azure-storage/azurite
```

Check the container:

```powershell
podman ps -a
```

If the container already exists but is stopped:

```powershell
podman start azurite
```

## Run Locally

Start the function host:

```powershell
func start
```

Expected output includes a line similar to:

```text
MCP server SSE endpoint: http://localhost:7071/runtime/webhooks/mcp/sse
```

The local MCP endpoint is:

```text
http://localhost:7071/runtime/webhooks/mcp/sse
```

## Test Locally

Start MCP Inspector:

```powershell
npx @modelcontextprotocol/inspector
```

Open the Inspector URL that prints in the terminal, usually:

```text
http://127.0.0.1:6274
```

Connect to:

```text
http://localhost:7071/runtime/webhooks/mcp/sse
```

Click `List Tools`. You should see the four tools listed above.

## Deploy To Azure

Sign in:

```powershell
az login
```

Set the Function App values:

```powershell
$FUNCTION_APP_NAME = "<your-function-name>"
$RESOURCE_GROUP = "<your-resource-group>"
$ZIP_FILE = "octo-mcp.zip"
```

Create the deployment zip:

```powershell
Remove-Item $ZIP_FILE -Force -ErrorAction SilentlyContinue

$exclude = @(
  ".venv",
  ".git",
  ".vscode",
  ".azurite",
  "local.settings.json",
  "__pycache__",
  $ZIP_FILE
)

Get-ChildItem -Force |
  Where-Object { $exclude -notcontains $_.Name } |
  Compress-Archive -DestinationPath $ZIP_FILE -Force
```

Confirm the zip contains the required files:

```powershell
tar -tf $ZIP_FILE | Select-String "function_app.py|host.json|requirements.txt|.funcignore"
```

Deploy the zip with remote build:

```powershell
az functionapp deployment source config-zip `
  --src $ZIP_FILE `
  --name $FUNCTION_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --build-remote true
```

After deployment, check the Function App in the Azure Portal. Under `Functions`, you should see:

- `echo`
- `get_weather_forecast`
- `get_current_conditions`
- `get_weather_alerts`

## Test In Azure

In the Azure Portal, open the Function App.

Go to:

```text
Functions > App keys
```

Under `System keys`, copy the key named:

```text
mcp_extension
```

The cloud MCP endpoint is:

```text
https://<your-function-name>.azurewebsites.net/runtime/webhooks/mcp/sse?code=<mcp_extension_key>
```

Start MCP Inspector:

```powershell
npx @modelcontextprotocol/inspector
```

Connect to the cloud endpoint above and click `List Tools`.

## Useful PowerShell Commands

View Function App deployment logs:

```powershell
az webapp log tail `
  --name $FUNCTION_APP_NAME `
  --resource-group $RESOURCE_GROUP
```

List app settings:

```powershell
az functionapp config appsettings list `
  --name $FUNCTION_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --output table
```

Restart the Function App:

```powershell
az functionapp restart `
  --name $FUNCTION_APP_NAME `
  --resource-group $RESOURCE_GROUP
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `func: command not found` | Install Azure Functions Core Tools v4 |
| Local storage error | Start Azurite with Podman and confirm `AzureWebJobsStorage` is `UseDevelopmentStorage=true` |
| Tools do not appear locally | Confirm `func start` shows the MCP SSE endpoint |
| Tools do not appear in Azure | Confirm deployment succeeded and the Functions list shows the tool functions |
| Cloud Inspector cannot connect | Confirm the URL includes `/runtime/webhooks/mcp/sse?code=<mcp_extension_key>` |
| `mcp_extension` key missing | Confirm `host.json` uses `Microsoft.Azure.Functions.ExtensionBundle.Experimental` |

## Notes

- Do not set `FUNCTIONS_WORKER_RUNTIME` in Azure app settings for Flex Consumption through CLI commands. The portal/runtime stack config handles the cloud runtime. Keep it in `local.settings.json` for local development.
- Do not use the old `/mcp` endpoint for this repository. The MCP extension endpoint is `/runtime/webhooks/mcp/sse`.
- Do not deploy `local.settings.json`.
