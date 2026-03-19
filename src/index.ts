import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import { createMcpServer, handleMessage } from './server';

const PORT = parseInt(process.env.PORT ?? '3000', 10);

const app = express();
app.use(cors());
app.use(express.json());

// ── Health check ───────────────────────────────────────────────────────────
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// ── SSE endpoint ── one persistent connection per MCP client ───────────────
app.get('/sse', async (req, res) => {
  // Headers are set by SSEServerTransport.start(); we just hand off res.
  const { server, transport } = await createMcpServer(req, res);

  req.on('close', async () => {
    await server.close();
    transport.close();
  });
});

// ── Message endpoint ── clients POST JSON-RPC messages here ────────────────
app.post('/message', async (req, res) => {
  await handleMessage(req, res);
});

app.listen(PORT, () => {
  console.log(`MCP server listening on http://localhost:${PORT}`);
  console.log(`  SSE      : GET  /sse`);
  console.log(`  Messages : POST /message?sessionId=<id>`);
  console.log(`  Health   : GET  /health`);
});
