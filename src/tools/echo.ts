import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import * as z from 'zod/v4';

/**
 * Registers the `echo` tool onto the MCP server.
 *
 * The tool accepts a single `message` string argument and returns it unchanged.
 * It exists primarily as a smoke-test / template for adding real tools.
 */
export function registerEchoTool(server: McpServer): void {
  server.registerTool(
    'echo',
    {
      description: 'Returns the provided message unchanged. Useful for testing connectivity.',
      inputSchema: { message: z.string().describe('The message to echo back') },
    },
    async ({ message }) => ({
      content: [{ type: 'text' as const, text: message }],
    }),
  );
}
