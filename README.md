# SELF-AGENT · Personal AI Agent + RAG Knowledge Base

[English](README.md) | [简体中文](README.zh-CN.md)

Build a personal AI agent that speaks in your style, answers questions about your approved background, and retrieves information from documents you upload. Use the original two-mode chat page, embed the widget in another website, or call the API from your own agent.

The application combines a versioned **Persona** for identity and communication rules with an optional **RAG knowledge base** for project details and changing information. RAG retrieves relevant excerpts when a question arrives; it does not retrain the language model.

This public repository contains reusable code and fictional examples. Example Candidate and the evaluation projects are fictional; the maintainer's personal Persona, résumé, documents, conversations, database, credentials, and model weights are not included.

## Features

### Personal agent

- **Professional and casual modes:** separate conversations for work/project questions and everyday conversation.
- **Versioned Persona:** structured background, speaking style, first-person instructions, reference Q&A, and response boundaries.
- **Website chat:** a standalone landing page and a dependency-free Web Component with Shadow DOM.
- **Conversation controls:** streamed replies, stop/retry, session restore and reset. The API also supports JSON replies.
- **Interface options:** Chinese, English, and German; light/dark themes; mobile layout and keyboard controls.
- **Model choice:** DeepSeek, OpenAI-compatible APIs, and compatible local or remote llama.cpp servers.
- **FastAPI backend:** public profile, JSON/SSE chat, bounded history, request IDs, rate limits, and metrics without raw conversation logging.

### RAG knowledge base

- **Drop files to upload:** MD, TXT, PDF, and DOCX, with automatically inferred title, author/source, and dates where available. Review or edit the detected fields when needed.
- **Document processing:** background parsing, chunking, embeddings, job status, and retries.
- **Hybrid retrieval:** local multilingual embeddings plus keyword search in PostgreSQL/pgvector or local PGlite.
- **Cited answers:** source snippets with page, paragraph, or line locations; the widget displays citations used in the answer.
- **Version management:** activate processed replacements, retain the current version if replacement fails, unpublish, or delete.
- **Private and public use:** uploads default to private owner preview. Visitor chat uses explicitly published material.
- **Public mirror:** synchronize published current excerpts to a separate visitor database while original files remain in local storage.
- **Windows operation:** reusable management password, background execution, and startup when the current user signs in, without a CMD popup.

## How the two parts work together

Persona establishes who the agent represents and how it communicates. The knowledge base supplies evidence for documents, project progress, research notes, and other updates. Changing a knowledge document does not require retraining the model or rebuilding the website.

```mermaid
flowchart LR
    UI["Chat page / embedded widget"] --> API["FastAPI chat and preview APIs"]
    Persona["Versioned Persona"] --> API
    Owner["Local knowledge manager"] --> Ingest["Parse, chunk and embed"]
    Ingest --> KB["Private knowledge database"]
    KB -- "Owner preview" --> API
    KB -- "Publish selected material" --> Mirror["Optional public mirror"]
    Mirror -- "Visitor retrieval" --> API
    API --> Model["DeepSeek / compatible API / local model"]
    Model --> Reply["Reply with source citations when available"]
```

**Persona schema 1** supports the original fixed background/project package. **Schema 2** keeps stable identity, style, and boundaries in Persona and moves dynamic facts into dated knowledge documents. Both are supported.

## Requirements and installation

Use Python **3.12** for the documented setup. Node.js **22.12+** and npm are used for the local PGlite database and frontend tooling. The basic chat page can be served with Python alone.

Commands below use **Windows PowerShell** from the repository root unless a step explicitly changes directories.

```powershell
git clone https://github.com/ZacharyZ-25/self-agent-p.git
cd self-agent-p
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -e './backend'
```

The core FastAPI agent also runs on Linux/macOS: create a virtual environment with `python3 -m venv backend/.venv` and use `backend/.venv/bin/python` in place of the Windows interpreter path. The bundled launcher, password storage, and scheduled-task scripts target Windows.

## 1. Try the personal agent without a model or API key

In one terminal:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.demo:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal, also at the repository root:

```powershell
backend/.venv/Scripts/python.exe -m http.server 8080 --bind 127.0.0.1 --directory frontend
```

Open [the chat page](http://localhost:8080), choose professional or casual mode, and send a message. The demo uses the real UI and JSON/SSE transport with a clearly labelled **fixed response**. It makes no model calls and does not perform RAG retrieval. Initial dependency installation requires internet access.

## 2. Connect a real model

Stop the demo API. Copy the configuration template:

```powershell
Copy-Item backend/.env.example backend/.env
```

For DeepSeek, edit `backend/.env` locally:

```dotenv
APP_ENV=development
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=YOUR_OWN_KEY
DEEPSEEK_MODEL=YOUR_ENABLED_MODEL_ID
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
RAG_ENABLED=false
```

The empty generic fields allow the DeepSeek-specific settings to apply. For another compatible provider, use `LLM_PROVIDER=openai_compatible` and set `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`.

Run **from `backend/`** so the process loads `backend/.env`:

```powershell
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Keep the frontend server running. Replies now use the configured model.

For local inference, start your own compatible server at `http://127.0.0.1:8010/v1` with model alias `local-model`, then use `LLM_PROVIDER=local`, that base URL, and `LLM_MODEL=local-model`. The local knowledge launcher uses this local configuration for owner previews; the standalone API and optional visitor API can use remote providers.

Local parsing, embeddings, and retrieval require no paid model API. Local answer generation uses your own model and hardware; remote providers may charge for usage.

## 3. Customize Persona and embed the agent

Copy `persona.example/` into the ignored `persona/` directory, or use another private directory. Replace the fictional information, set `PERSONA_DIR` to its absolute path, and restart the API after edits.

| File | Purpose |
| --- | --- |
| `manifest.yaml` | Schema/version, approval, and verification metadata |
| `profile.yaml` | Identity, education, skills, interests, and public contacts |
| `projects.yaml` | Original schema 1 projects; empty in schema 2 |
| `voice_rules.yaml` | Tone, sentence length, formatting, and language choices |
| `boundaries.yaml` | Allowed topics and response limits |
| `qa_pairs.md` | Reviewed reference answers and style examples |
| `system_prompt.md` | First-person role and evidence rules |

Schema 1 requires at least 30 Q&A entries; schema 2 requires at least three stable entries and `facts_policy: knowledge_base`. Use `## Q:` followed by `A:`. The current validator requires the literal phrase `第一人称` in the system prompt. The bundled example is unapproved and suitable for development; review your own package and record its approval before production.

For an existing website:

```html
<script defer src="/chat-widget.js"></script>
<agent-chat-widget
  api-base="https://your-api.example"
  theme="auto"
  locale="auto"
  persona-mode
></agent-chat-widget>
```

The `persona-mode` attribute enables the two-mode experience. The original landing page also uses `layout="stage"` and `start-open`; omitting these uses the floating widget. Set `CORS_ORIGINS` to your exact frontend origins. Change the HTML `api-base` before building for a remote website.

## 4. Run the local RAG knowledge manager

Return to the repository root and stop any API already using port 8000.

```powershell
backend/.venv/Scripts/python.exe -m pip install -e './backend[knowledge]'
npm --prefix scripts/phase8-local-db ci
backend/.venv/Scripts/python.exe scripts/local-kb-password.py set
backend/.venv/Scripts/python.exe scripts/start-local-kb.py
```

Save the password once, then reuse it when logging into [the knowledge manager](http://127.0.0.1:8000/admin/kb). Windows DPAPI stores it for the current user. The launcher starts the local database, worker, and management API; it downloads the embedding model on first use.

Drop a file, wait for processing, and ask questions in owner preview. Documents default to private. Review the detected metadata when necessary, then publish the documents you want visitor chat to use. Replacing or withdrawing published material updates what can be retrieved.

For local answers, provide a server with the alias described above. The launcher can also start `local-model/runtime/llama-server.exe` if `local-model/models/` contains `Qwen3-4B-Q4_K_M.gguf`. No weights or inference executables are bundled. Without a chat model, uploading, indexing, and CLI retrieval still work:

```powershell
$env:DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:55437/postgres?sslmode=disable'
$env:KB_PGLITE_COMPAT='true'
backend/.venv/Scripts/python.exe scripts/kb-cli.py search 'your question' --owner-preview
```

Manual mode stops when you press Enter; closing the browser does not stop the services. Defaults are 20 MB per upload, 200 PDF pages, and 200,000 extracted characters. Scanned PDFs require OCR outside this application.

### Storage, migration, and background startup

Original files and the private database live in `knowledge-data/personal-kb/`; embedding cache is in `knowledge-data/model-cache/`. These directories are ignored by Git. Stop the services before copying database files for backup, and retain original files and your private Persona with the backup.

`scripts/migrate-persona.py` moves reviewed schema 1 dynamic facts into private knowledge documents and writes schema 2 core files after indexing succeeds. It preserves the original verification dates and backs up the old package. See [migration and development instructions](backend/app/knowledge/README.md).

After stopping manual mode, enable background startup:

```powershell
./scripts/local-kb-autostart.ps1 -Action Install
./scripts/local-kb-autostart.ps1 -Action Start
```

The `Local RAG Knowledge Base` task starts when the current Windows user signs in, using `pythonw.exe`. Use `Status`, `Stop`, or `Remove` to inspect, stop, or remove startup. A graphical password setup is available with `backend/.venv/Scripts/pythonw.exe scripts/local-kb-password.py set --gui`.

## 5. Connect the knowledge base to a public website

The two public chat routes use published material only. Authenticated owner preview is available at `/api/v1/admin/kb/preview`.

To run a separate visitor API, configure your reviewed private Persona and DeepSeek settings in `backend/.env`, then launch from the repository root:

```powershell
$env:PERSONA_DIR='C:/path/to/your/private/persona'
$env:KB_PUBLIC_API_ENABLED='1'
$env:KB_PUBLIC_CORS_ORIGINS='https://your-actual-site.example'
backend/.venv/Scripts/python.exe scripts/start-local-kb.py
```

The launcher maintains a public-only mirror and starts the visitor API at `127.0.0.1:8003`. Point an HTTPS reverse proxy to **8003**, then set the website widget's `api-base` to that HTTPS address. Management stays on the local interface. The computer must stay on and connected.

For automatic visitor startup, save `PERSONA_DIR`, `KB_PUBLIC_API_ENABLED`, and `KB_PUBLIC_CORS_ORIGINS` as persistent user environment variables; scheduled tasks do not retain temporary terminal variables.

The sync scripts also support a separate PostgreSQL/pgvector database. Docker images are defined by `backend/Dockerfile` for the basic agent and `backend/Dockerfile.rag` for RAG dependencies and cached embeddings. Production requires an approved Persona, explicit HTTPS frontend origins, and a configured HTTPS model provider.

## API reference

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Process liveness |
| `GET /readyz` | Persona/model configuration readiness, not a live model probe |
| `GET /api/v1/profile` | Public profile and quick questions |
| `POST /api/v1/chat` | JSON reply |
| `POST /api/v1/chat/stream` | SSE reply |
| `GET /api/v1/knowledge/sources/{chunk_id}` | A currently visible public source |
| `GET /admin/kb` | Local knowledge manager |
| `POST /api/v1/admin/kb/preview` | Authenticated private/public owner preview |

Example chat request:

```json
{"message":"Which project are you working on?","history":[],"locale":"en","persona_mode":"professional"}
```

Chat accepts `message`, optional `history`, `session_id`, `locale`, and `persona_mode` (`professional` / `casual`). RAG responses add source and knowledge-status fields; SSE emits sources alongside reply events. Conversation history is held in browser sessionStorage and sent with requests. The API does not persist a conversation database; rate limits are in memory.

## Development and tests

Run backend tests from the repository root so personal `backend/.env` settings are not loaded:

```powershell
backend/.venv/Scripts/python.exe -m pip install -e './backend[dev,knowledge]'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests
backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests
npm --prefix frontend ci
cd frontend
npx playwright install chromium
npm test
npm run test:size
npm run build
```

The static build writes `index.html`, `chat-widget.js`, and `style-demo.html` to `frontend/dist/`. Serve that directory for deployment.

Tests cover Persona migration, API/provider contracts, streamed replies, citations, and browser behavior. Database tests additionally cover the four file formats, indexing, permissions, version replacement, withdrawal, deletion, and public mirror sync. They require explicitly enabled, disposable test databases; see [the development guide](backend/app/knowledge/README.md). Providers are mocked, so the default tests do not call paid APIs.

## Repository layout

```text
backend/app/             FastAPI, Persona, model providers, RAG, admin page
frontend/                Original two-mode page and embeddable chat widget
persona.example/         Fictional Persona package
scripts/                 Ingestion CLI, migration, mirror, Windows launcher
evals/phase8/            Fictional document and question fixtures
knowledge-data/          Local runtime data and backups (Git-ignored)
```
