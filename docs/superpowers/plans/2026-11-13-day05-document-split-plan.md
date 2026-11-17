# 第 5 节文档切片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 本计划服务于“先写教程、用户手敲、AI 隔离验收”的带练流程；不得直接修改 `src/` 学习代码。

**Goal:** 交付第 5 节“文档切片”施工图纸，让用户从第 4 节真实 Markdown 生成可追溯的 `chunks` 列表和 `chunks.json` 备份。

**Architecture:** 新增独立 `NodeDocumentSplit` 节点，沿用现有 `BaseNode`、`ImportGraphState` 和异常外壳。节点按“输入标准化 → Markdown 标题粗切 → 无标题兜底 → 长块递归切分 → 同归属短块合并 → 元数据、统计和备份”串联；本节不接正式主图，学习期用 `__main__` 直接读取真实 Markdown 验证。

**Tech Stack:** Python 3.11+、uv、`langchain-text-splitters`、现有 LangGraph 状态和项目异常类型。

---

## 文件边界

- 新建教程：[docs/study/day05-文档切片.md](E:/dev/python/project-study/shopkeeper-brain/docs/study/day05-文档切片.md)，只保存业务、原理、手敲代码和真实验证。
- 教程指导用户修改：[pyproject.toml](E:/dev/python/project-study/shopkeeper-brain/pyproject.toml)、[src/shopkeeper_brain/processor/import_processor/state.py](E:/dev/python/project-study/shopkeeper-brain/src/shopkeeper_brain/processor/import_processor/state.py)，以及新增 `src/shopkeeper_brain/processor/import_processor/nodes/node_document_split.py`。
- 后续验收才修改：`docs/memory/day05-acceptance.md`、`docs/memory/learning-progress.md`。
- 验收副本和 `chunks.json`：`workspace/verification/day05/`；不复制 `.env` 或 `__pycache__`。

## Task 1：固化本节契约和依赖

- [ ] 在教程开头写明第 4 节输出 `md_path`、`md_content`，本节只把正文整理成检索前的 Chunk，不重复图片、VL 和 MinIO。
- [ ] 说明输入字段、输出字段、备份文件和跳过范围；把 `md_path` 标为备份所需字段，把 `md_content` 和 `file_title` 标为切片核心输入。
- [ ] 给出 `langchain-text-splitters` 的清华镜像安装/同步命令，并明确命令在教程交付前未运行时不能写成通过。
- [ ] 把参考实现的三个事实差异写入教程：当天压缩包节点仍是占位；课堂代码存在缩进残留和拼写错误；`parent_title` 和带语言标记的代码围栏识别存在缺口。

## Task 2：推导标题粗切和兜底

- [ ] 先用真实 Markdown 的问题说明固定字符切分会丢失章节语境，再说明“标题粗切、长度优化”两级策略。
- [ ] 提供完整的 `_step_1_get_inputs` 和 `_step_2_split_by_titles` 代码：统一 `\r\n`/`\r`，识别 1～6 级 ATX 标题，维护可带语言标记的代码围栏状态，遇标题先 flush 前一节，并为每节写入归属标题。
- [ ] 提供完整的 `_step_3_handle_no_title` 代码，确保无标题 Markdown 仍产生统一章节结构。
- [ ] 给出真实验证：使用第 4 节 `_new.md`确认业务 Markdown 能识别标题；使用真实课堂 Markdown 确认代码围栏内的 `#`不会切成章节。

## Task 3：推导长切、短合和元数据

- [ ] 提供完整的 `_step_4_refine_chunks`、`_split_long_section` 和 `_merge_short_sections` 代码。
- [ ] 使用现行导入路径 `from langchain_text_splitters import RecursiveCharacterTextSplitter`，设置 `chunk_size=available_len`、`chunk_overlap=0`，分隔符依次覆盖段落、换行、中英文句读和空格。
- [ ] 长块重组时保留标题前缀、`file_title`、`parent_title`、`part`；短块只在相同归属标题下合并，合并前删除重复标题文本。
- [ ] 明确 `2000` 是 Python 字符长度上限，不是模型 Token 数；`chunk_overlap=0`降低重复但不提供跨块重叠上下文。
- [ ] 在教程中用一个不依赖外部服务的观察步骤检查：最终每个 Chunk 有 `title`、`content`、`file_title`、`parent_title`，不同标题短块没有跨标题合并。

## Task 4：完成节点、状态和备份代码图纸

- [ ] 提供完整的 `ImportGraphState` 增量代码，增加 `chunks` 字段和默认空列表；保留 `deepcopy`，避免不同状态共享同一列表。
- [ ] 提供完整的 `NodeDocumentSplit` 文件，包含必要导入、两个配置常量、类型别名、`process()`、六个步骤方法和末尾学习期 `__main__`。
- [ ] `process()`按固定顺序串联：输入 → 标题初切 → 无标题兜底 → 长切短合 → 统计 → JSON 备份 → `state["chunks"]`回写，并返回原状态对象。
- [ ] 备份使用 `json.dump(..., ensure_ascii=False, indent=2)`写入 `Path(state["md_path"]).parent / "chunks.json"`；备份失败记录日志但不吞掉切片结果。
- [ ] 不修改当前 `main_graph.py`，教程中解释本节独立入口与正式主图的边界。

## Task 5：编写真实验证步骤

- [ ] 在 `__main__`中读取用户电脑上真实存在的第 4 节 `_new.md`，创建包含 `md_path`、`md_content`、`file_title` 的状态并调用节点。
- [ ] 验证输出文件存在、`state["chunks"]`非空、JSON 可读、JSON 与状态内容一致、每个 Chunk 的元数据完整。
- [ ] 验证输入正文仍可回读，且切片总数和每项长度由实际输出打印，不在教程中预填猜测数字。
- [ ] 明确 `uv sync`、`compileall`、模块导入、真实 Markdown 探针的结果在用户运行前都标记为“未验证”；外部服务不在本节重新调用。

## Task 6：教程自检与隔离代码验证

- [ ] 检查教程标题骨架：承上启下、本节目标、术语、业务原因、手敲步骤、验证、参考对照和小结均存在。
- [ ] 检查所有可落盘代码块前一行紧邻 `**文件**：`，路径相对仓库根目录，代码块包含完整 import 和辅助方法。
- [ ] 在 `workspace/verification/day05/tutorial-code/`复制当前项目的必要文件，抽取教程代码后运行 `uv sync`、`compileall`、模块导入和真实 Markdown 探针；这些命令的结果单独记录，不冒充用户代码验收。
- [ ] 对教程隔离副本做一次破坏性实验：去掉初切阶段的 `parent_title`赋值，确认不同标题短块合并探针失败；恢复后再次运行并记录差异。
- [ ] 只读检查 `git diff --stat`、`git status --short`和教程代码标记；不修改 `reference/`，不提交，不清理历史 `__pycache__`。

## Task 7：等待用户手敲后的验收

- [ ] 用户明确表示手敲完成后，读取真实 `state.py`、`node_document_split.py`、`pyproject.toml`，不拿教程内容代替实现。
- [ ] 将真实学习工程复制到 `workspace/verification/day05/`，运行编译、导入、状态隔离、真实 `_new.md`切片和 `chunks.json`一致性探针。
- [ ] 在隔离副本破坏 `parent_title`归属或 `state["chunks"]`回写，确认探针按预期失败；恢复后再运行正常验证。
- [ ] 按“必须改 / 建议改 / 可选”批改；只有所有必要项通过后，才更新 `day05-acceptance.md`和进度文件，并提供用户自行提交的 Git 提交信息。
