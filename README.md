# ShopDesk AI（商答台）

面向电商客服场景的商品知识问答助手。用户可以上传商品手册，系统在确认商品型号后检索资料，流式给出回答和相关配图。

## 当前能力

- **手册入库**：支持 Markdown 和 PDF 导入，处理图片、切分正文、识别商品并写入 Milvus。Web 端已实测 Markdown 导入整链，PDF Web 整链未运行。
- **多轮商品问答**：型号不明确时追问，找不到相关商品时说明无法确认；确认后通过向量检索、HyDE 和联网搜索找资料，再融合、重排、生成答案。
- **流式展示与回显**：页面通过 SSE 展示查询进度及正文，完成后显示配图；刷新后可从 MongoDB 读回历史正文与配图。

当前聚焦商品知识问答，尚未接入订单查询、退换货办理或人工转接。扩展范围待讨论，见[项目概览](docs/memory/project-overview.md)。

## 运行与演示

源码位于 [src/shopkeeper_brain](src/shopkeeper_brain/)。项目源自「掌柜智库」带练重建，16 节均已验收；[学习进度](docs/memory/learning-progress.md)保留提交基线和未验证项，[第 16 节验收](docs/memory/day16-acceptance.md)记录了真实查询闭环。

[导入主图](src/shopkeeper_brain/processor/import_processor/main_graph.py)已接通 PDF／Markdown 分支和入库节点。[查询主图](src/shopkeeper_brain/processor/query_processor/main_graph.py)会直接返回已有追问或拒答；确认产品后，用重排资料和近期会话生成答案。各节点的学习期 `__main__` 保留用于单独运行；命令行入口仍是脚手架问候。MongoDB 使用虚拟机服务，联网搜索使用 Tavily 远程 MCP，重排使用阿里云百炼，连接配置见 [.env.example](.env.example)；密钥只填本地 `.env`。

在 PyCharm 直接运行 Web 入口的 `__main__`，访问 `http://127.0.0.1:8000/`。点击「检查服务」会向同源的 `GET /health` 发请求，页面显示 `{"ok":true}`，表示 HTTP 服务可以响应。详见 [Web 入口](src/shopkeeper_brain/api/main.py) 和 [第 13 节教程](docs/study/day13-Web服务骨架.md)。

从首页点「导入手册」上传文件，页面按任务 ID 轮询直到成功或失败；上传和切片产物写入 `workspace/day15-uploads/`。点「查询手册」提交问题，页面用 SSE 显示节点进度和流式正文，完成时显示配图与重排条数；刷新后从 MongoDB 读回最近 5 条消息及配图。导入试跑按[第 15 节教程](docs/study/day15-API前端与流式交互.md)配置实验集合，查询试跑按[第 16 节教程](docs/study/day16-答案输出与项目收敛.md)复用已入库的真实手册并使用独立历史库。已实测 Markdown 导入和手册问答，PDF Web 整链未运行。

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
| [学习进度](docs/memory/learning-progress.md) | 唯一章节状态源、提交基线与未验证项 |
| [教学偏好](docs/memory/teaching-preferences.md) | IDE 真实验证、不使用子 agent 等长期约定 |
| [验收手册](docs/memory/verification-playbook.md) | AI 内部隔离验证与证据记录方式 |
| [规则与设计](docs/superpowers/) | 已确认设计和执行计划；带日期的文件记录当时决策 |
| [协作规则](AGENTS.md) | 本地参考资料只读，教学、验证和 Git 操作按项目约定执行 |

`workspace/` 是唯一实验区，容纳模型、真实输入与输出、临时副本和验证日志，不作为需要提交的学习源码目录。参考项目的 `app/` 等目录不能替代本工程的实际包路径。

## 导入产物如何衔接

第 5 节原始 `chunks.json` 保留切片结果；第 6 节的 `item_name` 回填发生在内存中。第 7 节入口显式恢复主体标签并完成向量化，另存 `workspace/day07-real-run/state_vector.json`，包含名称双向量和全部 Chunk 的双向量；第 8 节直接读取这份状态，分别写入两个 Milvus 集合。

第 8 节只在返回的 `state["chunks"]` 中回填 `chunk_id`，没有覆盖第 7 节备份，也没有另存含主键的新 JSON。后续查询使用数据库中的真实主键，不能假定旧备份已经有 `chunk_id`。两个集合均按 `file_title` 删除旧记录后插入，重复导入会生成新主键；该过程不具备跨删除和插入的事务回滚。

稀疏向量在内存中使用整数特征编号，JSON 对象键会变成字符串；读取备份后需恢复整数键。Dense 为 1024 维并做 L2 归一化，Sparse 保留模型原权重，不能照搬 Dense 的单位范数要求。

Milvus 两类数据的真实入库、索引、重复导入和主键回填已在第 8 节验收；第 9 节已验收产品名称确认（只查 `kb_item_names`），第 10 节已验收带商品过滤的正文向量检索（查 `kb_chunks`），第 11 节已验收 HyDE 与 Tavily 联网搜索，第 12 节已验收 RRF 融合与百炼重排；第 15 节已验收 Web 导入、查询进度与会话历史；第 16 节已验收答案生成、SSE 正文与配图回显。
