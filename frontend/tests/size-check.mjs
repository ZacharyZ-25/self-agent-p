import { gzipSync } from "node:zlib";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../chat-widget.js", import.meta.url));
const compressed = gzipSync(source, { level: 9 });
const limit = 50 * 1024;

console.log(`chat-widget.js: ${source.length} bytes raw, ${compressed.length} bytes gzip`);
if (compressed.length > limit) {
  console.error(`FAIL: gzip size exceeds ${limit} bytes`);
  process.exitCode = 1;
} else {
  console.log(`PASS: gzip size is within the ${limit}-byte budget`);
}
