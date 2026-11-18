# 第 12 节资料与教程备课记录：RRF 融合与 Rerank 重排

本文件记录第 12 节资料事实、设计取舍和教程副本验证事实。章节状态只维护在 [学习进度](learning-progress.md)；本记录不代表用户手敲代码验收。

## 资料事实

- day12 视频目录（三张截图，共 19 项）：01 是 day11 回顾，02 至 08 是 RRF（公式、为什么需要、k 值、单元测试、倒数排名融合、数据融合与测试），09 至 17 是 Rerank（重排概念、交叉编码与两阶段检索、断崖检测、组装 rrf 与 mcp 数据、配置与调用千问 rerank、获取排序结果、断崖截断）。day12 的课堂笔记文件夹混着 01 至 17 全部笔记，本节只用 `16`、`17`，补充笔记为 `1.笔记/18`、`19`。
- 代码来自 `day12/knowledge_base.zip`（文件名 GBK，只在内存读取，没有解压）：`node_rrf.py`、`node_rerank.py`、`reranker_http_utils.py`、`reranker_config.py`、状态定义。
- 重排服务：阿里云百炼 DashScope 的 `qwen3-rerank`（`dashscope.TextReRank.call`），需要百炼 API 密钥；参考把密钥借用 `OPENAI_API_KEY`。参考 `.env.example` 里还有 `BGE_RERANKER_LARGE` 一类本地重排配置，但节点没有使用。官方文档：单次最多 500 条文档，单条不超过 4000 Token，`results` 按分数降序并带原 `index`，分数只在同一次请求内可比。
- 用户 `.env` 里没有任何重排或百炼配置，本机环境变量里也没有；文本模型走本地网关，不提供重排接口。用户确认选择“与参考一致，用阿里云”。

## 设计取舍与参考缺陷

- `dashscope 2.1.0` 的 `TextReRank` 仍可用（在 `legacy_1x` 下），支持 `api_key=` 参数，本节用参数而不是全局变量；官方文档页给的是新写法 `Client(...).rerank.create`，教程沿用资料的 `TextReRank.call`，没有改用新接口。
- 配置变量：`SHOPKEEPER_BRAIN_RERANK_MODEL`（留空用 `qwen3-rerank`）、`SHOPKEEPER_BRAIN_RERANK_INSTRUCT`（留空表示不传；官方建议英文）、`SHOPKEEPER_BRAIN_RERANK_API_KEY`。文件 `core/rerank_config.py`、`utils/rerank_utils.py`（不沿用参考的 `reranker_http_utils.py`，因为实际用 SDK）。
- RRF：k=60，两路权重 1.0，联网搜索不参与（没有 `chunk_id`）。参考的 `max_results` 在课堂笔记、zip、补充笔记里分别是无、5、10，本节不设上限：两路各 5 条，并集最多 10 条。参考没有处理空字段之外的畸形项，本节跳过没有 `chunk_id` 的项。
- 重排：参考有四处缺陷，教程已逐条修正：直接遍历 `state.get(...)`（字段缺失会抛 `TypeError`）；降级分支 `[{**merged_multi_docs, "score": None}]` 把列表用 `**` 展开（降级分支本身会抛 `TypeError`）；分数列表长度取 `len(results)`；标题取 `rrf_doc.get('title')` 而本工程 Chunk 实体没有 `title`（改用 `item_name`）。
- 降级策略（本节设计，未经用户另行确认）：重排出错时只保留本地结果，沿用 RRF 顺序，分数为 `None`；联网结果丢弃，因为重排是它唯一的相关性把关。断崖检测遇到 `None` 跳过。契约错误（缺 `rewritten_query`）仍抛 `StateFieldError`。
- 断崖检测沿用参考常量：最少 3 条、最多 10 条、绝对差 0.5、相对差 0.25；前 3 条之间的落差不检查（循环从下标 2 开始）。

## 教程副本验证事实（2026-11-17）

- 隔离副本：`workspace/verification/day12/tutorial-20261117/project/`（复制 `src/`、锁文件和本地 `.env`）；`dashscope 2.1.0` 装在 `workspace/verification/day12/site/`，运行器 `run_node.py` 把副本源码放在前、该目录放在后，没有改动根虚拟环境、`pyproject.toml`、`uv.lock`。副本里 `uv add --no-sync dashscope`（清华源）解析通过，只新增 `"dashscope>=2.1.0"` 一行。
- 教程四个完整文件块与副本逐字一致（脚本比对），编译通过，两张 Mermaid 图、三块结构检查通过。
- 真实两路检索 + RRF 的学习期入口运行通过：向量检索 5 条、HyDE 5 条，融合 6 条；两路都排第 1 的“交流电压测量”得分 0.032787，名次 2、3 和 3、2 的两条同分 0.032002 且按先出现的顺序，只命中一路的 0.015625。
- 查询主图（副本，真实文本模型、Milvus、Tavily，MongoDB 临时库 `verify_d12_tut1117`，已删除，正式库未触碰）：拒答问题不进入检索；确认问题三路并行，RRF 融合 7 条，重排待处理 12 条，因本机没有重排密钥走降级、保留 7 条本地结果，日志 `ERROR ... ConfigurationError: 重排密钥未配置`。
- 重排调用形态：用故意写错的密钥真实请求百炼，得到 `RuntimeError: DashScope 重排调用失败：401 Invalid API-key provided.`，说明 SDK 调用参数和失败路径正确；这不是重排打分的证据。
- AI 边界探针 25 项通过（不写进教程，脚本 `probes.py`）：RRF 两路缺字段/为空/只有一路/畸形项、公式值 1/61+1/63、权重、同分稳定；合并时空正文丢弃、字段统一、两个字段为 `None`；契约抛 `StateFieldError`；无文档不调用服务；断崖截断（绝对断崖、相对断崖、平稳全留、上限 10、不足 3 条、全 `None`、前 3 条之间的落差不检查）；降级只保留本地、顺序不变。探针中两处期望值是我写错的（同分顺序、前 3 条的落差），已按参考真实语义更正，不是代码缺陷。

## 未运行

- **真实重排打分未运行**：没有百炼密钥，`rerank_documents` 返回真实分数、相关/无关文档的分数差、`qwen3-rerank` 对联网噪声页的过滤效果、断崖检测在真实分数上的截断位置都没有验证。教程中对应的判据是预期现象，已标“未验证（未运行）”。
- 没有运行用户第 12 节源码；教程交付不等于章节通过。没有验证百炼限流、超长文档（超 4000 Token）、500 条上限、`instruct` 参数的实际效果。
- 没有在 FastAPI/异步环境下验证节点。
