# shopkeeper-brain · 掌柜智库

面向产品手册和技术文档的 RAG 项目带练重建。以只读参考资料为依据，由用户手敲学习代码，AI 负责教程、审阅、隔离验收和文档维护。

章节状态、提交基线、验收范围和下一节门槛统一查看 [学习进度](docs/memory/learning-progress.md)。业务全景与实现边界见 [项目概览](docs/memory/project-overview.md)，协作规则见 [AGENTS.md](AGENTS.md)。

## 现有实现与运行入口

学习代码位于 [src/shopkeeper_brain](src/shopkeeper_brain/)，包括入口路由、PDF 转 Markdown、图片摘要与 MinIO 替换、文档切片、主体识别、BGE-M3 名称和切片双向量化，Milvus 主体名称与 Chunk 入库，以及查询流程骨架、MongoDB 会话历史和产品名称确认。产品确认后的三路检索：正文向量检索（`node_search_embedding`）、HyDE 假设性文档检索（`node_search_embedding_hyde`）和 Tavily 联网搜索（`node_web_search_mcp`），之后是 RRF 融合（`node_rrf`）和百炼 `qwen3-rerank` 重排加断崖截断（`node_rerank`）。真实验证的范围与限制见各节验收记录，最近的记录为[第 14 节验收](docs/memory/day14-acceptance.md)。

当前主要通过各节点文件中的学习期 `__main__` 在 IDE 中运行。最近的真实入库入口为 [node_import_milvus.py](src/shopkeeper_brain/processor/import_processor/nodes/node_import_milvus.py)，先保存主体名称，再批量保存 Chunk 并回填主键。[main_graph.py](src/shopkeeper_brain/processor/import_processor/main_graph.py) 仍只提供入口后的路由函数；声明的命令行入口仍是脚手架问候，正式导入主图和业务 Web 接口按学习进度逐节接入。查询流程在 [query_processor](src/shopkeeper_brain/processor/query_processor/)：主图已接好路由，产品确认（运行入口 [node_item_name_confirm.py](src/shopkeeper_brain/processor/query_processor/nodes/node_item_name_confirm.py)）和三路检索（入口 [node_search_embedding.py](src/shopkeeper_brain/processor/query_processor/nodes/node_search_embedding.py)、[node_search_embedding_hyde.py](src/shopkeeper_brain/processor/query_processor/nodes/node_search_embedding_hyde.py)、[node_web_search_mcp.py](src/shopkeeper_brain/processor/query_processor/nodes/node_web_search_mcp.py)）有真实逻辑，融合与重排（入口 [node_rrf.py](src/shopkeeper_brain/processor/query_processor/nodes/node_rrf.py)、[node_rerank.py](src/shopkeeper_brain/processor/query_processor/nodes/node_rerank.py)）也已实现，只剩答案输出节点是占位。MongoDB 使用虚拟机服务，联网搜索使用 Tavily 远程 MCP，重排使用阿里云百炼，连接配置见 [.env.example](.env.example)（Tavily 地址可留空，Tavily 和百炼的密钥只填本地 `.env`），运行方法见 [第 9 节教程](docs/study/day09-检索流程骨架与产品确认.md)、[第 11 节教程](docs/study/day11-HyDE与网络搜索.md)、[第 12 节教程](docs/study/day12-RRF融合与Rerank重排.md)。

在 PyCharm 直接运行 Web 入口的 `__main__`，访问 `http://127.0.0.1:8000/`。点击「检查服务」会向同源的 `GET /health` 发请求，页面显示 `{"ok":true}`，表示 HTTP 服务可以响应。详见 [Web 入口](src/shopkeeper_brain/api/main.py) 和 [第 13 节教程](docs/study/day13-Web服务骨架.md)。

在同一服务下打开 `/docs`，可用 `POST /demo/preview` 练习 JSON 校验。访问 `/demo/sse` 并点击「开始接收」，浏览器会逐条显示服务端发来的进度，收到 `complete` 后关闭连接。操作与判据见[第 14 节教程](docs/study/day14-FastAPI与SSE.md)。

## 环境准备

- Python 声明为 `>=3.11`，工程选择见 [.python-version](.python-version)。实际验收解释器与依赖版本记录在对应验收文档中。
- 使用 uv 管理依赖，以 [pyproject.toml](pyproject.toml) 和 [uv.lock](uv.lock) 为准；默认 PyPI 源已配置为清华镜像。
- 本地配置参考 [.env.example](.env.example)，在自己的 `.env` 或环境变量中填写；不把有效密钥写进源码、模板或文档。

新环境同步依赖的操作模板如下，执行前按“未验证（未运行）”对待；安装完成只证明环境准备，业务通过仍以真实入口验证为准：

```bash
uv sync --locked --default-index https://pypi.tuna.tsinghua.edu.cn/simple
```

IDE 选择本工程 uv 解释器，具体输入、配置、运行位置与观察判据按对应教程执行。当前不设置项目 pytest 测试套件，也不把隔离行为探针当作 pytest 测试条数。

BGE-M3 的实际路线是 CPU/FP32，模型准备和配置见 [第 7 节教程](docs/study/day07-向量化与稀疏向量.md)。本地模型位于 `workspace/models/bge-m3/`；该目录及运行产物被 Git 忽略，新环境需要自行准备，不能把缓存目录名当作权重已经齐全。

第 8 节使用虚拟机上的 Milvus `http://192.168.150.120:19530`；验收时服务端为 2.5.5、PyMilvus 为 3.0.3。主体集合为 `kb_item_names`，正文集合为 `kb_chunks`，配置变量见 [.env.example](.env.example)，运行方法见 [第 8 节教程](docs/study/day08-Milvus向量入库.md)。后续使用前只读确认虚拟机、连接和集合状态，不重新部署或清空已有服务；历史验收不代表服务此刻在线。

## 文档与目录

| 入口 | 内容 |
| --- | --- |
| [学习教程](docs/study/) | 按业务顺序交付的手敲教程；固定讲法参照 [第 6 节](docs/study/day06-主体识别.md) |
| [学习进度](docs/memory/learning-progress.md) | 唯一章节状态源、提交与接手门槛 |
| [教学偏好](docs/memory/teaching-preferences.md) | IDE 真实验证、不使用子 agent 等长期约定 |
| [验收手册](docs/memory/verification-playbook.md) | AI 内部隔离验证与证据记录方式 |
| [规则与设计](docs/superpowers/) | 已确认设计和执行计划；带日期的文件记录当时决策 |
| [参考区规则](reference/AGENTS.md) | 原资料只读，按视频目录图片、课堂资料、补充笔记的顺序核对 |

`workspace/` 是唯一实验区，容纳模型、真实输入与输出、临时副本和验证日志，不作为需要提交的学习源码目录。参考项目的 `app/` 等目录不能替代本工程的实际包路径。

## 导入产物如何衔接

第 5 节原始 `chunks.json` 保留切片结果；第 6 节的 `item_name` 回填发生在内存中。第 7 节入口显式恢复主体标签并完成向量化，另存 `workspace/day07-real-run/state_vector.json`，包含名称双向量和全部 Chunk 的双向量；第 8 节直接读取这份状态，分别写入两个 Milvus 集合。

第 8 节只在返回的 `state["chunks"]` 中回填 `chunk_id`，没有覆盖第 7 节备份，也没有另存含主键的新 JSON。后续查询使用数据库中的真实主键，不能假定旧备份已经有 `chunk_id`。两个集合均按 `file_title` 删除旧记录后插入，重复导入会生成新主键；该过程不具备跨删除和插入的事务回滚。

稀疏向量在内存中使用整数特征编号，JSON 对象键会变成字符串；读取备份后需恢复整数键。Dense 为 1024 维并做 L2 归一化，Sparse 保留模型原权重，不能照搬 Dense 的单位范数要求。

Milvus 两类数据的真实入库、索引、重复导入和主键回填已在第 8 节验收；第 9 节已验收产品名称确认（只查 `kb_item_names`），第 10 节已验收带商品过滤的正文向量检索（查 `kb_chunks`），第 11 节已验收 HyDE 与 Tavily 联网搜索，第 12 节已验收 RRF 融合与百炼重排；答案输出和 Web 交互等能力仍按学习进度推进，不能把入库、检索或重排通过当作查询链路已经就绪。
