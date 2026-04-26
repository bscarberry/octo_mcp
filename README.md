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
requirements.txt             # Azure deployment dependencies
Dockerfile                   # Container image (optional)
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
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableMcpCustomHandlerPreview",
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

- An Azure subscription with permission to create resources (Contributor or Owner role)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli):
  ```bash
  # Windows (winget)
  winget install Microsoft.AzureCLI

  # macOS
  brew install azure-cli

  # Linux
  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
  ```
  Verify: `az version`

- Azure Functions Core Tools v4:
  ```bash
  winget install Microsoft.AzureFunctionsCoreTools   # Windows
  brew tap azure/functions && brew install azure-functions-core-tools@4   # macOS
  ```
  Verify: `func --version`

- A globally unique Function App name. Function App names allow lowercase letters, numbers, and hyphens.

### 1. Sign in and choose a subscription

```bash
az login
az account set --subscription "<subscription-id-or-name>"
```

### 2. Set deployment variables

Bash examples use `\` for line continuation and `$VARIABLE` syntax. PowerShell examples use argument arrays (`@(...)`) and `az @args` to avoid fragile backtick line continuations. Backtick continuations also work in PowerShell, but a trailing space after a backtick breaks the command in a hard-to-see way.

Bash:

```bash
RESOURCE_GROUP="rg-octo-mcp"
LOCATION="eastus"
STORAGE_ACCOUNT="octomcp$RANDOM"
FUNCTION_APP_NAME="octo-mcp-<unique-suffix>"
```

PowerShell:

```powershell
$RESOURCE_GROUP = "rg-octo-mcp"
$LOCATION = "eastus"
$STORAGE_ACCOUNT = "octomcp$(Get-Random)"
$FUNCTION_APP_NAME = "octo-mcp-<unique-suffix>"
```

### 3. Create Azure resources

This creates a resource group, storage account, and Python Function App in the Flex Consumption plan.

Bash:

```bash
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --allow-blob-public-access false

az functionapp create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$FUNCTION_APP_NAME" \
  --storage-account "$STORAGE_ACCOUNT" \
  --flexconsumption-location "$LOCATION" \
  --runtime python \
  --runtime-version 3.11
```

PowerShell:

```powershell
$groupArgs = @(
  "group", "create",
  "--name", $RESOURCE_GROUP,
  "--location", $LOCATION
)
az @groupArgs

$storageArgs = @(
  "storage", "account", "create",
  "--name", $STORAGE_ACCOUNT,
  "--resource-group", $RESOURCE_GROUP,
  "--location", $LOCATION,
  "--sku", "Standard_LRS",
  "--allow-blob-public-access", "false"
)
az @storageArgs

$functionArgs = @(
  "functionapp", "create",
  "--resource-group", $RESOURCE_GROUP,
  "--name", $FUNCTION_APP_NAME,
  "--storage-account", $STORAGE_ACCOUNT,
  "--flexconsumption-location", $LOCATION,
  "--runtime", "python",
  "--runtime-version", "3.11"
)
az @functionArgs
```

Use `az functionapp list-flexconsumption-locations -o table` if you need to find a region that supports Flex Consumption.

### 4. Configure required app settings

For this MCP hosting pattern, keep the MCP custom-handler profile enabled in `host.json` (`configurationProfile: "mcp-custom-handler"`). The custom handler preview flag is also required in Azure.

Do not set `FUNCTIONS_WORKER_RUNTIME` as an Azure app setting on Flex Consumption. The runtime is configured when the Function App is created with `az functionapp create --runtime python --runtime-version 3.11`. `FUNCTIONS_WORKER_RUNTIME=python` is still used in `local.settings.json` for local development, but Flex Consumption rejects it in Azure app settings.

Bash:

```bash
az functionapp config appsettings set \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --settings \
    AzureWebJobsFeatureFlags=EnableMcpCustomHandlerPreview \
    CUSTOM_HANDLER_PORT=8000 \
    PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages
```

PowerShell:

```powershell
$appSettingsArgs = @(
  "functionapp", "config", "appsettings", "set",
  "--name", $FUNCTION_APP_NAME,
  "--resource-group", $RESOURCE_GROUP,
  "--settings",
  "AzureWebJobsFeatureFlags=EnableMcpCustomHandlerPreview",
  "CUSTOM_HANDLER_PORT=8000",
  "PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages"
)
az @appSettingsArgs
```

Do not set `SCM_DO_BUILD_DURING_DEPLOYMENT` or `ENABLE_ORYX_BUILD` as Azure app settings on Flex Consumption. Build dependencies locally in Linux with Docker for the most reliable deployment path, or request Azure remote build with the deployment command's `--build-remote true` flag.

If you already tried to set `FUNCTIONS_WORKER_RUNTIME` and need to clean it up, run:

Bash:

```bash
az functionapp config appsettings delete \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --setting-names FUNCTIONS_WORKER_RUNTIME
```

PowerShell:

```powershell
$deleteRuntimeArgs = @(
  "functionapp", "config", "appsettings", "delete",
  "--name", $FUNCTION_APP_NAME,
  "--resource-group", $RESOURCE_GROUP,
  "--setting-names", "FUNCTIONS_WORKER_RUNTIME"
)
az @deleteRuntimeArgs
```

If you already set the unsupported remote-build app settings, remove them before deploying:

Bash:

```bash
az functionapp config appsettings delete \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --setting-names SCM_DO_BUILD_DURING_DEPLOYMENT ENABLE_ORYX_BUILD
```

PowerShell:

```powershell
$deleteBuildSettingsArgs = @(
  "functionapp", "config", "appsettings", "delete",
  "--name", $FUNCTION_APP_NAME,
  "--resource-group", $RESOURCE_GROUP,
  "--setting-names", "SCM_DO_BUILD_DURING_DEPLOYMENT", "ENABLE_ORYX_BUILD"
)
az @deleteBuildSettingsArgs
```

Validate that the Function App was created with the Python runtime:

```bash
az functionapp show \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "{runtime: siteConfig.linuxFxVersion, kind: kind}" -o json
```

For tools that require API keys or secrets, set them as App Settings:

Bash:

```bash
az functionapp config appsettings set \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --settings MY_API_KEY=your_value
```

PowerShell:

```powershell
$secretArgs = @(
  "functionapp", "config", "appsettings", "set",
  "--name", $FUNCTION_APP_NAME,
  "--resource-group", $RESOURCE_GROUP,
  "--settings", "MY_API_KEY=your_value"
)
az @secretArgs
```

Access them in `server.py` via `os.environ`:

```python
import os
MY_API_KEY = os.environ.get("MY_API_KEY", "")
```

### 5. Deploy the code

Keep `requirements.txt` in sync with `pyproject.toml` when dependencies change.

The most reliable path for Flex Consumption is to build Linux-compatible Python dependencies into `.python_packages/lib/site-packages`, include that folder in the zip, and deploy without Azure remote build. This avoids current Oryx remote-build failures such as `/tmp/oryx/platforms/python/<version>/bin/pip: cannot execute: required file not found`.

#### 5a. Build dependencies for Linux

From Windows PowerShell, use Docker so native wheels are built for Linux, not Windows:

```powershell
Remove-Item .python_packages -Recurse -Force -ErrorAction SilentlyContinue
docker run --rm `
  -v "${PWD}:/workspace" `
  -w /workspace `
  python:3.12-slim `
  sh -c "python -m pip install --upgrade pip && python -m pip install --target .python_packages/lib/site-packages -r requirements.txt"
```

Bash:

```bash
rm -rf .python_packages
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  python:3.12-slim \
  sh -c "python -m pip install --upgrade pip && python -m pip install --target .python_packages/lib/site-packages -r requirements.txt"
```

Use a Docker image that matches the Function App runtime, such as `python:3.11-slim` for Python 3.11 or `python:3.12-slim` for Python 3.12.

#### 5b. Create a deployment zip

Bash:

```bash
zip -r deploy.zip . \
  -x ".venv/*" ".azurite/*" ".git/*" "local.settings.json" "__pycache__/*" "*.pyc" "deploy.zip"
```

PowerShell:

```powershell
$exclude = @(".venv", ".azurite", ".git", "local.settings.json", "__pycache__", "deploy.zip")
Get-ChildItem -Force |
  Where-Object { $exclude -notcontains $_.Name } |
  Compress-Archive -DestinationPath deploy.zip -Force
```

Confirm the package includes both app files and dependencies:

```powershell
tar -tf deploy.zip | Select-String "requirements.txt|server.py|.python_packages"
```

#### 5c. Deploy without remote build

Bash:

```bash
az functionapp deployment source config-zip \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --src deploy.zip
```

PowerShell:

```powershell
$deployArgs = @(
  "functionapp", "deployment", "source", "config-zip",
  "--name", $FUNCTION_APP_NAME,
  "--resource-group", $RESOURCE_GROUP,
  "--src", "deploy.zip"
)
az @deployArgs
```

Recreate `deploy.zip` and re-run the same `az functionapp deployment source config-zip` command for code-only updates.

If you prefer Azure remote build, omit `.python_packages` from the zip and add `--build-remote true` to the deploy command. If Oryx fails with `/tmp/oryx/platforms/python/<version>/bin/pip: cannot execute: required file not found`, use the local Linux dependency build above instead.

### 6. Verify the deployment

Bash:

```bash
az functionapp show \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "defaultHostName" -o tsv

curl -X POST "https://${FUNCTION_APP_NAME}.azurewebsites.net/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

PowerShell:

```powershell
$showArgs = @(
  "functionapp", "show",
  "--name", $FUNCTION_APP_NAME,
  "--resource-group", $RESOURCE_GROUP,
  "--query", "defaultHostName",
  "-o", "tsv"
)
az @showArgs

Invoke-RestMethod `
  -Method Post `
  -Uri "https://$FUNCTION_APP_NAME.azurewebsites.net/mcp" `
  -ContentType "application/json" `
  -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

To view logs while testing:

```bash
az webapp log tail \
  --name "$FUNCTION_APP_NAME" \
  --resource-group "$RESOURCE_GROUP"
```

### MCP endpoint URLs

| Context | URL |
|---------|-----|
| Local | `http://localhost:7071/mcp` |
| Azure | `https://<funcappname>.azurewebsites.net/mcp` |

### Connect MCP clients to the deployed server

Replace `<funcappname>` with your actual Function App name.

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
| `FUNCTIONS_WORKER_RUNTIME` is invalid on Flex Consumption | Flex Consumption does not allow `FUNCTIONS_WORKER_RUNTIME` as an Azure app setting | Delete that app setting; the runtime is set by `az functionapp create --runtime python --runtime-version 3.11` |
| `WorkerConfig for runtime: custom not found` | A non-Flex Python Function App was configured with `FUNCTIONS_WORKER_RUNTIME=custom` | For non-Flex apps, use `FUNCTIONS_WORKER_RUNTIME=python`; for Flex Consumption, do not set it as an app setting |
| `AzureWebJobsStorage` connection error | Azurite not running | Start Azurite in a separate terminal |
| Claude Desktop: "not valid MCP server configurations" | Claude Desktop doesn't support `"type": "http"` directly | Use `mcp-remote` bridge — see Claude Desktop instructions above |
| Tools not appearing in client | Server not initialized or wrong URL | Check MCP Inspector → List Tools; verify URL ends in `/mcp` |
| `/api/mcp` returns 404 | Default `/api` prefix not stripped | Ensure `configurationProfile: "mcp-custom-handler"` is set in `host.json` |
| `az functionapp create` fails for Flex Consumption | Region or Azure CLI version does not support Flex Consumption | Run `az functionapp list-flexconsumption-locations -o table` and update Azure CLI |
| `The system cannot find the file specified` from `az functionapp create` on Windows | Azure CLI install/path issue or a missing bundled executable; if the one-line command fails too, this is not a PowerShell continuation problem | Run the Windows Azure CLI checks below, then repair or upgrade Azure CLI |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` or `ENABLE_ORYX_BUILD` is invalid on Flex Consumption | These remote-build app settings are not supported with this SKU | Delete both app settings; use the Docker-built `.python_packages` deployment path or deploy with `--build-remote true` without those app settings |
| Oryx fails with `/tmp/oryx/platforms/python/<version>/bin/pip: cannot execute` | Azure remote build image failure before app code runs | Build dependencies locally in Linux with Docker, include `.python_packages` in `deploy.zip`, and deploy without `--build-remote` |
| Zip deployment succeeds but dependencies are missing | Python dependencies were not included in the zip and remote build was not used | Confirm `deploy.zip` contains `.python_packages/lib/site-packages`, or retry Azure remote build with `--build-remote true` |
| Cold start timeouts (Azure) | Flex Consumption cold start | Keep `server.py` module-level init minimal |

### Windows Azure CLI checks

If `az functionapp create` fails in PowerShell with `The system cannot find the file specified`, first run the command as a single line to rule out continuation syntax:

```powershell
az functionapp create --resource-group $RESOURCE_GROUP --name $FUNCTION_APP_NAME --storage-account $STORAGE_ACCOUNT --flexconsumption-location $LOCATION --runtime python --runtime-version 3.11
```

If the one-line command still fails, check the local Azure CLI installation:

```powershell
Get-Command az | Format-List Source,CommandType
where.exe az
Test-Path "C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe"
az version
az functionapp list-flexconsumption-locations -o table
```

For the MSI/winget install, `az` usually resolves to:

```text
C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd
```

That wrapper must be able to launch:

```text
C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe
```

If `python.exe` is missing, `az version` fails, or the Flex Consumption command still throws the file error, repair or update Azure CLI:

```powershell
winget upgrade Microsoft.AzureCLI
```

If upgrade does not fix it:

```powershell
winget uninstall Microsoft.AzureCLI
winget install Microsoft.AzureCLI
```

To capture the exact failing Azure CLI operation:

```powershell
az functionapp create --resource-group $RESOURCE_GROUP --name $FUNCTION_APP_NAME --storage-account $STORAGE_ACCOUNT --flexconsumption-location $LOCATION --runtime python --runtime-version 3.11 --debug 2>&1 | Tee-Object az-functionapp-create-debug.log
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CUSTOM_HANDLER_PORT` | `8000` | Port the FastMCP server binds to — must match `host.json` |
| `AzureWebJobsStorage` | `UseDevelopmentStorage=true` | Storage connection string (Azurite locally; real account in Azure) |
| `FUNCTIONS_WORKER_RUNTIME` | `python` | Local-only setting for `local.settings.json`; do not add it to Azure app settings on Flex Consumption |

Add tool-specific secrets (API keys, connection strings) to `local.settings.json` under `Values` for local dev, and as Azure App Settings for production. Never commit secrets to source control.

---

## Deploy from a source repository

Provision Azure once with the Azure CLI commands above. After the Function App exists, use your source host to publish code updates to that same app.

### GitHub Actions

#### 1. Push this repo to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<org-or-user>/<repo>.git
git push -u origin main
```

#### 2. Create an Azure service principal

```bash
az ad sp create-for-rbac \
  --name "octo-mcp-github-deploy" \
  --role contributor \
  --scopes "/subscriptions/<subscription-id>/resourceGroups/<resource-group>" \
  --sdk-auth
```

Add the JSON output as a GitHub Actions secret named `AZURE_CREDENTIALS`. Also add repository variables named `AZURE_FUNCTIONAPP_NAME` and `AZURE_RESOURCE_GROUP`.

#### 3. Add a workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy Azure Function

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Create deployment package
        run: |
          python -m pip install --upgrade pip
          python -m pip install --target .python_packages/lib/site-packages -r requirements.txt
          zip -r deploy.zip . \
            -x ".venv/*" ".azurite/*" ".git/*" "local.settings.json" "__pycache__/*" "*.pyc"

      - name: Deploy
        run: |
          az functionapp deployment source config-zip \
            --name "${{ vars.AZURE_FUNCTIONAPP_NAME }}" \
            --resource-group "${{ vars.AZURE_RESOURCE_GROUP }}" \
            --src deploy.zip
```

#### 4. Day-2 workflow

For future changes:

```bash
git add .
git commit -m "Describe change"
git push
```

Push triggers GitHub Actions deployment automatically.

---

### Azure DevOps Pipelines

Use this when your code is in Azure DevOps and you want pipeline-based deployment with Azure CLI.

#### 1. Import/push the repo to Azure Repos

Use Azure DevOps UI (**Repos → Import**) or standard git remote push:

```bash
git remote add azuredevops https://dev.azure.com/<org>/<project>/_git/<repo>
git push -u azuredevops main
```

#### 2. Create a pipeline service connection

In Azure DevOps, create an Azure Resource Manager service connection scoped to the resource group that contains the Function App.

#### 3. Add a pipeline

Create `azure-pipelines.yml`:

```yaml
trigger:
  - main

pool:
  vmImage: ubuntu-latest

steps:
  - task: AzureCLI@2
    inputs:
      azureSubscription: "<service-connection-name>"
      scriptType: bash
      scriptLocation: inlineScript
      inlineScript: |
        python -m pip install --upgrade pip
        python -m pip install --target .python_packages/lib/site-packages -r requirements.txt
        zip -r "$(Build.ArtifactStagingDirectory)/deploy.zip" . \
          -x ".venv/*" ".azurite/*" ".git/*" "local.settings.json" "__pycache__/*" "*.pyc"
        az functionapp deployment source config-zip \
          --name "<function-app-name>" \
          --resource-group "<resource-group>" \
          --src "$(Build.ArtifactStagingDirectory)/deploy.zip"
```

#### 4. Day-2 workflow

```bash
git add .
git commit -m "Describe change"
git push
```

Push triggers Azure Pipelines deployment automatically.

---

### Validation checklist (dev → deploy)

Before enabling CI/CD:

1. Local run succeeds: `uv run func start`
2. Tool discovery succeeds: MCP Inspector → `List Tools`
3. One-time cloud deploy succeeds: `az functionapp deployment source config-zip`
4. Cloud endpoint responds: `https://<funcappname>.azurewebsites.net/mcp`
5. Runtime is correct in Azure: `siteConfig.linuxFxVersion` shows Python 3.11, and `FUNCTIONS_WORKER_RUNTIME` is not present in Azure app settings on Flex Consumption

This sequence is the shortest reliable path from local development to repeatable production deployment for this repo.
