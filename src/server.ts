import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import type { Request, Response } from 'express';

// ── Tool registrations ─────────────────────────────────────────────────────
// Import and call a register* function for each new tool you add.
import { registerEchoTool } from './tools/echo.js';

// ── Session registry ───────────────────────────────────────────────────────
// Maps sessionId → transport so that POST /message can route to the right one.
const sessions = new Map<string, SSEServerTransport>();

/**
 * Creates a new McpServer + SSEServerTransport pair for one SSE connection.
 * Called once per GET /sse request.
 */
export async function createMcpServer(
  _req: Request,
  res: Response,
): Promise<{ server: McpServer; transport: SSEServerTransport }> {
  const server = new McpServer({
    name: 'octo-mcp-server',
    version: '1.0.0',
  });

  // Register all tools here.
  registerEchoTool(server);

  // The client will POST messages to /message?sessionId=<id>
  const transport = new SSEServerTransport('/message', res as never);

  sessions.set(transport.sessionId, transport);

  transport.onclose = () => {
    sessions.delete(transport.sessionId);
  };

  await server.connect(transport);

  return { server, transport };
}

/**
 * Routes an incoming POST /message request to the correct SSE session.
 * Called by the /message Express handler in index.ts.
 */
export async function handleMessage(req: Request, res: Response): Promise<void> {
  const sessionId = req.query['sessionId'] as string | undefined;

  if (!sessionId) {
    res.status(400).json({ error: 'Missing sessionId query parameter' });
    return;
  }

  const transport = sessions.get(sessionId);

  if (!transport) {
    res.status(404).json({ error: `No active session for sessionId: ${sessionId}` });
    return;
  }

  await transport.handlePostMessage(req as never, res as never, req.body);
}
