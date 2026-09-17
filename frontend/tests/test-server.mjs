import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

const root = resolve(import.meta.dirname, "..");
const port = Number.parseInt(process.env.AGENT_TEST_PORT || "4173", 10);
const requests = [];
const attempts = new Map();
const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

const profile = {
  persona_version: "example-0.1.0",
  display_name: "Example Candidate",
  title: "Fictional software engineering student",
  intro: {
    zh: "我是一个完全虚构的示例候选人。",
    en: "I am a completely fictional example candidate.",
  },
  avatar_url: null,
  quick_questions: {
    zh: ["简单介绍一下你自己", "哪个项目最能代表你？"],
    en: ["Could you introduce yourself?", "Which project represents you best?"],
  },
  contact: {
    website: "https://example.com",
  },
  disclaimer: "I am an AI twin built from Example Candidate’s approved public information. Verify important details with him.",
};

function json(response, status, body) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
  });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function event(name, data, newline = "\n") {
  return Buffer.from(`event: ${name}${newline}data: ${JSON.stringify(data)}${newline}${newline}`);
}

function wait(milliseconds) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
}

async function streamReply(request, response, payload) {
  requests.push(payload);
  response.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "Access-Control-Allow-Origin": "*",
  });
  response.write(event("meta", { request_id: `req_${requests.length}`, persona_version: "example-0.1.0" }, "\r\n"));

  if (payload.message.includes("__STOP__")) {
    response.write(event("delta", { text: "partial response" }));
    const heartbeat = setInterval(() => response.write(": keep-alive\n\n"), 100);
    const close = () => clearInterval(heartbeat);
    request.once("close", close);
    response.once("close", close);
    await wait(2_000);
    if (!response.destroyed) response.end(event("done", { finish_reason: "stop" }));
    return;
  }

  if (payload.message.includes("__FAIL_ONCE__")) {
    const count = (attempts.get(payload.message) || 0) + 1;
    attempts.set(payload.message, count);
    if (count === 1) {
      response.end(event("error", { code: "UPSTREAM_RATE_LIMITED", message: "busy", retryable: true }));
      return;
    }
  }

  const text = payload.message.includes("__XSS__")
    ? '<img src=x onerror="globalThis.__xss=1"><script>globalThis.__xss=2</script>'
    : payload.message.includes("__FAIL_ONCE__")
      ? "Retry succeeded."
      : payload.persona_mode === "casual"
        ? "我平时喜欢足球、咖啡、音乐和 EA Sports FC。"
        : "我是完全虚构的示例候选人。";
  const first = event("delta", { text: text.slice(0, Math.ceil(text.length / 2)) });
  const marker = Buffer.from("具");
  const split = first.indexOf(marker);
  const splitAt = split >= 0 ? split + 1 : Math.max(1, Math.floor(first.length / 2));
  response.write(first.subarray(0, splitAt));
  await wait(payload.message.includes("__SLOW__") ? 450 : 15);
  response.write(first.subarray(splitAt));
  await wait(15);
  response.write(
    Buffer.concat([
      event("delta", { text: text.slice(Math.ceil(text.length / 2)) }),
      event("usage", { prompt_tokens: 10, completion_tokens: 8, total_tokens: 18 }),
    ]),
  );
  await wait(15);
  response.end(event("done", { finish_reason: "stop" }));
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", "http://127.0.0.1:4173");
  try {
    if (request.method === "OPTIONS") {
      response.writeHead(204, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Accept, Content-Type",
      });
      response.end();
      return;
    }
    if (request.method === "GET" && url.pathname === "/api/v1/profile") {
      json(response, 200, profile);
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/v1/chat/stream") {
      await streamReply(request, response, await readJson(request));
      return;
    }
    if (request.method === "GET" && url.pathname === "/__test/requests") {
      json(response, 200, requests);
      return;
    }
    if (request.method === "POST" && url.pathname === "/__test/reset") {
      requests.length = 0;
      attempts.clear();
      json(response, 200, { ok: true });
      return;
    }

    const pathname = url.pathname === "/" ? "/tests/fixture.html" : decodeURIComponent(url.pathname);
    let file = resolve(root, `.${pathname}`);
    if (!file.startsWith(`${root}${sep}`) || !existsSync(file)) {
      response.writeHead(404);
      response.end("Not found");
      return;
    }
    if (statSync(file).isDirectory()) file = resolve(file, "index.html");
    response.writeHead(200, {
      "Content-Type": mime[extname(file)] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    createReadStream(file).pipe(response);
  } catch (error) {
    if (!response.headersSent) json(response, 500, { error: String(error) });
    else response.destroy(error);
  }
});

server.listen(port, "127.0.0.1");
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
