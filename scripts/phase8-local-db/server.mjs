import { PGlite } from '@electric-sql/pglite';
import { PGLiteSocketServer } from '@electric-sql/pglite-socket';
import { vector } from '@electric-sql/pglite-pgvector';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const dbPath = process.env.KB_PGLITE_DB || path.join(root, 'knowledge-data', 'pglite-db');
const port = Number(process.env.KB_PGLITE_PORT || 55433);
const db = await PGlite.create(dbPath, { extensions: { vector } });
const server = new PGLiteSocketServer({
  db, host: '127.0.0.1', port, maxConnections: 8,
});
await server.start();
console.log(`Local PostgreSQL-compatible test database ready on 127.0.0.1:${port}`);
let stopping = false;
async function stop() {
  if (stopping) return;
  stopping = true;
  await server.stop();
  await db.close();
  process.exit(0);
}
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => { void stop(); });
}
process.stdin.setEncoding('utf8');
process.stdin.on('data', (chunk) => {
  if (chunk.trim() === 'stop') void stop();
});
process.stdin.on('end', () => { void stop(); });
