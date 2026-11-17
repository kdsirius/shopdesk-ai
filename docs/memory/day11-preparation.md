# 第 11 节资料与教程备课记录：HyDE 与网络搜索

本文件记录第 11 节资料事实、设计取舍和教程副本验证事实。章节状态只维护在 [学习进度](learning-progress.md)；本记录不代表用户手敲代码验收。

## 资料事实

- day11 视频目录（截图 1 至 3）：07 是导入流程的全流程测试，08 至 13 是 HyDE（概念与单测、流程、生成假设文档、LLM 工具类、向量查询、测试），14 至 17 是阿里云百炼 MCP（开通准备、定义 MCP 方法、调用 MCP 方法）。对应课堂笔记 `14`、`15`，补充笔记 `1.笔记/16`、`17`。
- 视频 07 没有对应课堂笔记；导入主图 `import_processor/main_graph.py` 目前只有入口路由，没有可串联的流程，经用户确认不并入本节，留待后面导入主图或服务集成时处理。
- 代码来自 `day11/knowledge_base.zip`（文件名为 GBK 编码，只在内存读取，没有解压）：`node_search_embedding_hyde.py`、`node_web_search_mcp.py`、`bailian_mcp_config.py`、`llm_utils.py`、提示词模块。
- 参考的 `NodeSearchEmbeddingHyde` 返回 `hyde_doc`，但参考和本工程的查询状态里都没有该字段。实测 LangGraph 对 TypedDict 状态里未声明的返回键是静默丢弃，不报错；本工程不返回 `hyde_doc`，假设文档只写日志。

## 设计取舍

- 联网搜索改用 Tavily 远程 MCP（用户已有 Tavily 密钥，不用百炼）。用户同意后，客户端选官方 `mcp` 包而不是参考的 `openai-agents`：少一层依赖，协议相同。副本解析到 `mcp 2.3.0`（接口为新版：`Client`、`is_error`、HTTP 库是 `httpx2`，需要用 `httpx2.AsyncClient(headers=...)` 带 `Authorization`）；Windows 上还会装入 `pywin32`。
- 配置新增 `core/tavily_config.py`，变量为 `SHOPKEEPER_BRAIN_TAVILY_MCP_URL`、`SHOPKEEPER_BRAIN_TAVILY_API_KEY`。用户 `.env` 里地址留空，代码空值回落官方地址 `https://mcp.tavily.com/mcp/`；密钥用 `SecretStr`，不进日志。
- 失败策略（用户确认）：HyDE 和网络搜索是辅助路，运行期故障记 `ERROR` 日志并返回空列表；输入契约错误（`StateFieldError`）仍抛出。第 10 节向量检索作为主路保持异常外抛。
- 参考的 HyDE 用 `f'item_name in {item_names}'`、空列表全库检索；本节复用第 10 节 `NodeSearchEmbedding._build_item_filter()`，名称转义，空列表拒绝。召回规模沿用 `PER_ROUTE_LIMIT=10`、`RESULT_LIMIT=5`。
- 参考的网络搜索对 Tavily 无对应；字段映射为 Tavily `content` → `snippet`，截取 500 字（实测 Tavily 的 content 可是整页参数表或视频字幕，长度约 1300 至 1500 字）。参考的 `logger.info("MCP 搜索结果:", docs)` 缺少占位符，本节没有照搬。
- 发现的真实陷阱：Tavily 密钥无效时 MCP 的 `is_error` 为 `False`，内容是 `{"error": ..., "status": 401}`。只写 `.get("results") or []` 会静默得到空列表，教程节点在无 `results` 时抛异常再降级。
- `asyncio.run()` 在 LangGraph 同步节点（线程池线程）里可用，主图并行三路实测通过。MCP 客户端的错误包在 `ExceptionGroup` 里，节点剥到最内层再记日志。

## 教程副本验证事实（2026-11-17）

- 隔离副本：`workspace/verification/day11/tutorial-20261117/project/`（复制 `src/`、锁文件和本地 `.env`），副本里 `uv add --no-sync mcp` 解析通过；`mcp` 等依赖装在 `workspace/verification/day11/site/`，用 `run_node.py` 把副本源码和该目录加入路径，没有改动根虚拟环境，也没有改动用户 `pyproject.toml`、`uv.lock`。运行器和边界探针是 `run_node.py`、`probes.py`。
- 开始前只读核对：Milvus 有 `kb_item_names`（1 条）、`kb_chunks`（21 条，已加载）和两个 `verify_d08_*` 实验集合；MongoDB ping 成功。
- 教程三个完整文件块与副本逐字一致（脚本比对）；两张 Mermaid 图、三块正文结构检查通过。
- 真实 Tavily MCP（本机直连，无代理）：5 条结果，格式化后全部保留，摘要截到 500 字。
- 真实本地文本模型 + BGE-M3 + Milvus 的 HyDE 入口运行了三次：第一条均为“交流电压测量”，评分 0.9048、0.9088、0.9100（直接检索第一条 0.8723）；每次 5 条里有 1 条仅 HyDE（`电阻测量`），其余与直接检索相同。
- 边界探针（AI 自行执行，不写进教程）：HyDE 缺 `rewritten_query`、空白问题、缺 `item_names`、空列表、含空字符串均抛 `StateFieldError`；网络节点缺或空白问题同样抛出；带引号反斜杠的名称不报错且召回 0 条；不存在的产品 0 条，混合名称 5 条。降级：文本模型地址不可达、模型密钥为空、Tavily 密钥为空、无效（401）、地址不可达，均返回空列表并留下 `ERROR` 日志，原因可读。格式化函数对空白正文、缺字段、非字典项、超长正文处理正确。
- 查询主图（副本，真实文本模型、Milvus、Tavily，MongoDB 临时库 `verify_d11_tut1117`、`verify_d11_tut1117b`）：拒答问题不进入检索；确认问题三路并行，日志为向量检索“召回 5 个 Chunk”、HyDE“召回 5 个 Chunk”、联网搜索“保留 5 条”，随后汇合到 RRF、Rerank、答案输出。三个临时库均已删除，正式库 `kb001` 未触碰。
- 破坏性实验（隔离副本）：把 HyDE 请求里的 `expr=expr` 改成 `expr=None` 后，不存在的产品和带引号名称都召回 5 条（正常为 0），说明过滤必须带进 HyDE 的检索；恢复后文件哈希与改前一致。网络节点去掉 `results` 检查的情形，由探针发现密钥 401 被静默吞掉的真实现象代替，已修复进教程。

## 未运行

- 没有运行用户第 11 节源码；教程交付不等于章节通过。
- `.env.example` 在本节开始后出现了用户自己追加的 Tavily 两行（未提交），内容与教程一致，没有代改。
- 没有在 FastAPI/异步环境下验证节点（当前图是同步执行）；没有验证 Tavily 的限流、额度耗尽和长时间超时行为；没有验证 BGE-M3 在 GPU 上的行为。
- 没有用多个名称写法的真实数据验证 HyDE 的商品过滤，库里只有一个产品。
