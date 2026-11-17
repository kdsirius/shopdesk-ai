# 第 9 节验收记录：检索流程骨架与产品确认

2026-11-17 对用户手敲的真实源码做了验收。章节状态只维护在 [学习进度](learning-progress.md)。

## 验收方式

- 读取用户真实源码，复制到 `workspace/verification/day09/formal-acceptance-20261117/project/`（首轮）和 `formal-acceptance-20261117-rerun/project/`（修订后复验），副本与用户 `src/` 逐字节一致；CPython 3.11.15，PyMongo 4.20.0，PyMilvus 3.0.3。
- 检查脚本沿用教程验证的 23 项：配置与连接、MongoDB 历史工具、第 4 至第 8 步各步骤、两轮对话、主图路由，以及名称检索评分。MongoDB 逻辑部分用 mongomock（不是真实服务），文本模型用脚本化的假客户端。
- 名称检索使用真实 BGE-M3 与虚拟机 Milvus 的 `kb_item_names`，只读。

## 首轮发现与修订

- 首轮 22 项通过、1 项失败：`_step_6_align_item_names` 缺少 `continue`，确认的商品名同时进了候选列表。分支结果不受影响，因为候选只在没有确认商品时使用，但与教程不一致。
- 另外两处不一致：`main_graph.py` 放在了 `nodes/` 目录下，教程要求放在 `query_processor/`；提示词每行多了 8 个缩进空格。
- 用户三处都已修订；复验 23 项全部通过，原样运行两个学习期入口也通过。用户同时把导入包改名为 `import_processor`，教程已同步。

## 真实服务证据

- 虚拟机 MongoDB：用用户 `.env` 里的连接，在临时库 `verify_d09_58acaab5` 上原样运行 `mongo_history_utils.py` 入口，认证、读写、顺序、批量回填均通过；临时库用完已删除，没有触碰 `kb001`。
- 真实文本模型：用户在 IDE 运行节点入口的日志显示接口返回 200。拒答一次：提取 `iPhone 15`，评分约 0.529，分支 C，历史里是用户消息和拒答。两句对话一次：`RS-12` 评分约 0.760，分支 B；第二句模型从历史解析出完整名称，评分约 0.919，分支 A，三条历史消息都回填了商品名。
- Milvus 评分：完整名称 A、`RS-12` 与 `万用表` B、`iPhone 15` 与 `示波器` C，与教程预期一致。

## 跳过或未运行

- 主图在真实文本模型下的运行没有单独验证：主图用脚本化模型加真实检索验证了路由，节点本身的真实模型行为见上面的用户日志。
- 没有自动化测试文件，测试条数记为无自动化测试。

## 环境备注

- 验收中途根 `.venv` 的 Python 启动器一度报 `uv trampoline failed to spawn Python child process`，原因是 uv 的 Python 目录符号链接被 Windows 拒绝遍历（错误 448）。验收改为直接使用 `cpython-3.11.15` 解释器并挂载根环境的 site-packages；用户 IDE 运行不受影响。
