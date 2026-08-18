# V93K RAG 智能问答系统 v2

基于检索增强生成（RAG）的半导体测试机（V93000 / V93K）知识助手。

> 离线构建索引 + 在线三路问答（FAQ / Knowledge / Chitchat）+ MySQL 会话历史 + RAGAS 评估闭环。

## ✨ 功能亮点

| 模块 | 能力 |
|------|------|
| **多模文档加载** | PDF（文本层+扫描版 OCR）、DOCX、PPT/PPTX、PNG/JPG、MD、TXT |
| **嵌入** | bge-m3 同时输出 1024 维稠密向量 + 稀疏词项权重 |
| **混合检索** | 稠密 + 稀疏 + RRF 融合 → 父子块还原 |
| **重排序** | BGE-Reranker-Large（启动时预热，避免冷启动延迟） |
| **三路问答** | FAQ 快速路径（top-1 阈值，跳过 LLM）/ Knowledge（4 种策略 + rerank）/ Chitchat |
| **OCR** | rapidocr_onnxruntime（CPU，无 GPU 依赖） |
| **会话历史** | MySQL 持久化（s_<uuid8> session_id），每次一问一答一行，摘要后台线程重建 |
| **评估** | RAGAS 4 指标（faithfulness / answer_relevancy / context_precision / context_recall） |
| **Web UI** | Dark Mode + 紫渐变毛玻璃，localStorage 维护 session_id |

## 🚀 快速启动

### 前置

- Python ≥ 3.10（推荐 `D:\Anaconda\envs\DL_Pytorch_CUDA\python.exe`）
- 本地权重：`D:\workspace\python\RAG_project\my_pro\models\bge-m3\`
- 引用权重（rerank）：`D:\workspace\python\RAG_project\learning\EduRag\rag_qa\models\bge-reranker-large\`
- LLM Key：智谱（GLM）API Key（已写入 `config.ini`，或环境变量 `DASHSCOPE_API_KEY`）
- MySQL：localhost:3306，user=root（首次启动会自动建库 `v93k_rag` + 2 张表）

### 安装依赖

```bash
D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe -m pip install -r requirements.txt
```

### 首次构建索引

```bash
D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe scripts/build_index.py
```

### 启动后端（FastAPI :8000）

```bash
D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

启动过程（lifespan 预热，约 30-40s）：
1. 加载 bge-m3（~10s）
2. 加载 BGE-Reranker-Large（~7s）
3. 连接 Chroma 双 collection
4. 自动建 MySQL 库 `v93k_rag` + 表 `sessions` / `summaries`

### 启动前端服务（:8888 反向代理，可选）

```bash
D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe web_server.py
```

> 也可以直接访问 `http://localhost:8000/` —— `main.py` 已挂载 `web_ui/dist/` 静态文件，无需 :8888。

### 健康检查

```bash
curl http://localhost:8000/api/health
# → {"status":"ok","llm_model":"glm-4.5-air","collection":"v93k_kb","chunk_count":120}
```

### 提问示例

```bash
# 首次会 auto-generate session_id，响应里返回
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"STIL 是什么？"}'

# 续会话（带 session_id）
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"它怎么用？","session_id":"s_a289ab73"}'
```

### 跑评估

```bash
D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe scripts/run_eval.py --limit 3  # 冒烟
D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe scripts/run_eval.py             # 完整 25 道
```

报告写到 `data/eval/report_<时间戳>.json`。

## 📁 目录结构

```
my_pro/
├── main.py                    # FastAPI 入口（lifespan 预热 bge-m3 + rerank + 建 MySQL 库）
├── web_server.py              # :8888 反向代理 → :8000
├── config.ini                 # 集中配置（含 [mysql] 段）
├── requirements.txt
│
├── base/                      # 配置 + 日志
│   ├── config.py              # 含 MYSQL_* 字段
│   └── logger.py
│
├── api/                       # HTTP 层
│   ├── routes.py              # /api/ask /api/rebuild_index /api/health
│   └── schemas.py             # Pydantic 模型（AskRequest 含 session_id）
│
├── rag_qa/                    # RAG 核心
│   ├── core/
│   │   ├── embedding.py          # bge-m3
│   │   ├── vector_store.py       # Chroma 双 collection + 内存稀疏索引
│   │   ├── retriever.py          # 4 种策略 + retrieve_top_match
│   │   ├── reranker.py           # BGE-Reranker-Large（懒加载）
│   │   ├── query_router.py       # LLM 路由
│   │   ├── rag_system.py         # 三分支编排 + 后台摘要
│   │   ├── generator.py          # Prompt + LLM（含 generate_with_history / summarize）
│   │   ├── prompts.py            # 4 个 Prompt（含 with_history / summary）
│   │   ├── document_processor.py # 加载 + 父子块切分
│   │   └── llm_client.py         # OpenAI 兼容 + 30s 超时
│   ├── loaders/                # 文档加载（含 OCR）
│   │   ├── md_loader.py / pdf_loader.py
│   │   ├── ocr.py              # RapidOCR 单例
│   │   └── ocr_{pdf,docx,pptx,image}.py
│   ├── splitters/
│   │   └── chinese_recursive_splitter.py
│   ├── chat_history.py         # MySQL 会话历史 + 摘要（s_<uuid8> session_id）
│   └── eval/                   # RAGAS 评估
│       └── dataset.py / runner.py / report.py
│
├── data/                      # 知识库源 + 评估集
│   ├── *.md / *.pdf            # V93K 基础知识 / 常见错误 / STIL / API
│   └── eval/
│       ├── v93k_qa_v1.json    # 25 道评估题
│       └── report_*.json
│
├── scripts/                   # 运维脚本
│   ├── build_index.py         # 全量重建索引
│   ├── run_eval.py            # 跑 RAGAS 评估
│   └── smoke_test_{1-4}.py    # 链路冒烟
│
├── chroma_data/               # Chroma 持久化
├── models/bge-m3/             # bge-m3 权重
├── logs/app.log                # 运行日志
└── web_ui/dist/
    ├── index.html              # SPA（聊天 + 落地页）
    └── arch_diagram.html       # 架构图 v2
```

## 🧠 架构图

打开 `http://localhost:8888/arch_diagram.html` 或本地直接打开 `web_ui/dist/arch_diagram.html`。

整体 4 段分层：
1. **离线入库**（蓝）：多格式文档 → OCR → 切分 → bge-m3 → Chroma 双 collection
2. **在线问答**（粉）：用户 → Web UI → 反代 → FastAPI → QueryRouter → 三分支
3. **RAG 核心**（黄）：Retriever → 混合检索 → restore_parent → BGE-Rerank → Generator
4. **MySQL 会话历史**（黄）：sessions 表（每次一问一答）+ summaries 表（每 session 一条最新摘要）

## 🧪 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET`  | `/api/health` | 健康检查，返回 chunk_count |
| `POST` | `/api/ask` | 问答，`{question, source_filter?, session_id?}` → `{answer, domain, strategy, sources, elapsed_ms, session_id}` |
| `POST` | `/api/rebuild_index` | 全量重建索引（同步） |

`session_id` 行为：
- 不传 → 后端 auto-generate（`s_<uuid8>`）并在响应里返回
- 传已存在 → 复用同一会话，拼接上下文

`domain` 取值：`knowledge` / `faq` / `chitchat`
`strategy` 取值：`direct` / `hyde` / `subquery` / `backtracking`

## 💬 会话历史机制

**两张表（数据库 `v93k_rag`）**：

```sql
-- 每次一问一答 = 1 行
CREATE TABLE sessions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL,
  question TEXT, answer TEXT,
  domain VARCHAR(32), strategy VARCHAR(32),
  sources JSON, elapsed_ms FLOAT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_session_created (session_id, created_at)
);

-- 每个 session 一条最新摘要（覆盖式）
CREATE TABLE summaries (
  session_id VARCHAR(64) PRIMARY KEY,
  summary TEXT NOT NULL,
  turn_count INT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

**问答流程**：
1. LLM 生成答案（拼最近 3 轮 + 摘要 + 当前问题）
2. **同步**写 sessions 表（10ms，必须先写完）
3. **后台线程**调 LLM 重建摘要 + upsert summaries（~10s，不阻塞响应）

**Prompt 结构**（Knowledge 路径）：
```
[对话摘要（老于最近 3 轮）]
{summary}

[最近 3 轮对话]
轮 1: 用户问 ... 助手答 ...
...

[当前问题]
{question}

[助手回复]
```

FAQ 路径不调 LLM，但**仍写 sessions**（用户原话"每次一问一答"）。

## ⚙️ 配置说明（`config.ini`）

| 段 | 关键字段 |
|------|------|
| `[llm]` | `model`, `dashscope_api_key`, `temperature`, `timeout` |
| `[embedding]` | `model_dir` (bge-m3 本地), `device`, `use_fp16`, `max_length` |
| `[chroma]` | `persist_dir`, `collection_name`, `parents_collection_name`, `distance_metric` |
| `[retrieval]` | `parent_chunk_size`, `child_chunk_size`, `chunk_overlap`, `retrieval_k`, `candidate_m`, `faq_similarity_threshold` |
| `[rerank]` | `enabled`, `model_path`（引用 EduRag 权重）, `device`, `use_fp16` |
| `[ocr]` | `use_cuda`, `pdf_image_threshold` |
| `[mysql]` | `host`, `port`, `user`, `password`, `database` |
| `[app]` | `host`, `port`, `data_dir` |
| `[logger]` | `log_file`, `log_level` |

敏感字段（API key、MySQL 密码）可通过环境变量覆盖：`DASHSCOPE_API_KEY=xxx`, `MYSQL_PASSWORD=xxx`。

## 🛠 性能数据（实测）

| 路径 | 延迟 | 备注 |
|------|------|------|
| FAQ 命中 | ~2s | 跳过 LLM |
| Chitchat | ~6s | LLM 直答 |
| Knowledge（首问） | ~35s | 含 rerank 预热 + 首次检索 + LLM + 写库 |
| Knowledge（后续） | 14-26s | rerank 已 cache + 检索缓存 |
| Knowledge（FAQ miss 降级） | ~15s | 走完整链路 |

后台摘要：~10s/轮，**不阻塞**前端响应。

## 🔧 常见操作

### 添加新文档

把文件丢进 `data/`（支持 `.pdf`/`.md`/`.txt`/`.docx`/`.ppt`/`.pptx`/`.png`/`.jpg`），然后：

```bash
D:/Anaconda/envs/DL_Pytorch_CUDA/python.exe -m uvicorn main:app &
curl -X POST http://localhost:8000/api/rebuild_index
```

### 关闭重排（提速）

`config.ini`：
```ini
[rerank]
enabled = false
```

### 关闭 FAQ 路径

`config.ini`：
```ini
[retrieval]
faq_similarity_threshold = 1.0   # 永远不命中
```

### 切换 OCR 阈值

`config.ini`：
```ini
[ocr]
pdf_image_threshold = 0.4   # 更激进（更多图片 OCR）
```

### 重置 MySQL 数据

```sql
USE v93k_rag;
TRUNCATE TABLE sessions;
TRUNCATE TABLE summaries;
```

### 切换 LLM

`config.ini [llm]`：
- `model` 改模型名
- `dashscope_api_key` + `dashscope_base_url` 改端点

## 🐛 故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `AttributeError: 'ChatOpenAI' object has no field 'invoke'` | FlagEmbedding 与 transformers 版本 | 已有 monkey-patch |
| 启动后 `chunk_count=0` | 没建过索引 | 跑 `scripts/build_index.py` |
| `/api/ask` 422 | question 为空 | 已加 `min_length=1` 校验 |
| `/api/ask` 500 detail 是中文 | 后端异常 | 看 `logs/app.log` |
| LLM 30s 超时 | API 慢或挂了 | 调 `[llm] timeout` |
| 跨源请求被拦 | 已加 CORS(`*`) | 检查 `main.py` middleware |
| 评估时 faithfulness/answer_relevancy NaN | zhipu 限速 | runner 已加 tenacity retry |
| 首问 35s+ 漫长 | rerank 首次加载 | 已在 lifespan 预热，第二次起快 |
| MySQL 报错 Unknown column 'id' | 子查询 ORDER BY 引用外层未选列 | 见 chat_history.py:107 |

## 📦 依赖

- fastapi / uvicorn / chromadb / FlagEmbedding / sentence-transformers / openai
- langchain-*/langchain-text-splitters / PyMuPDF / python-docx / python-pptx / Pillow / opencv-python
- rapidocr-onnxruntime / ragas / pydantic / tenacity / **pymysql**（新增）

## 📜 License

仅供学习与内部使用。LLM key、MySQL 密码、reranking 模型路径等敏感信息已配置化，请勿提交到公共仓库。