# RAG development

`repository.py` 管理文档、版本和任务；`parsers.py` 解析文件；`chunker.py` 分块；`indexer.py` 建立索引；`retriever.py` 检索授权的当前版本；`public_mirror.py` 同步已发布片段。管理页位于 `app/admin/kb.html`，引用接口位于 `app/api/knowledge_sources.py`。

## 独立启动

可用 `backend/knowledge-local.compose.yaml` 启动 PostgreSQL/pgvector，或使用 Node 的 `scripts/phase8-local-db/server.mjs` 启动文件 PGlite。后者必须设置 `KB_PGLITE_COMPAT=true`。启动器已有这些设置。

```powershell
$env:DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:55437/postgres?sslmode=disable'
$env:KB_PGLITE_COMPAT='true'
$env:RAG_ENABLED='true'
$env:KB_ADMIN_ENABLED='true'
# 在当前终端设置自己的 KB_ADMIN_PASSWORD，不要提交密码。
backend/.venv/Scripts/python.exe scripts/kb-cli.py migrate
backend/.venv/Scripts/python.exe scripts/kb-cli.py work-forever
```

在具有相同环境变量的另一终端启动 `uvicorn app.main:app --app-dir backend --port 8000`。回答模型需要另外配置。原件默认本地存储，也支持 S3；凭据用标准 SDK 配置。

`extracted` 表示提取完成；`ready` 表示索引完成；激活、发布是独立步骤。CLI 导入可加 `--run-worker`，再执行 `activate VERSION_ID`；加 `--publish` 才用于访客问答。管理页自动激活成功上传的版本，默认私有。

## Persona 迁移

Schema 2 使用 `facts_policy: knowledge_base`。profile 不存当前介绍、论文或毕业计划、career 和 skills.learning；projects 为空；至少保留三条稳定问答和原交流规则。Schema 1 仍兼容。

`scripts/migrate-persona.py` 从已确认的 schema 1 包读取动态事实，建立日期沿用原记录的私有知识文档，索引完成后替换核心 Persona。原文件及结果备份到指定的本机目录。

迁移配置 YAML 包含 `persona_version`、`performed_at`、`stable_identity`（stable_title、stable_intro_zh/en）、`qa_routes`，以及可选的 qa_overrides、extra_documents、system_prompt。每条原问答按从 1 开始的编号指定路由；稳定问答用 `core`，动态问答用项目 ID 或 `status` / `career` / `learning`，额外分组在 extra_documents 中给出标题。需逐条确认，避免把进度留在固定问答里。

```powershell
backend/.venv/Scripts/python.exe scripts/migrate-persona.py --persona-dir C:/path/to/private/persona --config C:/path/to/private/migration.yaml --backup-dir knowledge-data/persona-backup
```

迁移不会发布资料。私人配置、备份与 Persona 不应提交。`test_persona_migration.py` 用虚构旧包验证日期保留、信息迁移与关闭 RAG 后的回退行为。

## 验证

```powershell
backend/.venv/Scripts/python.exe -m pip install -e './backend[dev,knowledge]'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests
backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests
npm --prefix frontend ci
npx --prefix frontend playwright install chromium
npm --prefix frontend test
npm --prefix frontend run test:size
```

数据库测试使用两套独立测试库，不使用个人资料库。在两个终端分别设置 `KB_PGLITE_DB=memory://`，用端口 55445 和 55446 启动 Node 数据库脚本；在测试终端设置：

```powershell
$env:DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:55445/postgres?sslmode=disable'
$env:PUBLIC_KB_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:55446/postgres?sslmode=disable'
$env:KB_PGLITE_COMPAT='true'
$env:PUBLIC_KB_PGLITE_COMPAT='true'
$env:RUN_KB_INTEGRATION='1'
$env:RUN_KB_MIRROR_INTEGRATION='1'
$env:RUN_REAL_DEEPSEEK_SMOKE='0'
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests
```

测试验证四种格式、定位、索引、版本切换、私有预览、发布/撤回/删除、公开镜像和 JSON/SSE 引用。Provider 使用固定回复；不代表实际模型的回答质量。

`backend/Dockerfile.rag` 安装知识库依赖并缓存 Embedding。生产部署还需持久数据库、自己的已批准 Persona 和 HTTPS 站点设置。
