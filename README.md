# SemiconRAG · 半导体工艺智能问答系统

基于现有 RAG 项目改造的**晶圆制造场景教学原型**。面向工艺整合、设备维护、良率分析、洁净室规范和制程质量控制五类问题。项目附带的是明确标识的演示资料，不含真实厂内受控工艺窗口、设备 PM 规程或生产数据。

## 当前实现

- PDF、Word、PPT、图片、Markdown 等文档加载和 OCR；父子块切分。
- BGE-M3 稠密与稀疏混合检索、RRF 融合、可选 BGE Reranker。
- FAQ 优先匹配；未命中后将问题路由到五类业务领域，并选择 Direct、HyDE、SubQuery 或 Backtracking 策略。
- Chroma 持久化子块与父块；按领域元数据过滤。当前是**两个 Chroma collection**，不是场景模板中的五个 Milvus collection。
- FastAPI 问答接口、SSE 流式输出、MySQL 会话历史与摘要、Web 聊天界面。
- 回答要求基于检索资料，引用资料标题；缺少证据时明确说明，不补造工艺参数。涉及停机、放行、PM 等操作应以厂内最新受控文件和审批流程为准。

场景模板里的 Redis 三级缓存、Milvus 五 Collection、Qwen 微调、PIMS/EAM/YMS 对接、权限隔离和 WebSocket 尚未实现。模板中的 95.2% 准确率、8000+ 日请求等数字也不是本项目的实测结果。

## 数据目录

`data/semicon/` 是当前默认索引目录，五个子目录分别是 `process`、`equipment`、`yield`、`cleanroom`、`quality`。每份资料均标注 `DEMO-*` 文档编号、版本和教学用途。`data/semicon_faq.json` 是当前 FAQ。原 `data/` 根目录的 V93K 资料和 `data/eval/v93k_qa_v1.json` 保留作旧项目参考，但不进入默认索引。

要接入实际资料，请先完成权限、脱敏、版本管理与领域审核，再替换演示文件并重建索引。现有实现按文件夹标注领域；同名文件可位于不同领域文件夹。`source_filter` 可按文件 stem 精确限定文档，此时优先于自动领域路由。

## 启动

1. 安装 `requirements.txt`。本地 BGE-M3 权重路径、重排权重路径、LLM 接口和 MySQL 连接信息在 `config.ini` 中配置。敏感配置可使用 `DASHSCOPE_API_KEY`、`MYSQL_PASSWORD` 环境变量覆盖。
2. 在项目根目录执行 `python scripts/build_index.py`，将 `data/semicon/` 建入新的 `semicon_kb` 和 `semicon_kb_parents` 集合。
3. 执行 `python -m uvicorn main:app --host 127.0.0.1 --port 8000`，访问 `http://127.0.0.1:8000/`。
4. 修改 FAQ 后调用 `POST /api/faq/reload`；修改文档后重建索引。旧索引不会自动迁移到新集合。

```json
POST /api/ask
{"question":"刻蚀腔体 particle 超标怎么排查？","stream":false}
```

`GET /api/health` 返回当前模型、collection 和子块数。`POST /api/ask` 返回答案、路径、策略、来源、耗时和会话 ID；`stream=true` 时返回 SSE 事件。

## 评估

`python scripts/run_eval.py --limit 3` 默认读取 `data/eval/semicon_qa_v1.json`。这是一组五领域的初始教学题，未经工艺专家标注。现有 RAGAS 脚本只计算上下文精确度与召回率；不要将其与模板中的问答准确率或综合 RAGAS 分数等同。测试真实参数和操作建议前，应补充经过专家审核的语料与评估集。

## 已知边界

当前文档来源只返回文件标题，无法在 UI 中跳转到厂内文档系统；也没有文档级权限、受控版本自动失效或生产系统集成。回答不能作为产线操作指令。`docs/` 下原 V93K 访谈与痛点笔记是旧项目资料，不代表当前场景的实现状态。
