# 第 5 节验收记录：文档切片

- 验收日期：2026-11-14
- 用户真实代码：`src/shopkeeper_brain/processor/import_processor/nodes/node_document_split.py`
- 第二轮隔离验收副本：`workspace/verification/day05/formal-acceptance-20261114-rerun/`
- 第一轮隔离验收副本：`workspace/verification/day05/formal-acceptance-20261114/`
- 自动化测试：本节没有新增自动化测试文件；测试条数记为无自动化测试。

## 验收范围

本节按文档切片完整职责验收：状态增加 `chunks`、Markdown 标题粗切、首个标题前正文、带语言标记代码围栏、无标题兜底、长章节递归切分、同归属短块合并、元数据、`chunks.json` 备份和学习期真实入口。

本节不调用 VL、MinIO、MinerU、Milvus 或 MongoDB；图片处理链路属于第 4 节已通过范围。

## 隔离环境

用户真实工程复制到第二轮隔离目录，没有复制 `.env` 和 `__pycache__`。真实输入使用第 4 节生成的 RS-12 Markdown `_new.md`；代码围栏探针使用真实 day05 课堂 Markdown。

- CPython 3.13.12：第二轮隔离环境实际使用版本；项目声明的 Python 3.11 最低版本未在本节单独复验。
- `uv sync`：通过，解析并检查 `langchain-text-splitters==1.1.3`。
- `compileall`：通过。
- 模块导入：通过，`NodeDocumentSplit().name` 为 `node_document_split`。
- 状态隔离：通过，两个默认状态的 `chunks` 列表互不共享。

## 第一轮发现与修正

第一轮用户代码真实入口生成 20 个 Chunk，基础流程能完成，但隔离探针发现三项必须修正：

1. `flush_section()`用 `if not current_title`丢弃了第一个 Markdown 标题前的真实正文；改为判断 `current_lines`后，前置章节得到保留。
2. 短块合并时把 `next_content`误写成 `next_parent[...]`，同归属子块正文会丢失；改为从 `next_content`本身删除重复父标题。
3. `md_path`只检查空字符串，没有拒绝空白路径；改为 `not md_path.strip()`。

用户同时恢复了真实课堂代码围栏探针。

## 第二轮验证结果

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 用户真实源码读取 | 通过 | 修订后的 `node_document_split.py`已复核 |
| `uv sync` | 通过 | 第二轮副本重新执行，退出码 0 |
| `compileall` | 通过 | 第二轮副本退出码 0 |
| 模块导入 | 通过 | 输出 `node_document_split` |
| 状态列表隔离 | 通过 | 第二轮独立状态探针通过 |
| 真实 RS-12 Markdown | 通过 | 330 行、20 个标题、21 个 Chunk |
| 首个标题前正文保留 | 通过 | 前置正文存在于最终 Chunk 中 |
| `chunks.json`生成 | 通过 | 真实输入目录生成备份 |
| 状态与 JSON 一致 | 通过 | `state["chunks"] == chunks.json` |
| Chunk 元数据 | 通过 | `title`、`content`、`file_title`、`parent_title`均存在 |
| 代码围栏保护 | 通过 | 真实课堂 Markdown 中 `# 作用：...`未被识别为标题 |
| 空白 `md_path`边界 | 通过 | 抛出 `StateFieldError` |
| 同归属短块合并 | 通过 | 后续子块正文保留 |
| 真实入口退出 | 通过 | `状态与 JSON 备份一致：通过`、`文档切片：通过`、代码围栏通过 |
| 外部服务 | 跳过 | 本节职责不依赖 VL、MinIO、MinerU 等服务 |

仓库现有真实 Markdown 没有自然触发“首个子块小于 500 字”的短块合并候选，因此同归属短块修正使用了隔离副本定向边界探针验证；第一轮该探针按预期失败，修正后通过。

## 结论

第 5 节状态更新为 `已通过`。通过范围包括：真实 Markdown 切片、首个标题前正文、代码围栏保护、状态回写、JSON 备份、元数据、空白路径边界和同归属短块合并正文保留。

下一节是第 6 节“主体识别”，对应 `reference/掌教智库/4.视频/day06/`。进入下一节前，保持第 5 节代码和验收记忆不再改动。
