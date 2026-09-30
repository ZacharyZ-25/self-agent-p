# Local RAG for a personal agent

在自己的电脑上管理知识库，让 Agent 检索资料并引用来源。拖入文件即可自动提取标题、作者和日期，完成索引后直接提问。

本仓库发布通用程序、测试与虚构样例。Example Candidate 和测试项目均为虚构；不包含维护者的简历、论文、聊天记录、知识库、数据库或 API 密钥。

## 功能

- MD / TXT / PDF / DOCX 拖入即上传，自动识别基本信息，也可手动修改。
- 后台解析、分块、来源页码/段落、处理状态与重试。
- 本地多语 Embedding + PostgreSQL/pgvector，向量与关键词混合检索。
- 新版本处理成功后切换，失败替换保留旧版，可撤回公开或删除。
- 默认私有；管理员预览可用私有资料，访客只使用已发布资料。
- JSON / SSE 连续聊天、可点击引用及来源片段；没有依据时说明无法确认。
- 独立公开镜像，只同步已发布片段，访客接口不连接私有原件。
- Persona schema 2 保留身份、语气与边界，动态事实由知识文档提供；兼容 schema 1，提供迁移工具。
- Windows 固定管理密码、后台运行、用户登录后自启，无 CMD 弹窗。

## Windows 本机安装

使用 Python 3.12、Node.js 和 npm，在 PowerShell 中运行：

```powershell
git clone https://github.com/ZacharyZ-25/self-agent-p.git
cd self-agent-p
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -e './backend[knowledge]'
npm --prefix scripts/phase8-local-db ci
backend/.venv/Scripts/python.exe scripts/start-local-kb.py
```

首次启动下载本地 Embedding 模型，随后打开 [管理页](http://127.0.0.1:8000/admin/kb)。拖入资料后等待状态变为可用。启动器默认只启动私有管理，不调用收费聊天 API。手动模式按 Enter 停止，关掉网页不会停止服务。

数据库和原件存于 `knowledge-data/personal-kb/`，缓存存于 `knowledge-data/model-cache/`，均被 Git 忽略。备份时先停止服务，再一起复制数据库、原件和私人 Persona。扫描版 PDF 需要另做 OCR；单文件上限 20 MB，超长文件需人工处理。

### 生成回答

上传、分块和检索无需聊天 API。自然语言回答需要模型：

- 本地启动器连接 `http://127.0.0.1:8010/v1`，模型别名 `local-model`。若自行准备了 `local-model/runtime/llama-server.exe` 和 `local-model/models/` 下的 `Qwen3-4B-Q4_K_M.gguf`，也会自动启动。仓库不包含权重或模型运行程序。
- 公开访客或独立 API 使用 DeepSeek / OpenAI-compatible 服务：在本机 `backend/.env` 配置自己的密钥、模型和地址。API 用量可能收费。本地小模型与远程模型的质量不同，需要检查自己的回答与引用。

不配置回答模型时仍可检索。在另一个 PowerShell 中：

```powershell
$env:DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:55437/postgres?sslmode=disable'
$env:KB_PGLITE_COMPAT='true'
backend/.venv/Scripts/python.exe scripts/kb-cli.py search '你的问题' --owner-preview
```

### 后台启动

先结束手动服务，以日常 Windows 用户运行：

```powershell
backend/.venv/Scripts/pythonw.exe scripts/local-kb-password.py set --gui
./scripts/local-kb-autostart.ps1 -Action Install
./scripts/local-kb-autostart.ps1 -Action Start
```

任务名为 `Local RAG Knowledge Base`，由当前用户登录触发。密码使用 Windows DPAPI 保存，只能由设置密码的 Windows 用户读取。`Status` 查看状态，`Stop` 停止，`Remove` 取消自启。

## 接入 Agent 或网站

本机 Agent 可调用 `POST http://127.0.0.1:8000/api/v1/chat` 或 `/api/v1/chat/stream`。这两个访客接口只用已发布资料；私有问答使用已登录的管理员 `/api/v1/admin/kb/preview`。管理页应仅在本机访问。

公开网站可通过单独的访客接口读取已发布资料。先准备并确认自己的私人 Persona，并设置 `PERSONA_DIR`；示例 Persona 未批准，不能作为生产身份。将 `backend/.env.example` 复制为 `backend/.env`，配置 DeepSeek（清除示例中的通用 LLM_* 覆盖值），然后在启动器运行前设置：

```powershell
$env:KB_PUBLIC_API_ENABLED='1'
$env:KB_PUBLIC_CORS_ORIGINS='https://your-actual-site.example'
backend/.venv/Scripts/python.exe scripts/start-local-kb.py
```

启动器创建公开镜像和 `127.0.0.1:8003` 生产访客接口。把 HTTPS 反向代理接到 **8003**，前端 `<agent-chat-widget api-base="https://your-api.example">` 指向它；电脑需要开机联网。生产接口关闭本地密码管理入口。同步脚本也可连接另一套 PostgreSQL/pgvector 数据库。

若需要访客接口随 Windows 自启运行，把 `KB_PUBLIC_API_ENABLED`、`KB_PUBLIC_CORS_ORIGINS` 和 `PERSONA_DIR` 设为当前用户的持久环境变量；后台任务不会保存临时终端变量。密钥仍保存在本机 `backend/.env`。

独立 API / Worker、Docker、迁移和测试说明见 [知识库开发说明](backend/app/knowledge/README.md)。

## 离线 UI 演示

固定回复演示，无需数据库或密钥：

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.demo:app --app-dir backend --port 8000
npm --prefix frontend ci
npm --prefix frontend run build
backend/.venv/Scripts/python.exe -m http.server 8080 --directory frontend/dist
```

打开 [演示页](http://127.0.0.1:8080)。固定回复只检查 UI 与通信，不是实际 AI 或 RAG 回答。
