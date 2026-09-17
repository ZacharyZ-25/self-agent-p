# SELF-AGENT

A reproducible, Persona-grounded AI chat application: a dependency-free Web Component frontend and a FastAPI backend with JSON and Server-Sent Events (SSE).

这是 SELF-AGENT 的公开复现版，包含旧版「专业 / 闲聊」双人格前端与当前后端组件。仓库只提供**完全虚构的 Example Candidate**，不包含作者个人 Persona、API Key、个人网站内容、照片、聊天记录或训练权重。下面先运行无需密钥的完整演示，再按需接入自己的模型。

## What is included

- Original two-mode chat landing page; isolated session history, light/dark themes, Chinese/English/German UI, streamed replies, stop/retry and JSON fallback.
- FastAPI: profile endpoint, JSON/SSE chat, Persona validation, bounded conversation context, request IDs, rate limits and structured metrics without raw conversation logging.
- Providers: DeepSeek and OpenAI-compatible APIs, including local or remotely hosted llama.cpp.
- Complete fictional Persona with 30 example Q&A pairs, automated API/provider/browser tests, locked Python and Node dependencies, Dockerfile.

This release packages the application, not a trained model. The newer personal portfolio website and experimental training pipeline are not included. The offline demo returns a **fixed, clearly labelled response**; it is not an LLM.

## Requirements

- Python 3.12 recommended (supported: 3.10–3.13).
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for the locked Python environment.
- Node.js 22.12+ and npm only for frontend build/browser tests. No Node runtime is needed to serve the page.
- Git. Real AI chat additionally requires your own compatible API account or model server.

## 1. Run the complete offline demo (no key, no model)

```sh
git clone https://github.com/ZacharyZ-25/self-agent-public.git
cd self-agent-public/backend
uv sync --frozen --extra dev
uv run uvicorn app.demo:app --host 127.0.0.1 --port 8000
```

Open another terminal in the cloned repository root:

```sh
uv run --project backend python -m http.server 8080 --bind 127.0.0.1 --directory frontend
```

Visit **http://localhost:8080**, choose a persona mode, and send a message. The page connects to `http://localhost:8000`. Both `localhost:8080` and `127.0.0.1:8080` are allowed browser origins. Leave both terminals running; stop with Ctrl+C.

API documentation: http://localhost:8000/docs. Health: http://localhost:8000/healthz. The demo exercises the real frontend, validation and API transport with an injected fixed-response provider; it makes no model API calls. Initial dependency installation needs internet access.

## 2. Connect a real model

Stop the demo backend. In `backend/`, copy `.env.example` to `.env`:

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

```sh
# macOS / Linux
cp .env.example .env
```

Edit `.env` locally, providing a model ID available from your chosen provider:

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=YOUR_ENABLED_MODEL_ID
LLM_API_KEY=YOUR_OWN_KEY
```

Then run **from `backend/`**, so `.env` is found:

```sh
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep the frontend server running from step 1. Requests now use your model and may incur provider charges. Keys belong only in the backend environment, never HTML or JavaScript.

For local llama.cpp, start a separately installed server with a compatible GGUF file:

```sh
llama-server -m /path/to/model.gguf --host 127.0.0.1 --port 8010 --alias local-model
```

Use `LLM_PROVIDER=local`, `LLM_BASE_URL=http://127.0.0.1:8010/v1`, `LLM_MODEL=local-model` and an empty `LLM_API_KEY`. Model download, licensing and hardware requirements depend on the model; weights are not included. `local` is development-only. Remote `llama_cpp` and `openai_compatible` configurations require endpoint, model and key. For DeepSeek use `LLM_PROVIDER=deepseek`, `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL`; remove generic endpoint/model overrides to use the DeepSeek defaults.

## 3. Use your own Persona

The default is `persona.example/`. Its manifest intentionally has `approved: false`; it runs in development but is not production-ready.

1. Copy `persona.example/` to the ignored root directory `persona/` (or another private directory).
2. Replace fictional facts in `profile.yaml`, `projects.yaml`, `voice_rules.yaml`, `boundaries.yaml`, `system_prompt.md` and `qa_pairs.md`. Keep the schemas and at least 30 Q&A sections using `## Q:` followed by `A:`. The first-person system prompt currently requires the literal phrase `第一人称`.
3. Set `PERSONA_DIR` in `backend/.env` to the absolute path of your private directory. Restart the backend after edits; it loads an immutable snapshot on startup.
4. Before production, review every fact and set the manifest approval fields yourself. Do not mark the bundled fictional example as a real person's approved identity.

The widget branding can be edited in `frontend/index.html` and the copy dictionaries in `frontend/chat-widget.js`. Embedding on an existing page:

```html
<script defer src="/chat-widget.js"></script>
<agent-chat-widget api-base="https://your-api.example"
  theme="auto" locale="auto" persona-mode></agent-chat-widget>
```

Set `CORS_ORIGINS` to the exact frontend origins (scheme + host + optional port, no trailing slash). Production accepts explicit HTTPS origins only; the API itself is public, so CORS is not authentication.

## Architecture and API

```text
Browser Web Component → FastAPI → validated Persona + bounded history
                              → OpenAI-compatible model provider
Browser ← JSON reply or SSE meta / delta / done / error events
```

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Process liveness |
| `GET /readyz` | Persona/configuration readiness; does not probe model availability |
| `GET /api/v1/profile` | Public profile and quick questions |
| `POST /api/v1/chat` | JSON response |
| `POST /api/v1/chat/stream` | SSE response |

Both chat routes accept `message`, optional `history` (`role`/`content` entries), `session_id` (UUID), `locale` and `persona_mode` (`professional` or `casual`). Example request:

```json
{"message":"Introduce yourself","history":[],"locale":"en","persona_mode":"professional"}
```

History is sent by the browser and stored in sessionStorage per persona mode. The server does not persist a conversation database. Rate limiting is in memory, resets on restart and is not shared across workers; use one worker or add a shared limiter before scaling.

## Tests and static build

Run backend tests **from the repository root**, so local `backend/.env` credentials are not loaded:

```sh
uv run --project backend pytest -c backend/pyproject.toml backend/tests
uv run --project backend ruff check backend
```

All included backend tests use fake/mocked providers; no paid API smoke test is included.

```sh
cd frontend
npm ci
npx playwright install chromium
npm test
npm run test:size
npm run build
```

On Linux CI, use `npx playwright install --with-deps chromium`. The static build writes only `index.html`, `chat-widget.js` and `style-demo.html` to `frontend/dist/`; do not deploy test servers or source test fixtures. Set the `api-base` in the HTML pages before building for a remote host.

## Docker and deployment

From the repository root:

```sh
docker build -f backend/Dockerfile -t self-agent-api .
docker run --rm -p 8000:10000 --env-file backend/.env self-agent-api
```

This starts the real-provider backend with the fictional example. To use a private Persona, mount it read-only at `/app/persona` and set `PERSONA_DIR=/app/persona`. The build context explicitly allows only application code, dependency locks and `persona.example/`; `.env` and your private Persona are not baked into the image.

For production set `APP_ENV=production`, `REQUIRE_APPROVED_PERSONA=true`, your HTTPS `CORS_ORIGINS`, and a remote HTTPS provider with your own secret key. Mount your reviewed Persona. Keep `LOG_RAW_CONVERSATIONS=false`. Configure the host's port using `PORT` (container default: 10000). Preserve SSE streaming through reverse proxies. Docker commands are provided as a deployment recipe; a Docker daemon is not needed for the local quickstart.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Page loads, requests fail | Backend on port 8000, `api-base`, browser origin and `CORS_ORIGINS` |
| Readiness says OK but model fails | Development readiness reports warnings; inspect its `checks`. It is not an upstream connectivity test. |
| Chat unavailable | Complete Persona, correct model/key, use `app.demo:app` for the no-key demo |
| Production returns 503 | Persona approval/completeness and provider configuration |
| 429 after repeated testing | Per-minute/day/session quotas; restart a local test server or configure development limits |
| Local model connection refused | Start llama.cpp separately; `local` does not start a server for you |
| Docker cannot reach localhost model | Container localhost is the container; configure an accessible model host |

## Privacy and source boundaries

This repository has a new Git history and includes only allowlisted application files and fictional fixtures. `.env`, `persona/`, `private/`, key files and generated output are ignored. Git ignore is not encryption: always inspect staged files before publishing your own changes. The public release contains no personal portfolio assets, real Persona package, model weights or private repository history.
