# 第 1 节：项目定位与导入骨架模块

> 本节只做三件事：看懂掌柜智库的真实业务链路，手敲导入流程的三个基础模块，按步骤验证这些模块的真实行为。PDF、模型、Milvus 等功能在对应节点出现后再验证，本节不提前写替身流程。

---

## 0. 本节你会学到

1. 说清楚文档为什么要经过“解析 → 切片 → 向量化 → 入库”，以及它怎样支撑后面的问答。
2. 手敲并读懂 `exceptions.py`、`state.py`、`BaseNode.py` 三个真实骨架模块。
3. 用命令验证状态工厂、异常对象和节点基类当前已经具备的真实行为。

**前置条件**：当前工程已经有 `pyproject.toml`、`src/shopkeeper_brain/` 和 LangGraph 依赖。本节不重复初始化 uv 项目，也不新增测试文件。

---

## 1. 业务流程：掌柜智库到底在处理什么

用户上传一份产品手册后，系统先把它变成“可以被检索的知识”，再处理用户问题。

```mermaid
flowchart LR
    A[用户上传 PDF / Markdown] --> B[node_entry 入口判断]
    B --> C[node_pdf_to_md PDF 转 Markdown]
    C --> D[node_md_img 图片处理]
    B --> D
    D --> E[node_document_split 文档切片]
    E --> F[node_item_name_recognition 主体识别]
    F --> G[node_bge_embedding 向量化]
    G --> H[node_import_milvus 写入 Milvus]
    H --> I[知识库可检索]

    I --> J[用户提问]
    J --> K[产品确认]
    K --> L[向量检索 / HyDE / Web 搜索]
    L --> M[RRF 融合]
    M --> N[Rerank 重排]
    N --> O[答案生成]
    O --> P[FastAPI + SSE 输出]
```

这条链路里，本节只落地最前面的流程基础设施：

| 模块 | 当前作用 | 后续谁会用它 |
| --- | --- | --- |
| `exceptions.py` | 给流程错误增加节点名和原始原因 | 所有导入节点 |
| `state.py` | 规定节点之间传递哪些字段 | LangGraph 导入主图 |
| `BaseNode.py` | 统一节点调用入口和异常包装 | 入口、PDF、切片等导入节点 |

节点共享一个状态；状态字段就是上下游之间的约定。后面每增加一个节点，先看它从状态读取什么、向状态写什么。

---

## 2. 术语只讲本节会遇到的

### `TypedDict`

它仍然是字典，只是把字段名和类型写出来，方便 IDE 提示和读代码。它不会像 Pydantic 那样在运行时自动校验数据。

```python
class ImportGraphState(TypedDict):
    import_file_path: str
```

### `deepcopy`

`GRAPH_DEFAULT_STATE` 里有列表。每次创建任务时要复制出一份独立列表，否则两个任务可能共用同一个 `visited_nodes`。

### 相对导入

```python
from .exceptions import ImportProcessError
```

`.` 表示当前包。这样 `BaseNode.py` 不依赖仓库根目录的绝对路径，包被 uv 安装后仍能找到同级模块。

### `__call__`

实现 `__call__` 后，节点对象可以这样调用：

```python
node(state)
```

这让节点对象可以直接交给工作流框架，同时把日志和异常处理集中在基类。

### `raise ... from`

```python
raise ImportProcessError(...) from exc
```

前面的异常是对外统一的业务异常，`from exc` 保留原始异常链，排查问题时还能看到最初原因。

---

## 3. 阶段①：先读取真实工程，再确认代码能运行

当前工程中已有以下真实文件：

```text
pyproject.toml
src/shopkeeper_brain/processor/import_processor/exceptions.py
src/shopkeeper_brain/processor/import_processor/state.py
src/shopkeeper_brain/processor/import_processor/BaseNode.py
```

先运行：

```bash
uv sync
uv run python -m compileall -q src/shopkeeper_brain
```

预期效果：两个命令都以退出码 0 结束，没有 Python 语法错误。

如果 `uv sync` 报错，先把完整错误原文发给我；不要自行修改项目配置，也不要把猜测的原因写进教程。

---

## 4. 阶段②：逐个看懂并手敲三个真实模块

### 4.1 `exceptions.py`：让错误带上节点上下文

参考项目后续会有配置错误、PDF 转换错误、向量化错误和存储错误。它们都继承一个导入流程基础异常。本节先保留最小版本。

**文件**：`src/shopkeeper_brain/processor/import_processor/exceptions.py`

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

手敲时注意：

- `Exception | None` 表示这个参数可以是异常对象，也可以是 `None`。
- `super().__init__(message)` 调用父类 `Exception` 的初始化逻辑。
- `__str__` 决定 `print(error)` 时显示什么内容。

### 4.2 `state.py`：规定节点之间传递的字段

当前阶段只保留骨架真正需要的字段。后面随着 PDF、切片和向量节点增加，再按真实业务增加字段。

**文件**：`src/shopkeeper_brain/processor/import_processor/state.py`

```python
from copy import deepcopy
from typing import TypedDict, Unpack


class ImportGraphState(TypedDict):
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


def create_default_state(**overrides: Unpack[ImportGraphState]) -> ImportGraphState:
    """创建彼此隔离的状态副本，并允许调用方覆盖字段。"""
    state = deepcopy(GRAPH_DEFAULT_STATE)
    state.update(overrides)
    return state
```

手敲时重点看：

- `class ImportGraphState(TypedDict)` 只描述字典结构，不会生成实例对象。
- `**overrides` 接收调用方传入的关键字参数。
- `Unpack[ImportGraphState]` 告诉类型检查器：这些关键字应该来自状态字段。
- `deepcopy` 保证每个任务的 `visited_nodes` 独立。

### 4.3 `BaseNode.py`：统一每个节点的执行入口

参考项目的每个节点都需要开始日志、执行 `process`、完成日志和异常包装。把固定步骤放进基类，具体业务留给子类。

**文件**：`src/shopkeeper_brain/processor/import_processor/BaseNode.py`

```python
from abc import ABC, abstractmethod
import logging
from typing import TypeVar

from .exceptions import ImportProcessError
from .state import ImportGraphState

StateT = TypeVar('StateT', bound=ImportGraphState)


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
            )from exc
        self.logger.info("%s 完成", self.name)
        return result

    @abstractmethod
    def process(self, state: StateT) -> StateT:
        """子类实现具体业务。"""
        raise NotImplementedError
```

手敲时重点看：

- `ABC` 和 `@abstractmethod` 规定子类必须实现 `process`。
- `name` 是类属性，子类覆盖它后，基类日志自动带上节点名。
- `node(state)` 实际会进入 `__call__`，再由 `__call__` 调用 `process`。
- `except Exception` 会捕获普通异常并包装成 `ImportProcessError`；已经是业务异常时直接继续抛出。

本节不为 `BaseNode` 虚构业务子类。等入口节点真正出现后，再用真实节点验证这条调用链。

---

## 5. 阶段③：真实验证步骤

本节不新增测试文件。你按下面步骤操作，把真实终端输出发给我；每一步都给出预期效果。

### 5.1 语法和模块导入

运行：

```bash
uv run python -m compileall -q src/shopkeeper_brain
uv run python -c "from shopkeeper_brain.processor.import_processor.BaseNode import BaseNode; from shopkeeper_brain.processor.import_processor.exceptions import ImportProcessError; from shopkeeper_brain.processor.import_processor.state import create_default_state; print(BaseNode.__name__, ImportProcessError.__name__, create_default_state()['status'])"
```

预期效果：

- 两条命令退出码都是 0。
- 第二条命令输出包含：

```text
BaseNode ImportProcessError created
```

### 5.2 状态工厂的独立性

运行：

```bash
uv run python -c "from shopkeeper_brain.processor.import_processor.state import create_default_state; first=create_default_state(); second=create_default_state(); first['visited_nodes'].append('first'); assert second['visited_nodes']==[], second['visited_nodes']; print('状态隔离验证通过')"
```

预期效果：输出：

```text
状态隔离验证通过
```

这一步验证的是 `deepcopy` 的真实行为：第一个任务追加节点后，第二个任务仍然拥有空列表。

### 5.3 异常对象的信息

运行：

```bash
uv run python -c "from shopkeeper_brain.processor.import_processor.exceptions import ImportProcessError; error=ImportProcessError('读取失败', node_name='node_entry', cause=ValueError('文件不存在')); assert str(error)=='[node_entry] 读取失败 (原因: 文件不存在)'; print(error)"
```

预期效果：输出：

```text
[node_entry] 读取失败 (原因: 文件不存在)
```

这一步只验证异常对象当前已经实现的格式，不模拟任何文件读取。

### 5.4 破坏性验证：确认状态隔离真的被保护

1. 打开 `src/shopkeeper_brain/processor/import_processor/state.py`。
2. 把：

```python
state = deepcopy(GRAPH_DEFAULT_STATE)
```

临时改成：

```python
state = GRAPH_DEFAULT_STATE
```

3. 重新运行 5.2 的状态隔离命令。

预期效果：命令失败，并出现类似下面的断言信息：

```text
AssertionError: ['first']
```

这说明两个状态错误地共享了同一个列表。

4. 恢复为 `deepcopy`。
5. 再次运行 5.2，预期重新输出 `状态隔离验证通过`。

本节不验证 `BaseNode.__call__` 的完整执行过程，因为当前工程还没有真实入口节点；下一节出现入口节点后再验证，不提前写临时业务类。

---

## 6. 小结

如果只记三件事：

1. 掌柜智库先把文档加工成可检索知识，再进入检索和答案生成。
2. `state.py` 是节点之间的数据契约，`BaseNode.py` 是节点统一执行入口，`exceptions.py` 负责保留失败上下文。
3. 验证要直接打到真实模块：本节验证状态工厂和异常对象；真实节点出现后再验证节点执行。

### 对照参考项目

| 维度 | 参考项目 | 当前学习工程 |
| --- | --- | --- |
| 状态 | `ImportGraphState` + 默认状态工厂 | 保持同样的字段契约和深拷贝方式 |
| 异常 | `ImportProcessError` 携带节点名和原因 | 保持同样的错误信息结构 |
| 节点基类 | `BaseNode.__call__` 调用 `process` | 保持同样的调用关系 |
| 真实业务节点 | 入口、PDF、图片、切片、向量化、入库 | 下一节开始逐个手敲 |
| 本节验证 | 验证基础模块已有行为 | 不新增测试文件，不提前验证外部服务 |

### 下一节预告

**第 2 节：入口节点与文件类型路由。** 下一节会手敲参考项目里的真实入口节点，使用真实文件路径验证 PDF、Markdown 和不支持格式的分支状态；不提前写 PDF 转换流程。
