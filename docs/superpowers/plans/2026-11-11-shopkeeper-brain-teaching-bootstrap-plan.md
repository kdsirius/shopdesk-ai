# shopkeeper-brain 教学初始化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可跨会话继续的带练项目规则、记忆与进度，并产出严格对齐原项目的 16 节学习路线和第 1 节施工图纸。

**Architecture:** 以 `reference/掌教智库` 为只读事实源；根规则负责全局边界，`reference/AGENTS.md` 和 `docs/AGENTS.md` 负责局部差异。学习文档按 `day01` 至 `day16` 一一对应，进度和验收事实统一记录在 `docs/memory/`，实验副本统一放入被忽略的 `workspace/`。

**Tech Stack:** Python 3.11、uv、LangGraph、FastAPI、Milvus、MongoDB、MinIO、Markdown、Mermaid。

---

## 文件地图

- `AGENTS.md`：仓库级工作边界、中文沟通、用户手敲、reference 只读、Git 只读、验证总规则。
- `CLAUDE.md`：只包含 `@AGENTS.md`，避免规则重复。
- `.gitignore`：只新增 `workspace/`，保证实验产物不进入工作区变更。
- `reference/AGENTS.md`：参考资料只读、引用路径、禁止运行压缩包内代码的局部规则。
- `docs/AGENTS.md`：学习文档、记忆、进度和图片的局部规则。
- `docs/memory/project-overview.md`：项目目标、原项目技术栈和初步目录地图。
- `docs/memory/learning-progress.md`：16 节唯一进度源、当前卡点、欠账和实测基线。
- `docs/memory/verification-playbook.md`：Python/uv 版抽取、运行、破坏性实验和验收清单。
- `docs/study/day01-项目定位与最小骨架.md` 至 `docs/study/day16-答案输出与项目收敛.md`：恰好 16 节施工图纸。
- `workspace/`：被忽略的实验目录，只保存临时副本、脚本、日志和测试输出。

## Task 1: 固化仓库边界与实验区

**Files:**
- Create: `.gitignore`
- Create: `AGENTS.md`
- Create: `CLAUDE.md`
- Create: `reference/AGENTS.md`
- Create: `docs/AGENTS.md`

- [ ] **Step 1: 写入实验区忽略规则**

`.gitignore` 只写一行：

```gitignore
workspace/
```

- [ ] **Step 2: 写入根规则**

根 `AGENTS.md` 固定包含五段：开始之前、仓库地图、工作模式、硬性规则、验证。内容必须明确：

- 使用中文；先读取真实文件再修改文档或代码。
- `reference/` 只读；用户负责手敲学习代码，AI 负责教程和验收。
- Git 只做 `status`、`log`、`diff`、`check-ignore` 等只读操作，不执行提交、推送、重置或删除。
- `workspace/` 是唯一实验区；临时脚本、复制工程、输出和日志放这里。
- uv 命令涉及安装依赖时追加清华源配置，密钥只放 `.env`，提交模板使用 `.env.example`。
- 验收必须区分通过、失败、跳过、未运行，测试条数只来自真实输出。

- [ ] **Step 3: 写入转发文件和局部规则**

`CLAUDE.md` 内容只能是：

```text
@AGENTS.md
```

`reference/AGENTS.md` 只写参考区局部差异：禁止修改、解压覆盖、格式化和运行未知压缩包代码；引用原资料时保留相对路径。

`docs/AGENTS.md` 只写文档区局部差异：学习文档只写业务/原理/流程、手敲代码、真实验证；代码块采用 `**文件**：` 标记；进度状态只能使用四种值；图片放 `docs/study/images/` 并使用相对路径。

- [ ] **Step 4: 验证规则文件和忽略规则**

运行：

```bash
git check-ignore -v workspace/probe.txt
wc -l AGENTS.md CLAUDE.md reference/AGENTS.md docs/AGENTS.md
```

预期：第一条输出 `.gitignore` 对 `workspace/probe.txt` 的匹配行；四个规则文件存在且 `CLAUDE.md` 为一行。若 `git check-ignore` 无输出，先修正 `.gitignore`，不继续后续任务。

## Task 2: 建立项目记忆和唯一进度源

**Files:**
- Create: `docs/memory/project-overview.md`
- Create: `docs/memory/learning-progress.md`
- Create: `docs/memory/verification-playbook.md`

- [ ] **Step 1: 写入项目全景记忆**

记录已确认事实：

- 参考项目路径为 `reference/掌教智库/`。
- 视频目录为 `day01` 至 `day16`。
- 主业务链路为文档导入、向量入库、多路检索、RRF、Rerank、答案生成、FastAPI/SSE。
- 初步目录为 `api / core / processor / schema / services / utils / front`。
- 新项目名为 `shopkeeper-brain`，Python 包名为 `shopkeeper_brain`，配置前缀为 `SHOPKEEPER_BRAIN_`。
- 原项目优先；发现缺陷时才记录并讨论修正。

- [ ] **Step 2: 写入学习进度**

按模板创建 `learning-progress.md`：

- 项目信息写明新项目、参考项目、uv 管理；构建命令和测试命令在代码工程建立前标记为“未确定，尚未运行”，不得伪造基线。
- 章节表列出 16 行，标题使用 Task 3 的确切文件标题，状态全部为 `未开始`。
- 当前卡点记录“尚未建立学习代码工程；下一步完成规则和第 1 节图纸”。
- 欠账记录外部服务尚未启动、原始压缩包未执行验证。

- [ ] **Step 3: 写入 Python/uv 验收手册**

`verification-playbook.md` 固定说明：

1. 读取用户真实工程。
2. 将工程复制到 `workspace/verification/<递增编号>/`。
3. 从教程中的 `**文件**：` 标记抽取代码块并覆盖临时副本。
4. 运行 `uv sync`、测试命令和行为探针；每条命令记录真实输出。
5. 修改关键行前先确认文件内容，跑失败实验后恢复并用 `git diff --no-index` 或哈希核对。
6. 对无法复现的外部服务、掉电和真实网络分区记录欠账。

- [ ] **Step 4: 验证进度格式**

运行：

```bash
rg -n "未开始|编写中|待验收|已通过|day01|day16|测试条数" docs/memory/learning-progress.md
```

预期：四种状态定义存在；章节表正好有 16 个章节项；没有用预测数字填充测试基线。

## Task 3: 固化 16 节路线并编写第 1 节

**Files:**
- Create: `docs/study/day01-项目定位与最小骨架.md`
- Modify: `docs/memory/learning-progress.md`

> 只创建当前待学章节。`day02` 至 `day16` 的标题先记录在进度表，等上一节验收通过后再创建对应施工图纸。

- [ ] **Step 1: 建立章节标题表**

按上述 16 个文件名更新进度表。每一行的状态仍为 `未开始`，不要提前把“编写中”写成“已通过”。

- [ ] **Step 2: 摸底 day01 原始材料**

只读以下资料：

```text
reference/掌教智库/4.视频/day01/课堂笔记/01【掌柜智库】项目简介.md
reference/掌教智库/4.视频/day01/课堂笔记/02【掌柜智库】环境准备.md
reference/掌教智库/4.视频/day01/课堂笔记/03【掌柜智库】【导入】骨架代码.md
reference/掌教智库/1.笔记/01【掌柜智库】项目简介.md
reference/掌教智库/1.笔记/02【掌柜智库】环境准备.md
```

以实际材料确定第 1 节的命令、目录和代码，不从其他项目套用命名。

- [ ] **Step 3: 编写第 1 节施工图纸**

`day01-项目定位与最小骨架.md` 必须包含：

- 项目业务目标、RAG 主链路和 API/Processor/数据层关系。
- Python 学习者需要的最小术语解释：虚拟环境、`pyproject.toml`、模块导入、状态字典、工作流节点。
- 一个不依赖真实模型和数据库的最小探针，让用户能看到状态从入口节点流向下一个节点。
- 按原项目顺序从函数式节点到节点基类/骨架的推导，每次只解决一个具体问题。
- 完整 Python 代码块；代码块正上方使用 `**文件**：`，路径相对仓库根目录。
- uv 运行命令、预期输出和失败判据；未实际跑过的命令标记为“未验证”。
- 至少一个针对节点路由或状态字段的破坏性实验步骤。
- “对照参考项目”和“下一节预告”，不写汇报记录。

- [ ] **Step 4: 只为 Mermaid 选择必要图示**

在第 1 节中使用 Mermaid 表达真实类名和节点名的关系；不新增与参考项目无关的视觉内容，图片目录在确有必要时再创建图片文件。

- [ ] **Step 5: 验证第 1 节文档结构**

运行：

```bash
rg -n "^#|本节你会学到|术语小灶|最小探针|验证汇总|对照参考项目|下一节预告|\*\*文件\*\*：" docs/study/day01-项目定位与最小骨架.md
```

预期：固定骨架各出现至少一次；每个可落盘代码块都紧邻一个 `**文件**：` 标记；代码块路径不指向 `reference/`。

## Task 4: 用 workspace 做首次真实验证

**Files:**
- Create: `workspace/verification/day01/`
- Create: `workspace/scripts/` 下的临时抽取或检查脚本
- Modify: `docs/study/day01-项目定位与最小骨架.md`（仅修正实跑发现的问题）
- Modify: `docs/memory/learning-progress.md`（记录真实状态）

- [ ] **Step 1: 建立隔离副本**

将用户当前学习工程或第 1 节最小工程复制到 `workspace/verification/day01/`，不得复制回 `reference/`，不得在仓库根目录生成运行产物。

- [ ] **Step 2: 抽取第 1 节代码并运行**

使用 `workspace/scripts/` 中的临时脚本读取 `**文件**：` 标记，写入隔离副本；在隔离副本中运行实际可用的 uv 命令。若当前章节尚未形成 `pyproject.toml`，只运行 Python 语法检查和探针命令，并把“测试未运行”写入进度。

- [ ] **Step 3: 做破坏性实验**

选择节点路由条件或状态字段默认值，先确认原文件内容，再修改一处使路由结果错误；运行对应探针，确认输出按预期变化或失败；恢复文件后用哈希或 `git diff --no-index` 确认恢复。

- [ ] **Step 4: 更新实测记录**

把命令、真实输出、测试条数、失败原因、跳过原因和未运行原因写入第 1 节文档与进度记忆。只有真实跑通的步骤才能标记为通过；第 1 节完成前保持 `待验收`。

- [ ] **Step 5: 准备用户会话入口**

在第 1 节末尾给出用户开始提示词，明确要手敲的文件、命令、预期输出和提交“写完了”后的验收入口；不直接修改学习代码。

## 验证总表

- `git check-ignore -v workspace/probe.txt` 能命中根 `.gitignore`。
- 课程完成时，`docs/study/` 中学习文档数量正好为 16，分别对应 `day01` 至 `day16`；每次只创建当前已获准章节。
- `reference/` 没有文件时间戳或内容变化。
- `docs/memory/learning-progress.md` 是唯一进度源，所有测试数字都有实际输出来源。
- 第 1 节代码块能够被标记检查工具定位，且没有把 `reference/` 路径当作学习代码写入目标。
- 破坏性实验能记录变更前、变更后、失败现象和恢复核对结果。

Git 提交和推送步骤不纳入执行范围；完成后只汇报文件清单、验证结果和建议的提交信息，由用户自行执行 Git 写操作。
