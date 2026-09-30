# SELF-AGENT · 个人 AI Agent + RAG 知识库

[English](README.md) | [简体中文](README.zh-CN.md)

搭建一个按你的表达风格聊天、介绍已确认背景、检索上传资料的个人 AI Agent。可以使用原来的双人格聊天页面，也可以把组件嵌入其他网站，或让自己的 Agent 调用 API。

系统由两部分组成：**Persona** 保存身份与交流规则，**RAG 知识库** 提供项目细节和动态资料。RAG 在提问时查找相关片段，不需要重新训练语言模型。

公开仓库包含通用代码和虚构样例。Example Candidate 和评测项目均为虚构；维护者的真实 Persona、简历、文档、聊天记录、数据库、密钥和模型权重不在仓库中。

## 功能

### 个人 Agent

- **专业 / 闲聊双人格**：工作、项目问题与日常聊天使用独立会话。
- **版本化 Persona**：结构化背景、表达风格、第一人称规则、参考问答和回答边界。
- **网站聊天界面**：独立主页，以及使用 Shadow DOM、无需运行时前端依赖的 Web Component。
- **会话操作**：流式回复、停止、重试、JSON 回退、会话恢复与清空。
- **界面选项**：中文、英文、德文，明暗主题，手机布局和键盘操作。
- **模型切换**：DeepSeek、OpenAI-compatible API，以及兼容的本地或远程 llama.cpp 服务。
- **FastAPI 后端**：公开简介、JSON/SSE 聊天、历史长度控制、请求 ID、限流和不记录聊天原文的指标。

### RAG 知识库

- **拖入文件即上传**：支持 MD、TXT、PDF、DOCX，尽量从文件识别标题、作者/来源和日期，识别结果可修改。
- **后台处理**：解析、分块、Embedding、任务状态与重试。
- **混合检索**：本地多语向量与关键词检索，使用 PostgreSQL/pgvector 或本机 PGlite。
- **带引用的回答**：保留页码、段落、行号等定位；聊天组件展示回答实际使用的来源。
- **版本管理**：替换处理成功后切换当前版本；失败保留旧版，支持撤回公开和删除。
- **私有与公开使用**：默认仅自己预览，访客只使用明确发布的资料。
- **公开镜像**：把已发布的当前片段同步到独立访客数据库，完整原件留在本机。
- **Windows 日常运行**：固定管理密码、后台运行、当前用户登录后自启，无 CMD 弹窗。

## 两部分如何配合

Persona 决定“代表谁、怎么说话”；知识库提供文档、项目进度、研究笔记等事实依据。更新知识文档不需要重新训练模型，也不需要重新构建网站。

```mermaid
flowchart LR
    UI["聊天页面 / 嵌入组件"] --> API["FastAPI 聊天与预览接口"]
    Persona["版本化 Persona"] --> API
    Owner["本地知识库管理页"] --> Ingest["解析、分块、建立向量"]
    Ingest --> KB["私有知识数据库"]
    KB -- "本人预览" --> API
    KB -- "发布所选资料" --> Mirror["可选公开镜像"]
    Mirror -- "访客检索" --> API
    API --> Model["DeepSeek / 兼容 API / 本地模型"]
    Model --> Reply["回复，并在有来源时附引用"]
```

**Persona schema 1** 支持原来固定保存背景和项目的方式；**schema 2** 把稳定身份、语气和边界留在 Persona，把动态事实迁入带日期的知识文档。两种格式都兼容。

## 环境与安装

以下安装方式使用 Python **3.12**。本机 PGlite 数据库和前端工具需要 Node.js **22.12+** 与 npm；基础聊天页面可以只用 Python 提供服务。

下列命令使用 **Windows PowerShell**，除明确切换目录的步骤外，都在仓库根目录运行。

```powershell
git clone https://github.com/ZacharyZ-25/self-agent-p.git
cd self-agent-p
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -e './backend'
```

核心 FastAPI Agent 也可在 Linux/macOS 运行：用 `python3 -m venv backend/.venv` 创建环境，并把 Windows 解释器路径替换为 `backend/.venv/bin/python`。仓库中的启动器、密码存储与计划任务脚本面向 Windows。

## 1. 先体验个人 Agent，无需模型和 API 密钥

在第一个终端运行：

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.demo:app --app-dir backend --host 127.0.0.1 --port 8000
```

在第二个终端，同样从仓库根目录运行：

```powershell
backend/.venv/Scripts/python.exe -m http.server 8080 --bind 127.0.0.1 --directory frontend
```

打开 [聊天页面](http://localhost:8080)，选择专业或闲聊人格后发消息。演示使用真实界面和 JSON/SSE 通信，但返回明确标记的**固定回复**，不调用模型，也不做 RAG 检索。首次安装依赖需要联网。

## 2. 接入真实模型

停止演示 API，复制配置模板：

```powershell
Copy-Item backend/.env.example backend/.env
```

使用 DeepSeek 时，在本机编辑 `backend/.env`：

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

清空通用字段后，DeepSeek 专用配置才会生效。其他兼容服务使用 `LLM_PROVIDER=openai_compatible`，填写 `LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_API_KEY`。

**进入 `backend/` 再启动**，程序才能读取 `backend/.env`：

```powershell
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

保留前端服务，此时回复就由配置的模型生成。

本地推理可自行启动兼容服务，地址为 `http://127.0.0.1:8010/v1`，模型别名为 `local-model`；然后设置 `LLM_PROVIDER=local`、对应地址及 `LLM_MODEL=local-model`。本地知识库启动器使用这套配置生成本人预览回答；独立 API 和可选访客 API 可以使用远程模型。

本地解析、Embedding 和检索无需付费模型 API。本地回答使用自己的模型与电脑算力，远程 API 则可能按使用量收费。

## 3. 定制 Persona，并嵌入网站

把 `persona.example/` 复制到 Git 忽略的 `persona/`，或另一处私有目录。替换虚构信息，把 `PERSONA_DIR` 设置为该目录的绝对路径；修改后重启 API。

| 文件 | 用途 |
| --- | --- |
| `manifest.yaml` | 格式版本、内容版本、批准与确认日期 |
| `profile.yaml` | 身份、教育、技能、兴趣和公开联系方式 |
| `projects.yaml` | schema 1 的项目；schema 2 中为空 |
| `voice_rules.yaml` | 语气、句长、格式和语言习惯 |
| `boundaries.yaml` | 可回答的话题与边界 |
| `qa_pairs.md` | 已确认的参考问答和表达示例 |
| `system_prompt.md` | 第一人称角色与事实依据规则 |

Schema 1 至少需要 30 条问答；schema 2 至少需要 3 条稳定问答，并设置 `facts_policy: knowledge_base`。问答格式为 `## Q:` 后接 `A:`。当前校验器要求系统提示词包含“`第一人称`”这个短语。仓库示例未批准，可用于开发；生产使用前应核对自己的资料并记录批准信息。

嵌入已有网站：

```html
<script defer src="/chat-widget.js"></script>
<agent-chat-widget
  api-base="https://your-api.example"
  theme="auto"
  locale="auto"
  persona-mode
></agent-chat-widget>
```

`persona-mode` 启用双人格体验。原主页还使用 `layout="stage"` 和 `start-open`；不设置这两项时使用悬浮聊天组件。`CORS_ORIGINS` 填写准确的前端来源。部署到远程网站前，修改 HTML 的 `api-base`。

## 4. 启动本机 RAG 知识库

回到仓库根目录，先停止已经占用 8000 端口的 API。

```powershell
backend/.venv/Scripts/python.exe -m pip install -e './backend[knowledge]'
npm --prefix scripts/phase8-local-db ci
backend/.venv/Scripts/python.exe scripts/local-kb-password.py set
backend/.venv/Scripts/python.exe scripts/start-local-kb.py
```

保存一次密码后，打开 [知识库管理页](http://127.0.0.1:8000/admin/kb) 时复用它。密码由 Windows DPAPI 为当前用户保存。启动器运行本机数据库、Worker 和管理 API，首次使用会下载 Embedding 模型。

拖入文件，等待处理完成，再在本人预览中提问。资料默认私有，必要时修改识别出的基本信息；希望访客使用的资料需要主动发布。替换或撤回后，可检索的内容随之更新。

本地回答需要前面所述的模型服务。如果 `local-model/models/` 下已有 `Qwen3-4B-Q4_K_M.gguf`，启动器也能自动运行 `local-model/runtime/llama-server.exe`。仓库不提供权重或推理程序。没有聊天模型时，上传、索引和 CLI 检索仍然可用：

```powershell
$env:DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:55437/postgres?sslmode=disable'
$env:KB_PGLITE_COMPAT='true'
backend/.venv/Scripts/python.exe scripts/kb-cli.py search '你的问题' --owner-preview
```

手动模式按 Enter 停止；关闭网页不会停止后台服务。默认限制是每文件 20 MB、PDF 200 页、提取正文 20 万字符。扫描版 PDF 需要在程序外先做 OCR。

### 数据、迁移与后台自启

原件和私有数据库保存在 `knowledge-data/personal-kb/`，Embedding 缓存保存在 `knowledge-data/model-cache/`，均被 Git 忽略。备份数据库文件前先停止服务，并同时保留原件及私人 Persona。

`scripts/migrate-persona.py` 将已确认的 schema 1 动态事实迁为私有知识文档，索引成功后写入 schema 2 核心包。迁移保留原资料确认日期并备份旧包。详见 [迁移与开发说明](backend/app/knowledge/README.md)。

结束手动运行后，启用后台自启：

```powershell
./scripts/local-kb-autostart.ps1 -Action Install
./scripts/local-kb-autostart.ps1 -Action Start
```

`Local RAG Knowledge Base` 任务使用 `pythonw.exe`，在当前 Windows 用户登录时启动。`Status` 查看状态，`Stop` 停止，`Remove` 取消自启。也可用 `backend/.venv/Scripts/pythonw.exe scripts/local-kb-password.py set --gui` 在图形窗口设置密码。

## 5. 让公开网站读取知识库

两个公开聊天接口只使用已发布资料；通过管理员登录的本人预览使用 `/api/v1/admin/kb/preview`。

需要单独访客 API 时，在 `backend/.env` 中配置已经核对的私人 Persona 和 DeepSeek 参数，然后从仓库根目录启动：

```powershell
$env:PERSONA_DIR='C:/path/to/your/private/persona'
$env:KB_PUBLIC_API_ENABLED='1'
$env:KB_PUBLIC_CORS_ORIGINS='https://your-actual-site.example'
backend/.venv/Scripts/python.exe scripts/start-local-kb.py
```

启动器维护仅含公开资料的镜像，并在 `127.0.0.1:8003` 运行访客 API。把 HTTPS 反向代理接到 **8003**，再把网站组件的 `api-base` 指向该 HTTPS 地址。管理接口仍留在本机，电脑需要保持开机联网。

访客接口需要随 Windows 自启时，把 `PERSONA_DIR`、`KB_PUBLIC_API_ENABLED`、`KB_PUBLIC_CORS_ORIGINS` 保存为当前用户的持久环境变量；计划任务不会保留临时终端变量。

同步脚本也支持另一套 PostgreSQL/pgvector 数据库。`backend/Dockerfile` 提供基础 Agent 镜像，`backend/Dockerfile.rag` 增加 RAG 依赖和 Embedding 缓存。生产部署需要已批准的 Persona、明确的 HTTPS 前端来源和已配置的 HTTPS 模型服务。

## API 参考

| 接口 | 用途 |
| --- | --- |
| `GET /healthz` | 进程存活检查 |
| `GET /readyz` | Persona/模型配置检查，不会实际调用模型 |
| `GET /api/v1/profile` | 公开简介与快捷问题 |
| `POST /api/v1/chat` | JSON 回复 |
| `POST /api/v1/chat/stream` | SSE 流式回复 |
| `GET /api/v1/knowledge/sources/{chunk_id}` | 当前可见的公开来源 |
| `GET /admin/kb` | 本地知识库管理页 |
| `POST /api/v1/admin/kb/preview` | 登录后预览私有/公开资料 |

聊天请求示例：

```json
{"message":"你目前在做什么项目？","history":[],"locale":"zh","persona_mode":"professional"}
```

请求支持 `message`，以及可选的 `history`、`session_id`、`locale`、`persona_mode`（`professional` / `casual`）。RAG 回复增加来源和知识库状态字段，SSE 会在回复事件中传递来源。聊天历史保存在浏览器 sessionStorage，并随请求发送；API 不建立持久聊天数据库，限流状态保存在进程内存。

## 开发与测试

从仓库根目录运行后端测试，避免读取个人 `backend/.env` 配置：

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

静态构建把 `index.html`、`chat-widget.js`、`style-demo.html` 写入 `frontend/dist/`；部署时提供这个目录。

测试覆盖 Persona 迁移、API/Provider 契约、流式回复、引用和浏览器行为。数据库测试还覆盖四种格式、索引、权限、版本替换、撤回、删除和公开镜像同步，需要主动启用独立的临时测试数据库，详见 [开发说明](backend/app/knowledge/README.md)。Provider 使用模拟服务，默认测试不会调用收费 API。

## 目录结构

```text
backend/app/             FastAPI、Persona、模型适配、RAG、管理页面
frontend/                原双人格主页与可嵌入聊天组件
persona.example/         虚构 Persona 包
scripts/                 导入 CLI、迁移、镜像、Windows 启动器
evals/phase8/            虚构文档与问题样例
knowledge-data/          本机运行数据和备份，Git 忽略
```
