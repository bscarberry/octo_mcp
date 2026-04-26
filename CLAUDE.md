# CLAUDE.md - Azure Functions MCP Extension Project

This repository hosts MCP tools with the Azure Functions MCP extension using the Python v2 programming model.

It does not use FastMCP, a self-hosted MCP SDK server, a custom handler, Docker deployment, or `azd`.

## Architecture

```text
MCP client
  -> /runtime/webhooks/mcp/sse
  -> Azure Functions MCP extension
  -> Python functions in function_app.py
  -> National Weather Service API
```

## Important Files

```text
function_app.py              # MCP tool trigger functions
host.json                    # Experimental extension bundle for MCP
local.settings.example.json  # Local development settings template
requirements.txt             # Azure deployment dependencies
pyproject.toml               # Local uv project metadata
.funcignore                  # Files excluded from deployment packages
README.md                    # PowerShell-only setup and deployment guide
```

## Required Host Configuration

`host.json` must use the experimental extension bundle:

```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  },
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle.Experimental",
    "version": "[4.*, 5.0.0)"
  }
}
```

## Local Settings

`local.settings.json` is local-only and must not be committed:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python"
  }
}
```

## Tool Pattern

Define tools in `function_app.py` with `@app.mcp_tool_trigger`.

```python
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="hello_mcp",
    description="Hello world.",
    tool_properties="[]",
)
def hello_mcp(context) -> str:
    return "Hello I am MCPTool!"
```

Tool arguments arrive as JSON in `context`; parse `json.loads(context)["arguments"]`.

## Endpoint

Local endpoint:

```text
http://localhost:7071/runtime/webhooks/mcp/sse
```

Azure endpoint:

```text
https://<function-app-name>.azurewebsites.net/runtime/webhooks/mcp/sse?code=<mcp_extension_key>
```

The key is in the Azure Portal under:

```text
Functions > App keys > System keys > mcp_extension
```

## Deployment

The README is the source of truth and intentionally contains PowerShell-only commands.

Deployment uses:

```powershell
az functionapp deployment source config-zip `
  --src $ZIP_FILE `
  --name $FUNCTION_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --build-remote true
```

Do not add old custom-handler settings such as:

- `configurationProfile: "mcp-custom-handler"`
- `CUSTOM_HANDLER_PORT`
- `AzureWebJobsFeatureFlags=EnableMcpCustomHandlerPreview`

Do not use the old `/mcp` endpoint. Use `/runtime/webhooks/mcp/sse`.
