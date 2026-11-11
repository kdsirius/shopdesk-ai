# 第 1 节：项目定位与最小骨架

> 这一节先把原项目的全景和导入流程骨架看懂，再用一个不依赖真实模型、数据库和 PDF 工具的最小流程验证“状态 → 节点 → 主图”。下一节再进入 uv 环境、配置加载和入口节点的完整工程化写法。

---

## 0. 本节你会学到

1. 说清楚掌柜智库解决什么业务问题，以及 RAG 问答为什么先要做文档导入。
2. 用 Python 字典表达一条最小的导入状态，并看见状态如何经过多个节点。
3. 理解参考项目中的 `TypedDict`、节点基类、`__call__` 和 LangGraph 主图分别解决什么问题。
4. 用 uv 创建 Python 3.11 项目、安装 LangGraph，并运行一个不依赖外部服务的流程。
5. 用文件类型路由实验验证 PDF、Markdown 和不支持格式走不同路径。

**前置条件**：当前仓库还没有学习代码；本机摸底到的环境是 uv 0.12.13、Python 3.12.9。参考项目要求 Python 3.11，本节会用 uv 为学习工程声明 Python 3.11；这条初始化命令已在 `workspace/` 实测，详细安装命令见第 2 节。

---

## 1. 术语小灶

### 1.1 RAG

RAG 是“先检索资料，再让模型根据资料回答”。它不是把所有资料直接塞给模型，而是先把文档加工成可搜索的知识。

生活类比：你去图书馆问问题，管理员先找到相关书页，再把书页交给回答者。掌柜智库中的“文档导入”就是管理员整理书架的过程，“检索和答案输出”才是回答问题的过程。

### 1.2 状态（State）

状态就是流程中一路传递的工作单。它可以记录任务 ID、原文件路径、文件类型判断、转换后的 Markdown、切片和向量等中间结果。

```python
state = {
    "import_file_path": "manual.pdf",
    "is_pdf_read_enabled": True,
}
```

和 Java 中的方法参数对象类似，但参考项目使用的是字典形态，因为 LangGraph 的节点以状态字典作为输入输出。

### 1.3 节点（Node）

节点是流程中的一个业务步骤，例如“入口节点”“PDF 转 Markdown 节点”“文档切片节点”。一个节点读取状态，完成自己的工作，再返回更新后的状态。

### 1.4 主图（Graph）

主图负责安排节点顺序和分支。节点只关心自己的业务，主图负责回答“下一个执行谁”。这就是参考项目把节点和 `main_graph.py` 分开的原因。

### 1.5 `TypedDict`

`TypedDict` 仍然是字典，但给字典声明了字段和类型。它不会在运行时把字典变成 Java Bean，也不会自动做完整的数据校验；它首先解决的是 IDE 补全、静态检查和状态契约可读性。

### 1.6 `__call__`

Python 允许对象实现 `__call__` 后像函数一样被调用：`node(state)`。参考项目利用这一点，让 LangGraph 看到的是一个可调用节点，同时把日志、异常包装等通用动作放进节点基类。

---

## 2. 环境准备：先让 uv 建出空项目

参考资料使用 `uv.toml` 配置镜像，但当前 uv 官方文档推荐在 `pyproject.toml` 的 `[tool.uv]` 中声明索引。为了避免把过时配置直接复制进学习项目，本节使用当前语法。

在仓库根目录执行。当前仓库还没有 `pyproject.toml`，所以这条命令只需要执行一次：

```bash
uv init --python 3.11 --name shopkeeper-brain
```

**预期效果**：根目录出现 `pyproject.toml`，其中包含 `requires-python = ">=3.11"`；同时 uv 会创建项目需要的基础配置。该命令在 `workspace/verification/day01/project` 实测通过。

在生成的 `pyproject.toml` 中追加当前 uv 的镜像配置。只追加下面这段，不要删除 `uv init` 生成的内容：

```toml
[[tool.uv.index]]
url = "https://pypi.tuna.tsinghua.edu.cn/simple"
default = true
```

**验证状态**：配置语法依据 uv 官方当前文档；本节已实际用 `UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple uv add langgraph` 验证安装流程，直接把配置写入 `pyproject.toml` 的行为尚未在本仓库执行，标记为“未验证”。

安装 LangGraph：

```bash
uv add langgraph
```

如果当前终端还没有使用项目配置，可以在 Git Bash 中临时指定镜像：

```bash
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple uv add langgraph
```

PowerShell 等价写法：

```powershell
$env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
uv add langgraph
Remove-Item Env:UV_DEFAULT_INDEX
```

**预期效果**：`pyproject.toml` 的 `dependencies` 出现 `langgraph`，同时生成或更新 `uv.lock` 和 `.venv`。如果你使用的是 PowerShell，记录真实命令输出；不要把“安装成功”当成猜测。

---

## 3. 阶段① 最小探针：先看看直写流程会怎么跑

当前项目还没有学习代码，因此这里不是读取现状，而是在新工程中故意写一个最小、直白的版本。先不要急着创建基类、状态类型和 LangGraph；先让一条业务流程跑起来。

### 3.1 直写版本

**文件**：`src/shopkeeper_brain/processor/import_process/probe.py`

```python
from pathlib import Path


def entry(state: dict) -> dict:
    """入口步骤：根据扩展名决定后续路径。"""
    file_path = Path(state["import_file_path"])
    state["visited_nodes"].append("entry")

    if file_path.suffix.lower() == ".pdf":
        state["is_pdf_read_enabled"] = True
    elif file_path.suffix.lower() == ".md":
        state["is_md_read_enabled"] = True
    else:
        state["status"] = "unsupported"

    return state


def pdf_to_markdown(state: dict) -> dict:
    """模拟 PDF 转 Markdown，不接入真实 MinerU。"""
    state["visited_nodes"].append("pdf_to_markdown")
    state["status"] = "markdown_ready"
    return state


def run_import(import_file_path: str) -> dict:
    """用最直白的方式串起当前能处理的步骤。"""
    state = {
        "import_file_path": import_file_path,
        "is_pdf_read_enabled": False,
        "is_md_read_enabled": False,
        "visited_nodes": [],
        "status": "created",
    }

    state = entry(state)
    if state["is_pdf_read_enabled"]:
        state = pdf_to_markdown(state)

    return state


if __name__ == "__main__":
    for file_path in ("manual.pdf", "manual.md", "manual.txt"):
        print(file_path, "->", run_import(file_path))
```

运行：

```bash
uv run python -m shopkeeper_brain.processor.import_process.probe
```

**预期效果**：

- `manual.pdf` 的 `visited_nodes` 包含 `entry` 和 `pdf_to_markdown`，状态为 `markdown_ready`。
- `manual.md` 只经过 `entry`，状态仍是 `created`。
- `manual.txt` 只经过 `entry`，状态为 `unsupported`。

这段代码能工作，但问题已经出现：状态字段散落在函数里，节点没有统一接口，异常没有统一上下文，流程分支也混在执行代码中。接下来只解决这些具体问题。

---

## 4. 阶段② 盯着探针，列出要补的账

| 缺口 | 后果 | 优先级 |
| --- | --- | --- |
| 状态只是普通 `dict`，字段没有集中声明 | 节点写错字段名时，编辑器和读代码的人都很难发现 | 高 |
| 每个步骤都是普通函数 | 日志、异常、任务追踪将来会在每个函数里重复 | 高 |
| PDF、Markdown 和不支持格式的分支写在 `run_import` 中 | 主流程会随着节点增加而变得越来越长 | 高 |
| `pdf_to_markdown` 只是模拟动作 | 本节只验证骨架；真实 MinerU 放到后续 PDF 节点章节 | 中 |
| 没有外部服务隔离 | 一开始就接 Milvus 或模型会把流程问题和环境问题混在一起 | 高 |

参考项目的 `config.py`、`exceptions.py`、`state.py`、`base.py` 和 `main_graph.py` 正是对这些账的逐步收敛。本节先完成其中最小骨架，真实 PDF、图片、切片和向量化留到后续章节。

---

## 5. 阶段③ 逐个改造

### 5.1 第一个改动：把状态变成明确的数据契约

为什么改：节点之间传递的是同一个状态。如果每个节点自己猜字段名，后面加节点时很容易出现“前一个节点写 `file_path`，后一个节点读 `import_file_path`”的问题。

**文件**：`src/shopkeeper_brain/processor/import_process/state.py`

```python
from copy import deepcopy
from typing import TypedDict


class ImportGraphState(TypedDict, total=False):
    """导入流程中所有节点共享的状态。"""

    import_file_path: str
    is_pdf_read_enabled: bool
    is_md_read_enabled: bool
    visited_nodes: list[str]
    status: str


GRAPH_DEFAULT_STATE: ImportGraphState = {
    "import_file_path": "",
    "is_pdf_read_enabled": False,
    "is_md_read_enabled": False,
    "visited_nodes": [],
    "status": "created",
}


def create_default_state(**overrides: object) -> ImportGraphState:
    """创建彼此隔离的状态副本，并允许调用方覆盖字段。"""
    state = deepcopy(GRAPH_DEFAULT_STATE)
    state.update(overrides)
    return state
```

这里的 `deepcopy` 不是装饰。`visited_nodes` 是可变列表，如果直接复用全局模板，多个任务可能共享同一份列表；每次复制出独立状态才能避免任务之间互相污染。

### 5.2 第二个改动：建立统一异常类型

为什么改：流程节点失败时，调用方至少需要知道“哪个节点失败”。先定义一个最小异常类型，后续再按配置、文件、向量和存储继续细分。

**文件**：`src/shopkeeper_brain/processor/import_process/exceptions.py`

```python
class ImportProcessError(Exception):
    """导入流程的基础异常。"""

    def __init__(
        self,
        message: str,
        node_name: str = "",
        cause: Exception | None = None,
    ) -> None:
        self.node_name = node_name
        self.cause = cause
        super().__init__(message)

    def __str__(self) -> str:
        prefix = f"[{self.node_name}] " if self.node_name else ""
        cause = f" (原因: {self.cause})" if self.cause else ""
        return f"{prefix}{super().__str__()}{cause}"
```

### 5.3 第三个改动：用节点基类收敛通用执行逻辑

为什么改：参考项目的节点都需要“开始日志 → 执行业务 → 完成日志 → 统一包装异常”。把这段固定流程放进基类，子类只实现 `process`。

**文件**：`src/shopkeeper_brain/processor/import_process/base.py`

```python
from abc import ABC, abstractmethod
import logging
from typing import TypeVar

from .exceptions import ImportProcessError
from .state import ImportGraphState


StateT = TypeVar("StateT", bound=ImportGraphState)


class BaseNode(ABC):
    """所有导入节点共享的执行外壳。"""

    name = "base_node"

    def __init__(self) -> None:
        if self.name == "base_node":
            raise ValueError("子类必须覆盖 name")
        self.logger = logging.getLogger(f"import.{self.name}")

    def __call__(self, state: StateT) -> StateT:
        """让节点实例可以被 LangGraph 当作函数调用。"""
        self.logger.info("%s 开始", self.name)
        try:
            result = self.process(state)
        except ImportProcessError:
            raise
        except Exception as exc:
            raise ImportProcessError(
                message=str(exc),
                node_name=self.name,
                cause=exc,
            ) from exc
        self.logger.info("%s 完成", self.name)
        return result

    @abstractmethod
    def process(self, state: StateT) -> StateT:
        """子类实现具体业务。"""
        raise NotImplementedError
```

这里对应参考项目里的模板方法思路：`__call__` 是固定骨架，`process` 是留给子类的变化点。代价是类的数量增加、初学者需要理解继承；换来的收益是每个节点的执行边界统一了。

### 5.4 第四个改动：把分支交给 LangGraph 主图

为什么改：直写版本把“调用谁”写在 `run_import` 里。LangGraph 的 `StateGraph` 让节点注册、顺序边和条件边集中在主图中，节点类只负责处理状态。

**文件**：`src/shopkeeper_brain/processor/import_process/main_graph.py`

```python
from typing import Literal

from langgraph.graph import END, START, StateGraph

from .base import BaseNode
from .state import ImportGraphState, create_default_state


class NodeEntry(BaseNode):
    """入口节点：判断输入文件类型。"""

    name = "node_entry"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        file_path = state["import_file_path"].lower()
        state["visited_nodes"].append(self.name)

        if file_path.endswith(".pdf"):
            state["is_pdf_read_enabled"] = True
        elif file_path.endswith(".md"):
            state["is_md_read_enabled"] = True
        else:
            state["status"] = "unsupported"

        return state


class NodePdfToMd(BaseNode):
    """模拟 PDF 转 Markdown，真实 MinerU 在后续章节接入。"""

    name = "node_pdf_to_md"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        state["visited_nodes"].append(self.name)
        state["status"] = "markdown_ready"
        return state


def route_after_entry(
    state: ImportGraphState,
) -> Literal["node_pdf_to_md", "__end__"]:
    """根据入口节点写入的标记选择下一步。"""
    if state.get("is_pdf_read_enabled"):
        return "node_pdf_to_md"
    return END


workflow = StateGraph(ImportGraphState)
workflow.add_node("node_entry", NodeEntry())
workflow.add_node("node_pdf_to_md", NodePdfToMd())
workflow.add_edge(START, "node_entry")
workflow.add_conditional_edges(
    "node_entry",
    route_after_entry,
    {
        "node_pdf_to_md": "node_pdf_to_md",
        END: END,
    },
)
workflow.add_edge("node_pdf_to_md", END)

kb_import_app = workflow.compile()


def run_import(import_file_path: str) -> ImportGraphState:
    """给外部调用方的最小执行入口。"""
    initial_state = create_default_state(import_file_path=import_file_path)
    return kb_import_app.invoke(initial_state)


if __name__ == "__main__":
    for file_path in ("manual.pdf", "manual.md", "manual.txt"):
        print(file_path, "->", run_import(file_path))
```

LangGraph 当前官方用法也是“先用 `StateGraph` 注册状态、节点和边，再 `compile()`，最后 `invoke()` 或 `stream()`”。这里的条件边只把 PDF 导向模拟转换节点，Markdown 和其他格式先结束；下一节再加入更完整的入口路由和后续节点。

---

## 6. 验证汇总

### 6.1 环境与依赖

```bash
uv --version
python --version
uv run python -c "from importlib.metadata import version; print(version('langgraph'))"
```

本次摸底实测：

- `uv --version`：`uv 0.12.13`
- `python --version`：`Python 3.12.9`
- `uv init --python 3.11 --name shopkeeper-brain ...`：已在 `workspace/verification/day01/project` 实测通过。
- `UV_DEFAULT_INDEX=... uv add langgraph`：已在 workspace 实测通过，安装 `langgraph 1.2.20`。
- 在当前仓库根目录执行 `uv init`、`uv add` 和 `uv run`：未执行，等你开始手敲本节时执行。

### 6.2 行为验证

在仓库根目录完成手敲后运行：

```bash
uv run python -m shopkeeper_brain.processor.import_process.probe
uv run python -m shopkeeper_brain.processor.import_process.main_graph
```

预期行为：

| 输入 | 经过节点 | 最终状态 |
| --- | --- | --- |
| `manual.pdf` | `node_entry → node_pdf_to_md` | `markdown_ready` |
| `manual.md` | `node_entry` | `created` |
| `manual.txt` | `node_entry` | `unsupported` |

`workspace/verification/day01/project` 实测输出：

```text
manual.pdf -> {'import_file_path': 'manual.pdf', 'is_pdf_read_enabled': True, 'is_md_read_enabled': False, 'visited_nodes': ['node_entry', 'node_pdf_to_md'], 'status': 'markdown_ready'}
manual.md -> {'import_file_path': 'manual.md', 'is_pdf_read_enabled': False, 'is_md_read_enabled': True, 'visited_nodes': ['node_entry'], 'status': 'created'}
manual.txt -> {'import_file_path': 'manual.txt', 'is_pdf_read_enabled': False, 'is_md_read_enabled': False, 'visited_nodes': ['node_entry'], 'status': 'unsupported'}
```

请在你手敲后把自己的真实输出贴到会话中；验收时我会从你的实际文件和实际输出判断结果，以上输出只代表本次 workspace 验证。

### 6.3 破坏性实验

改坏了什么：在 `main_graph.py` 的 `route_after_entry` 中，把：

```python
if state.get("is_pdf_read_enabled"):
    return "node_pdf_to_md"
```

临时改成：

```python
if True:
    return "node_pdf_to_md"
```

先运行：

```bash
uv run python -m shopkeeper_brain.processor.import_process.main_graph
```

预期：`manual.md` 和 `manual.txt` 也会错误地经过 `node_pdf_to_md`，说明路由条件被破坏。

workspace 实测的破坏结果：

```text
manual.md -> {'import_file_path': 'manual.md', 'is_pdf_read_enabled': False, 'is_md_read_enabled': True, 'visited_nodes': ['node_entry', 'node_pdf_to_md'], 'status': 'markdown_ready'}
manual.txt -> {'import_file_path': 'manual.txt', 'is_pdf_read_enabled': False, 'is_md_read_enabled': False, 'visited_nodes': ['node_entry', 'node_pdf_to_md'], 'status': 'markdown_ready'}
```

恢复原代码后再次运行，Markdown 和 TXT 不再进入 PDF 节点；恢复后的 `main_graph.py` SHA-256 为 `6f518b03d692ed6cf1c191f3b0b319168275cbefa33faba5fc247b3be25ea213`。

### 6.4 本节踩的坑

1. 现象：参考环境准备笔记使用 `uv.toml` 的 `index-url` 写法。
   原因：参考资料与当前 uv 版本的推荐配置方式存在时间差。
   处理：本节采用当前 uv 文档的 `[[tool.uv.index]]` 写法；参考资料原文作为差异记录保留，不修改 reference。

2. 现象：本机默认 Python 是 3.12.9，而参考项目要求 Python 3.11。
   原因：系统解释器版本和项目声明版本不是一回事。
   处理：用 `uv init --python 3.11` 为项目声明 Python 3.11；是否已经安装并实际使用 3.11，以你运行 `uv run` 的输出为准。

3. 现象：`import langgraph; print(langgraph.__version__)` 报 `AttributeError: module 'langgraph' has no attribute '__version__'`。
   原因：当前 LangGraph 包没有暴露 `__version__` 模块属性。
   处理：使用 `from importlib.metadata import version; print(version('langgraph'))` 查询已安装分发版本；workspace 实测输出为 `1.2.20`。

---

## 7. 小结

如果只记三件事：

1. RAG 项目先处理文档，再做检索和答案生成；导入流程是后续问答质量的基础。
2. 状态是节点之间的数据契约；节点负责业务，主图负责顺序和分支。
3. `BaseNode.__call__` 用固定执行外壳包住 `process`，这是从重复函数走向工程化节点的关键一步。

### 对照参考项目

| 维度 | 参考项目 | 本节重建 | 为什么 |
| --- | --- | --- | --- |
| 顶层包名 | `knowledge` | `shopkeeper_brain` | 使用已确认的新项目命名，其余目录职责保持一致 |
| 状态定义 | `ImportGraphState` + 默认状态工厂 | 同样采用 | 保留原项目的状态契约思路 |
| 节点接口 | `BaseNode.__call__` + `process` | 同样采用 | 保留模板方法和可调用对象设计 |
| 真实 PDF 处理 | MinerU | 暂用模拟节点 | 本节只验证流程骨架，真实工具放到 PDF 章节 |
| 运行方式 | LangGraph `compile` 后执行 | 同样采用 | 对齐当前 LangGraph 官方 API |
| 镜像配置 | 参考笔记使用 `uv.toml` | 使用当前 `pyproject.toml` 的 uv 配置 | 参考写法与当前 uv 推荐方式有时间差 |

### 下一节预告

**第 2 节：uv 环境与项目配置。** 这一节留下的问题是：状态和节点已经能跑，但配置、异常层级、日志和入口节点还没有按项目方式组织；下一节会把这些基础设施补齐，再验证文件类型路由。

---

## 给下一次会话的开始提示词

```text
继续 shopkeeper-brain 带练重建。先读取 AGENTS.md、docs/AGENTS.md、reference/AGENTS.md 和 docs/memory/learning-progress.md。当前进行第 1 节《项目定位与最小骨架》的手敲与验收：请读取我真实写出的文件，在 workspace/verification/ 下复制并实跑 uv 命令、两个流程探针和一次破坏性路由实验。不要修改 reference/，不要直接替我写学习代码。验收按“必须改 / 建议改 / 可选”反馈；通过后再更新进度和记忆，不要提前开始第 2 节。
```
