# 第 6 节主体识别 Implementation Plan

> 本计划服务于“先写教程、用户手敲、AI 隔离验收”的带练流程；不得直接修改 `src/` 学习代码。2026-11-15 按用户要求重构第 6 节讲法，后续以 `docs/AGENTS.md` 和 `docs/memory/teaching-preferences.md` 为教学规格；不回改前五节，不使用子 agent。

**Goal:** 交付第 6 节“主体识别”施工图纸，让用户从第 5 节真实 `chunks` 中识别文档主体，并把 `item_name` 回填到状态和每个 Chunk。

**Architecture:** 沿用当前 `BaseNode`、`ImportGraphState`、项目异常类型和学习期 `__main__` 入口。节点按“输入校验 → 前 3 个 Chunk 上下文压缩 → 文本 LLM 识别 → 清洗与文件标题兜底 → 状态和 Chunk 回填”串联。本节不接正式主图，不生成向量，不写 Milvus。

**Tech Stack:** Python 3.11+、uv、现有 `langchain-openai`、OpenAI 兼容文本模型接口、现有状态和异常外壳。

---

## 资料事实和口径

- 物理 `4.视频/day06/` 仍是文档切片资料；day06 业务主题的主体识别资料位于 day07/day08 目录。
- day07 代码实际完成输入校验和上下文构建，day08 代码补齐 LLM 识别、回填及后续向量/Milvus步骤。
- 本节使用 day07/day08 的主体识别事实，向量化和入库按章节表留给第 7、8 节。
- 补充 `1.笔记/08...主体识别.md` 只用于解释业务关系和核对完整流程，不覆盖当天代码事实。

## 文件边界

- 新建教程：[docs/study/day06-主体识别.md](E:/dev/python/project-study/shopkeeper-brain/docs/study/day06-主体识别.md)，只保存业务、原理、手敲代码和真实验证。
- 教程指导用户修改：[src/shopkeeper_brain/processor/import_processor/state.py](E:/dev/python/project-study/shopkeeper-brain/src/shopkeeper_brain/processor/import_processor/state.py)、`.env.example`。
- 教程指导用户新增：`src/shopkeeper_brain/core/llm_config.py`、`src/shopkeeper_brain/processor/import_processor/nodes/node_item_name_recognition.py`。
- 不修改当前 `main_graph.py`，不重复第 5 节节点和备份逻辑，不新增自动化测试文件。
- 后续验收才修改 `docs/memory/day06-acceptance.md`和进度文件。
- 验收副本、输入复制品和日志统一放在 `workspace/verification/day06/`；不复制 `.env` 或 `__pycache__`。

## Task 1：固化本节契约和边界

- [ ] 在教程开头说明第 5 节留下的 `file_title`、`chunks` 是本节输入，`item_name` 是本节新增状态字段。
- [ ] 明确主体识别是文档级标签传播，不是给每个 Chunk 独立分类。
- [ ] 明确 K=3、上下文上限 2500 字符的代码事实；K=5 的差异就近短讲，资料目录分布的详细依据留在设计说明，不在教程另列汇总。
- [ ] 明确本节不重复标题切分、代码围栏、`chunks.json`备份，不进入 BGE-M3 或 Milvus。

## Task 2：补齐状态和文本模型配置

- [ ] 在完整 `ImportGraphState` 中增加 `item_name: str`及默认空字符串。
- [ ] 新增文本模型配置读取模块，沿用当前 `core/` 配置风格和 `SHOPKEEPER_BRAIN_` 前缀。
- [ ] 仅给出 `.env.example`末尾的四行追加配置，副本验证时按定位追加；不重贴无关旧配置，不读取或覆盖本地 `.env`。
- [ ] 不新增依赖，使用现有 `langchain-openai`。

## Task 3：完成主体识别节点

- [ ] 提供完整 `NodeItemNameRecognition` 文件和类型标注。
- [ ] `_step_1_get_inputs`校验非空 `file_title`及非空列表 `chunks`。
- [ ] `_step_2_build_context`只读取前 3 个 Chunk，按标题和内容格式化，并截断到 2500 字符。
- [ ] `_step_3_call_llm`调用 OpenAI 兼容文本模型，要求只返回主体名称；使用 `response.text.strip()` 提取消息正文、仅去首尾空白并保留名称内部空格；空结果、配置缺失和异常统一回退到 `file_title`。
- [ ] `_step_4_update_chunks`将同一个 `item_name`写入状态和所有 Chunk。
- [ ] `__main__`只读取用户真实 `chunks.json`，打印识别和回填结果，不生成新的 JSON 备份。

## Task 4：编写真实验证步骤

- [ ] 只沿用“业务流程与设计原因 → 手敲步骤 → 必做真实验证”，以本项目第 3 节及只读团购项目的教学约定为依据，不套回阶段探针模板。
- [ ] 指导用户准备真实 `chunks.json`和文本模型配置，在 IDE 选择 uv 解释器，修改 `__main__` 中的路径并直接 Run/Debug，无需运行参数。
- [ ] 指明断点位置，观察模型调用前的上下文、返回后的消息及最终状态；上下文最多 3 个 Chunk、不超过 2500 字符。
- [ ] 验证全部 Chunk 的主体名称与状态一致，原正文保留；区分真实模型返回和文件标题兜底，不用末尾断言代替真实识别证据。
- [ ] 逐项给出失败现象、定位方法和退出条件；资料摸底、环境流水、构建输出和验收表不写入教程。
- [ ] 模块导入、缺少输入和边界探针由 AI 在隔离副本完成，不增加用户的终端测试作业；BGE-M3、Milvus仍在后续章节。

## Task 5：教程自检与隔离代码验证

- [ ] 检查正文只含三块主线，图后有白话，代码旁有设计原因，真实验证包含 IDE 操作、观察点和失败定位。
- [ ] 检查完整文件块前紧邻 `**文件**：`和仓库相对路径；追加配置片段不按整文件抽取。
- [ ] 在 `workspace/verification/day06/tutorial-refactor-20261115/project/`复制当前必要文件与锁文件，抽取三个完整 Python 文件，按教程追加配置模板后运行编译、导入、真实上下文边界和兜底回填。
- [ ] 在隔离副本验证缺少输入、空上下文和回填守护；只在副本破坏回填，恢复字节后重新验证。真实模型未调用时明确记录未运行。
- [ ] 核对前五节、用户源码、真实 JSON、只读团购文档的哈希和团购工作区基线不变；本项目仅保留必要文档变更，不提交或清理历史文件。

## Task 6：等待用户手敲后的验收

- [ ] 用户明确表示手敲完成后，读取真实 `state.py`、`llm_config.py`、`node_item_name_recognition.py`和 `.env.example`，不拿教程内容代替实现。
- [ ] 将真实学习工程复制到 `workspace/verification/day06/`，运行编译、导入、上下文边界、异常输入和真实 `chunks.json`回填验证。
- [ ] 至少进行一次隔离副本破坏性实验，确认移除 `item_name`回填后探针失败；实验不要求用户执行，也不写入教程步骤。
- [ ] 按“必须改 / 建议改 / 可选”批改；必要项通过后才新增 `day06-acceptance.md`并更新进度为“已通过”。
