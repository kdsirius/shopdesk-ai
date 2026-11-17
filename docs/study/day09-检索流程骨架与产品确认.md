# 第 9 节：检索流程骨架与产品确认

> 上一节已经把主体名称和 21 个 Chunk 写入 Milvus 的 `kb_item_names` 与 `kb_chunks`；这一节搭起查询流程的骨架，并实现第一个真实节点：从用户的问题里确认他问的是哪一个产品，同时把对话历史保存到你虚拟机上的 MongoDB。
> 对应资料：`reference/掌教智库/4.视频/day09/` 的检索骨架与产品确认课堂笔记；补充阅读 `reference/掌教智库/1.笔记/14【掌柜智库】【检索】【节点1】产品确认.md`，本节做到商品名提取、名称集合检索、评分对齐和历史记录。

## 一、业务流程与设计原因

### 1. 入库之后，用户的问题还缺一个产品

第 8 节已经把真实数据放进 Milvus：`kb_item_names` 里有 1 条主体记录 `RS PRO RS-12 数字万用表`，`kb_chunks` 里有这份手册的 21 个 Chunk。现在用户开始提问，先看三句可能出现的话：

| 用户的问题 | 系统此刻知道什么 | 直接拿问题去搜 `kb_chunks` 会怎样 |
| --- | --- | --- |
| RS-12 怎么测电压？ | 有型号，但比库里的完整名称短 | 库里有多个型号时，会混进别的型号的说明 |
| 它怎么测电压？ | 没有产品名，“它”要到上一轮对话里找 | 问题里没有任何可以检索的产品线索 |
| iPhone 15 怎么充电？ | 有产品名，但库里根本没有这个产品 | 仍会返回“最像”的几段，答案张冠李戴 |

Chunk 只记录“这一段说了什么”，不负责判断用户问的是谁。所以检索流程的第一个节点先不找答案，只回答一个问题：**用户问的是哪个产品**。它读到用户的一句话，要产出三种结果之一：

| 结果 | 条件 | 流程怎么走 |
| --- | --- | --- |
| 确认 | 库里有一个名称和用户说的几乎一致 | 把标准名称写进状态，继续检索正文 |
| 追问 | 有相似的名称，但不够确定 | 生成“您是想问……”，直接返回给用户 |
| 拒答 | 没有任何相似的名称 | 生成“未找到相关产品”，直接返回给用户 |

这个节点只查 `kb_item_names`，不查 `kb_chunks`：名称集合每个产品只有一条记录，查询快；正文检索要等产品确认之后，才能带着产品范围去做。

### 2. 查询流程有自己的状态和并行分支

查询流程和导入流程面对的问题不同：

| | 导入流程 | 查询流程 |
| --- | --- | --- |
| 一次执行的输入 | 一份文件路径 | 一句问题和一个会话编号 |
| 状态类 | `ImportGraphState` | `QueryGraphState`（本节新建） |
| 节点走向 | 按顺序依次处理 | 确认产品后三路检索并行，再汇合 |
| 最终产物 | Milvus 里的记录 | 一段回答 |

两条流程的状态字段、节点基类和主图都不一样，因此放进新的 `processor/query_processor/` 目录，不改 `import_processor`。

```mermaid
flowchart LR
    A["QueryGraphState：session_id + original_query"] --> B["NodeItemNameConfirm（本节真实实现）"]
    B -->|"answer 有值：追问或拒答"| H["NodeAnswerOutput（占位）"]
    B -->|"answer 为空：已确认商品"| C["NodeSearchEmbedding（占位）"]
    B -->|"answer 为空：已确认商品"| D["NodeSearchEmbeddingHyde（占位）"]
    B -->|"answer 为空：已确认商品"| E["NodeWebSearchMcp（占位）"]
    C --> F["NodeRrf（占位）"]
    D --> F
    E --> F
    F --> G["NodeRerank（占位）"]
    G --> H
```

从左往右读：`NodeItemNameConfirm` 是入口，也是本节唯一的真实节点。`KBQueryWorkflow._route_after_item_name_confirm` 只看 `state["answer"]`：有值说明已经决定追问或拒答，直接去 `NodeAnswerOutput`；没有值说明产品已确认，同时进入三路检索节点，三路都完成后汇合到 `NodeRrf`，再经过 `NodeRerank` 到达 `NodeAnswerOutput`。除入口以外的六个节点本节只写占位：被调用时输出日志、返回空结果，目的是先把整张图跑通，后面逐个换成真实实现。

三路检索并行执行，所以每个节点只返回自己负责的那个字段（例如 `embedding_chunks`），不返回整份状态；如果三个节点在同一步里写同一批键，LangGraph 会报错。

### 3. 产品确认节点分八步

```mermaid
flowchart TD
    A["process(state)"] --> B["_step_1_validate_param"]
    B --> C["步骤 2：get_recent_messages 读取历史"]
    C --> D["步骤 3：save_chat_message 保存当前问题"]
    D --> E["_step_4_extract_info：item_names + rewritten_query"]
    E --> F{"提取到商品名？"}
    F -->|是| G["_step_5_vectorize_and_query"]
    G --> H["_step_6_align_item_names"]
    F -->|否| I["_step_7_check_confirmation"]
    H --> I
    I -->|"有确认商品"| J["分支 A：写 item_names，回填历史"]
    I -->|"只有候选"| K["分支 B：answer 写追问"]
    I -->|"都没有"| L["分支 C：answer 写拒答"]
    J --> M["_step_8_write_history"]
    K --> M
    L --> M
```

从上往下读：`process()` 依次调用各步，数据沿着 `state` 和几个局部变量传递。步骤 2、3 只有一行调用，直接写在 `process()` 里；其余六步各是一个方法。模型没有提取到商品名时，跳过 5、6 两步，第 7 步拿到空的对齐结果，自然进入分支 C。

| 步骤 | 负责的问题 | 交给下一步的数据 |
| --- | --- | --- |
| 1 `_step_1_validate_param` | 输入契约是否成立 | `session_id`、`original_query` |
| 2 读取历史 | 之前聊过什么 | `history`（从旧到新） |
| 3 保存当前问题 | 先把用户这句话留下来 | `message_id` |
| 4 `_step_4_extract_info` | 问的是什么商品，问题怎么改写 | `item_names`、`rewritten_query` |
| 5 `_step_5_vectorize_and_query` | 每个名称在名称集合里像谁 | 每个名称的候选和评分 |
| 6 `_step_6_align_item_names` | 评分够不够确认 | 确认列表、候选列表 |
| 7 `_step_7_check_confirmation` | 走哪个分支 | `item_names`，必要时 `answer` |
| 8 `_step_8_write_history` | 结果怎样留进历史 | 无，只写 MongoDB |

有两处顺序不能换。步骤 2 必须在步骤 3 之前：先读历史再保存当前问题，历史里才不会混进用户刚说的这一句，模型也就不会看到它出现两次。步骤 3 要在调用模型之前：这样即使后面的模型或检索失败，用户说过的话也已经留在历史里。

### 4. 评分怎样决定三个分支

名称检索给每个候选一个 0 到 1 之间的评分，节点按它分三档：

| 评分 | 含义 | 处理 |
| --- | --- | --- |
| 大于 0.85 | 几乎就是库里的这个名称 | 确认；有多个时优先取与提取名完全相同的，否则取最高分 |
| 0.6 到 0.85 | 可能相关，也可能误匹配 | 作为候选，交给用户选 |
| 小于 0.6 | 无关 | 丢弃 |

节点汇总所有提取名称的结果：有确认商品是分支 A；没有确认商品但有候选是分支 B；两者都没有是分支 C。

这个评分不是余弦相似度本身。混合检索把 Dense 的余弦相似度换算到 0 到 1，再和 Sparse 得分按 0.8 比 0.2 加权，所以无关的词也不会接近 0。用第 8 节入库的真实数据做过一次只读查询，几个名称的参考量级如下：

| 提取到的名称 | 参考评分 | 落入的分支 |
| --- | --- | --- |
| `RS PRO RS-12 数字万用表` | 约 0.92 | A |
| `RS-12`、`万用表` | 约 0.76、0.77 | B |
| `手机` | 约 0.67 | B |
| `iPhone 15` | 约 0.53 | C |

读这张表要记住两点。第一，0.85 和 0.6 是参考项目的经验值，库里只有一个产品时，大多数像产品名的词都会落进分支 B，真正触发分支 C 需要明显无关的名称。第二，用户只说短型号时，系统先追问，再靠追问里出现的完整名称完成确认，这正是历史对话要保存的原因。后面验证时以你日志里的实际评分为准，不要求和上表一致。

### 5. 对话历史为什么放 MongoDB

一次 `invoke()` 结束，状态就没有了；而“追问、确认”要跨好几次提问。看一段对话：

| 轮次 | 谁说 | 内容 | 这一句要靠什么才能读懂 |
| --- | --- | --- | --- |
| 1 | 用户 | RS-12 怎么测电压？ | 不需要上下文 |
| 1 | 助手 | 您是想问以下哪个产品：RS PRO RS-12 数字万用表？请明确一下型号。 | 不需要上下文 |
| 2 | 用户 | 对，就是这个，怎么测电压？ | “这个”指上一句助手给出的完整名称 |

第 2 轮的“这个”只有读到第 1 轮才有意义，所以每条消息都要保存在图的外面，下一次提问时读出来交给模型。

项目没有使用 LangGraph 自带的检查点保存历史，而是自己用 MongoDB 存。每条消息是一份 JSON 文档，查询条件只有“某个会话 + 按时间排序”，没有多表关联，也不需要向量检索，适合文档数据库。一条消息的字段如下：

| 字段 | 含义 |
| --- | --- |
| `session_id` | 会话编号，同一场对话共用 |
| `role` | `user` 或 `assistant` |
| `text` | 这句话的原文 |
| `rewritten_query` | 用户消息改写后的独立问题，助手消息为空字符串 |
| `item_names` | 这句话关联的商品名，可以有多个 |
| `ts` | 第一次写入的时间戳，单位秒 |

MongoDB 里数据库（Database）装集合（Collection），集合里是文档（Document）。本节用数据库 `kb001` 的集合 `chat_message`，它们在第一次写入时自动创建；再建一个按 `session_id` 升序、`ts` 倒序的复合索引，对应“取这个会话最新几条”的查询。

MongoDB 部署在你的虚拟机 `192.168.150.120` 上：docker-compose 里的 `mongo` 服务，容器 `my-mongo`，镜像 `mongo:7.0`，宿主机端口 27017。这个服务启用了账号密码：首次初始化数据目录时，`MONGO_INITDB_ROOT_USERNAME` 创建了 root 用户 `admin`，它存放在 `admin` 库里。因此连接地址必须带用户名、密码和 `authSource=admin`。密码只写在本地 `.env`，不进入教程，也不进入 `.env.example`。

### 6. 为什么要改写问题

第 2 轮的“对，就是这个，怎么测电压？”单独拿去检索没有意义。模型在提取商品名的同时，把它改写成包含商品名的独立问题 `rewritten_query`，后面的检索节点才能直接使用：

| 原始问题 | 改写后 | 解决什么 |
| --- | --- | --- |
| 对，就是这个，怎么测电压？ | RS PRO RS-12 数字万用表怎么测电压？ | 消除指代 |
| 它的电阻挡在哪？ | RS PRO RS-12 数字万用表的电阻挡在哪？ | 补全主语 |
| 咋弄？ | RS PRO RS-12 数字万用表如何操作？ | 规范口语 |

一个已知取舍：`rewritten_query` 是模型提取名称时顺手生成的，用的是用户或历史里出现过的名称；第 6 步把名称对齐成库里的标准名称之后，不再回头重写它。再调用一次模型会增加延迟和费用，而后续检索还会用确认后的 `item_names` 限定产品范围，所以沿用参考项目的取舍。

### 7. 本节到哪里为止

```text
用户问题 + 会话历史
    → 提取商品名、改写问题
    → 在 kb_item_names 中混合检索
    → 评分对齐：确认 / 追问 / 拒答
    → 历史写入 MongoDB
    → 主图按 answer 选择直接输出或进入三路占位检索
```

本节不检索 `kb_chunks` 正文，不实现 HyDE、联网搜索、RRF、Rerank 和答案生成，不做 FastAPI、SSE 和前端，也不修改导入流程的主图。六个占位节点只验证路由，不代表这些能力已经实现。

## 二、手敲步骤

### 1. 先确认依赖和文件位置

打开 [pyproject.toml](../../pyproject.toml)，当前依赖里还没有 MongoDB 的 Python 客户端。在项目终端执行下面这一条依赖准备命令，它会更新 `pyproject.toml` 与 uv 锁文件，保留已有依赖：

```bash
uv add pymongo --default-index https://pypi.tuna.tsinghua.edu.cn/simple
```

本节会接触以下文件：

| 文件 | 你要做的事 |
| --- | --- |
| [.env.example](../../.env.example) | 追加 MongoDB 配置模板 |
| `src/shopkeeper_brain/core/mongo_config.py` | 新建 MongoDB 配置读取模块 |
| `src/shopkeeper_brain/utils/mongo_history_utils.py` | 新建历史对话读写工具与学习期入口 |
| `src/shopkeeper_brain/utils/milvus_utils.py` | 追加混合检索的两个函数 |
| `src/shopkeeper_brain/processor/query_processor/` | 新建 `__init__.py`、`state.py`、`base.py`、`main_graph.py` |
| `src/shopkeeper_brain/processor/query_processor/nodes/` | 新建 `__init__.py`、产品确认节点和六个占位节点 |

按“配置 → 历史工具 → Milvus 工具 → 状态与基类 → 产品确认节点 → 占位节点 → 主图”的顺序手敲，每个使用方出现时，被引用的文件已经存在。两个新目录各放一个空的 `__init__.py`，和 `processor/import_processor/` 的做法一致。

### 2. 追加 MongoDB 配置模板

开始之前先确认虚拟机上的 MongoDB 在运行。在虚拟机终端执行：

```bash
docker ps --filter name=my-mongo
```

`my-mongo` 的状态应是 `Up`，端口映射包含 `27017`。如果容器没有运行，用 `docker start my-mongo` 启动它；不需要重新部署，也不要删除 `/mongo-data` 里的数据。

不要替换 `.env.example` 的原有内容，在文件末尾追加下面的配置片段：

```dotenv
# ====================
# MongoDB
# ====================
# 账号密码只填在本地 .env；密码含 @ : / % 等字符时要先做 URL 编码
SHOPKEEPER_BRAIN_MONGO_URI=mongodb://admin:your-password@192.168.150.120:27017/?authSource=admin
SHOPKEEPER_BRAIN_MONGO_DB_NAME=kb001
```

然后在本地 `.env` 追加同名的两个变量，把 `your-password` 换成你在 docker-compose 里为 `MONGO_INITDB_ROOT_PASSWORD` 设置的真实密码。不要把真实密码写进 `.env.example`、教程或控制台输出。

连接地址的格式是 `mongodb://用户名:密码@主机:端口/?authSource=admin`。`authSource=admin` 指明到 `admin` 库里校验账号，因为 root 用户创建在那里；`kb001` 只是之后存放对话的业务库，由 `SHOPKEEPER_BRAIN_MONGO_DB_NAME` 单独配置。密码里如果有 `@`、`:`、`/`、`%` 这类字符，必须先做 URL 编码（例如 `@` 写成 `%40`），否则地址会被解析错。

### 3. 创建 MongoDB 配置模块

历史工具要读取地址和库名，先写配置模块，写法和第 8 节的 `milvus_config.py`、第 6 节的 `llm_config.py` 一致。

**文件**：`src/shopkeeper_brain/core/mongo_config.py`

```python
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class MongoConfig:
    """MongoDB 连接地址和对话历史所在的数据库；默认展示时隐藏含密码的地址。"""

    uri: str = field(repr=False)
    db_name: str


def load_mongo_config() -> MongoConfig:
    """从项目根目录读取 MongoDB 配置，系统环境变量优先。"""
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)

    return MongoConfig(
        uri=os.getenv("SHOPKEEPER_BRAIN_MONGO_URI", "").strip(),
        db_name=os.getenv("SHOPKEEPER_BRAIN_MONGO_DB_NAME", "").strip(),
    )
```

连接地址里带着密码，所以 `uri` 用 `field(repr=False)`，打印配置对象时不会显示它；其余写法与前面的配置模块相同：从模块位置找项目根目录，`override=False` 让系统环境变量优先，缺省值用空字符串，等真正连接时再检查。

### 4. 创建历史对话工具

产品确认节点要读历史、存消息、给旧消息补商品名，这些都围绕同一个集合，放进一个工具模块。节点只调用函数，不直接接触 MongoDB 客户端。

**文件**：`src/shopkeeper_brain/utils/mongo_history_utils.py`

```python
import logging
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import DESCENDING, MongoClient
from pymongo.collection import Collection

from shopkeeper_brain.core.mongo_config import load_mongo_config
from shopkeeper_brain.processor.import_processor.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

_chat_message: Collection | None = None


def get_chat_message_collection() -> Collection:
    """首次调用连接 MongoDB 并确保索引存在，后续在当前进程复用同一个集合对象。"""
    global _chat_message
    if _chat_message is not None:
        return _chat_message

    config = load_mongo_config()
    if not config.uri or not config.db_name:
        raise ConfigurationError(
            "MongoDB 未配置，请检查 SHOPKEEPER_BRAIN_MONGO_URI 和 "
            "SHOPKEEPER_BRAIN_MONGO_DB_NAME"
        )

    # 创建客户端不会立刻连接；5 秒内选不到服务器就报错，虚拟机没开时不用干等 30 秒。
    client = MongoClient(config.uri, serverSelectionTimeoutMS=5000)
    collection = client[config.db_name]["chat_message"]
    # “会话 + 时间倒序”复合索引，对应“取某个会话最新几条”；已存在时重复创建不会报错。
    collection.create_index([("session_id", 1), ("ts", -1)])
    _chat_message = collection
    return collection


def save_chat_message(
        session_id: str,
        role: str,
        text: str,
        rewritten_query: str = "",
        item_names: list[str] | None = None,
        message_id: str | None = None,
) -> str:
    """没有 message_id 时新增一条消息，有 message_id 时更新这条消息；返回消息主键字符串。"""
    collection = get_chat_message_collection()
    document = {
        "session_id": session_id,
        "role": role,
        "text": text,
        "rewritten_query": rewritten_query or "",
        "item_names": item_names or [],
    }

    if message_id:
        # 更新只改内容，不动 ts：消息的先后顺序以第一次写入的时间为准。
        collection.update_one({"_id": ObjectId(message_id)}, {"$set": document})
        return message_id

    document["ts"] = datetime.now().timestamp()
    result = collection.insert_one(document)
    return str(result.inserted_id)


def update_message_item_names(ids: list[str], item_names: list[str]) -> int:
    """批量给历史消息补上商品名，返回实际修改的条数；失败时记录日志并返回 0。"""
    collection = get_chat_message_collection()
    try:
        result = collection.update_many(
            {"_id": {"$in": [ObjectId(message_id) for message_id in ids]}},
            {"$set": {"item_names": item_names}},
        )
        return result.modified_count
    except Exception as exc:
        logger.error("批量回填商品名失败：%s", exc)
        return 0


def get_recent_messages(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """读取会话最近 limit 条消息，按时间从旧到新返回；查询失败时记录日志并返回空列表。"""
    collection = get_chat_message_collection()
    try:
        # 先倒序取最新的 limit 条，再翻转成正序；升序直接加 limit 只会取到最早的几条。
        # Windows 时钟刻度较粗，连续写入的消息 ts 可能相同，再按 _id 兜底保持写入顺序。
        cursor = (
            collection.find({"session_id": session_id})
            .sort([("ts", DESCENDING), ("_id", DESCENDING)])
            .limit(limit)
        )
        return list(cursor)[::-1]
    except Exception as exc:
        logger.error("读取历史消息失败：%s", exc)
        return []


def clear_history(session_id: str) -> int:
    """删除一个会话的全部消息，返回删除条数；失败时记录日志并返回 0。"""
    collection = get_chat_message_collection()
    try:
        return collection.delete_many({"session_id": session_id}).deleted_count
    except Exception as exc:
        logger.error("清空会话历史失败：%s", exc)
        return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    session_id = "day09-history-check"
    clear_history(session_id)  # 每次从空会话开始，结果才能重复

    first_id = save_chat_message(session_id, "user", "你好，有万用表吗？")
    save_chat_message(session_id, "assistant", "你好！请问你想询问哪个型号？")
    save_chat_message(session_id, "user", "RS-12 万用表")
    save_chat_message(session_id, "assistant", "有的")

    # 更新第一条消息：内容变了，但它仍然排在最前面。
    save_chat_message(
        session_id,
        "user",
        "你好，有万用表吗？",
        rewritten_query="有没有万用表？",
        message_id=first_id,
    )
    messages = get_recent_messages(session_id)
    assert [m["text"] for m in messages] == [
        "你好，有万用表吗？",
        "你好！请问你想询问哪个型号？",
        "RS-12 万用表",
        "有的",
    ]
    assert messages[0]["rewritten_query"] == "有没有万用表？"

    # 只取最近 2 条，仍然是从旧到新。
    latest = get_recent_messages(session_id, limit=2)
    assert [m["text"] for m in latest] == ["RS-12 万用表", "有的"]

    # 批量回填：给还没有商品名的消息补上商品名。
    ids = [str(m["_id"]) for m in messages if not m["item_names"]]
    assert update_message_item_names(ids, ["RS PRO RS-12 数字万用表"]) == 4

    for message in get_recent_messages(session_id):
        print(message["role"], message["item_names"], message["text"])
    print("MongoDB 历史读写：通过")
```

先看连接。`get_chat_message_collection()` 和第 8 节的 `get_milvus_client()` 同一个写法：第一次调用才连接，之后复用同一个集合对象。参考项目在导入模块时就连接 MongoDB，虚拟机没开时，仅仅 `import` 产品确认节点就会失败；改成首次使用时连接后，错误出现在真正读写历史的那一行。`MongoClient(...)` 本身不联网，`create_index()` 才会真正发出请求，也正是在这里验证账号密码。

再看四个函数的取舍：

- `save_chat_message()` 用 `message_id` 区分新增和更新。更新时不写 `ts`：产品确认节点先保存用户消息（第 3 步），最后又更新它（第 8 步），如果更新也改 `ts`，用户消息的时间会晚于中间保存的助手回答，下一轮读到的历史就变成“先回答、后提问”。
- `get_recent_messages()` 先按 `ts` 倒序取最新的 `limit` 条，再翻转成从旧到新。参考项目是升序后直接 `limit`，那样返回的是最早的几条，会话超过 10 条后模型读到的就不是最近的上下文。
- `update_message_item_names()` 用 `$in` 一次更新多条，后面分支 A 回填历史时用它。
- 读写历史属于“尽力而为”：查询和批量更新失败时只记日志并返回空结果，不拖垮整次问答；但取集合放在 `try` 之外，所以配置缺失或连不上服务器会直接抛出，不会被吞掉。

学习期入口先清空自己的测试会话，再写入四条消息，依次检查顺序、更新后顺序不变、`limit` 取到最近两条和批量回填，最后打印结果。它用的是 `day09-history-check` 这个测试会话，不会碰其他会话的数据。

### 5. 给 Milvus 工具追加混合检索

产品确认要把名称的 Dense、Sparse 两路向量一起拿去检索，这两个函数在你的 `milvus_utils.py` 里还没有。参考项目在后面章节的笔记里才补出它们，但本节的节点马上要用，所以先加在这里。两处改动都落在已有文件上，不要重抄其他内容。

#### 5.1 修改导入

找到文件开头的 `from pymilvus import MilvusClient`，改成下面这一行：

```python
from pymilvus import AnnSearchRequest, MilvusClient, WeightedRanker
```

#### 5.2 在文件末尾追加两个函数

接在 `restore_sparse_vector()` 之后，保留前面的空行：

```python
def create_hybrid_search_requests(
        dense_vector: list[float],
        sparse_vector: dict[int, float],
        limit: int = 5,
) -> list[AnnSearchRequest]:
    """为同一段文本构造 Dense 与 Sparse 两路检索请求，度量方式与入库时的索引一致。"""
    dense_req = AnnSearchRequest(
        data=[dense_vector],
        anns_field="dense_vector",
        param={"metric_type": "COSINE"},
        limit=limit,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_vector],
        anns_field="sparse_vector",
        param={"metric_type": "IP"},
        limit=limit,
    )
    return [dense_req, sparse_req]


def hybrid_search(
        client: MilvusClient,
        collection_name: str,
        reqs: list[AnnSearchRequest],
        ranker_weights: tuple[float, float] = (0.5, 0.5),
        norm_score: bool = False,
        limit: int = 5,
        output_fields: list[str] | None = None,
) -> list[list[dict]]:
    """两路结果按权重融合排序；每个查询返回一个按评分从高到低排列的候选列表。"""
    ranker = WeightedRanker(*ranker_weights, norm_score=norm_score)
    return client.hybrid_search(
        collection_name=collection_name,
        reqs=reqs,
        ranker=ranker,
        limit=limit,
        output_fields=output_fields,
    )
```

`anns_field` 和 `metric_type` 对应第 8 节建集合时的索引：`dense_vector` 用 `COSINE`，`sparse_vector` 用 `IP`，换了度量方式检索会报错或得到无意义的分数。两路请求各取 `limit` 条候选，`WeightedRanker` 再按 `ranker_weights` 把两路融合，依次对应 Dense 和 Sparse。`norm_score=True` 表示先把两路得分换算到 0 到 1 再加权，0.8 和 0.2 两个权重才落在同一把尺子上。

函数不捕获异常，也不替调用方决定失败后怎么办；`hybrid_search()` 返回的外层列表对应每个查询向量，本节每次只查一个，所以取 `[0]`。

### 6. 创建查询状态和节点基类

先建两个新目录，各放一个空的 `__init__.py`：`src/shopkeeper_brain/processor/query_processor/` 和 `src/shopkeeper_brain/processor/query_processor/nodes/`。然后写状态，它是所有节点之间的数据契约。

**文件**：`src/shopkeeper_brain/processor/query_processor/state.py`

```python
from typing import TypedDict


class QueryGraphState(TypedDict, total=False):
    """查询流程中所有节点共享的状态；各字段由不同节点逐步写入，所以都不是必填。"""

    # 用户输入
    session_id: str
    message_id: str
    original_query: str

    # 产品确认写入
    rewritten_query: str
    item_names: list[str]
    history: list[dict[str, object]]

    # 三路检索各写各的字段
    embedding_chunks: list[dict[str, object]]
    hyde_embedding_chunks: list[dict[str, object]]
    web_search_docs: list[dict[str, object]]

    # 融合、重排和生成
    rrf_chunks: list[dict[str, object]]
    reranked_docs: list[dict[str, object]]
    prompt: str
    answer: str
    is_stream: bool
```

`total=False` 表示这些键都可以缺席：学习期入口只传 `session_id` 和 `original_query`，并行节点也只返回自己负责的字段。字段按“谁写入”分组，`answer` 是整张图的关键信号：产品确认写入了它，就表示不需要再检索。

接着写节点基类。它和导入流程的 `BaseNode` 一样提供日志外壳，区别是日志前缀换成 `query.`，异常先记录再原样抛出，查询流程暂时没有自己的异常类型。

**文件**：`src/shopkeeper_brain/processor/query_processor/base.py`

```python
import logging
from abc import ABC, abstractmethod

from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeBase(ABC):
    """所有查询节点共享的执行外壳：统一日志，异常记录后原样抛出。"""

    name = "base_node"

    def __init__(self) -> None:
        if self.name == "base_node":
            raise ValueError("子类必须覆盖 name")
        self.logger = logging.getLogger(f"query.{self.name}")

    def __call__(self, state: QueryGraphState) -> QueryGraphState:
        """让节点实例可以被 LangGraph 当作函数调用。"""
        self.logger.info("%s 开始", self.name)
        try:
            result = self.process(state)
        except Exception as exc:
            self.logger.error("%s 失败：%s", self.name, exc)
            raise
        self.logger.info("%s 完成", self.name)
        return result

    @abstractmethod
    def process(self, state: QueryGraphState) -> QueryGraphState:
        """子类实现具体业务。"""
        raise NotImplementedError
```

### 7. 写产品确认节点和真实入口

现在写使用方。先读 `process()` 的调用顺序，对照前面的八步图，再手敲各个方法。

**文件**：`src/shopkeeper_brain/processor/query_processor/nodes/node_item_name_confirm.py`

```python
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from shopkeeper_brain.core.llm_config import load_llm_config
from shopkeeper_brain.core.milvus_config import load_milvus_config
from shopkeeper_brain.processor.import_processor.exceptions import (
    ConfigurationError,
    StateFieldError,
)
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState
from shopkeeper_brain.utils.embedding_utils import generate_embeddings
from shopkeeper_brain.utils.milvus_utils import (
    create_hybrid_search_requests,
    get_milvus_client,
    hybrid_search,
)
from shopkeeper_brain.utils.mongo_history_utils import (
    clear_history,
    get_recent_messages,
    save_chat_message,
    update_message_item_names,
)

CONFIRM_SCORE = 0.85
CANDIDATE_SCORE = 0.6
CANDIDATE_LIMIT = 3


class NodeItemNameConfirm(NodeBase):
    """确认用户问的是哪个产品；无法确认时直接生成追问或拒答。"""

    name = "node_item_name_confirm"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """读取 session_id、original_query；写入 history、rewritten_query、item_names，
        需要追问或拒答时写入 answer。"""
        session_id, original_query = self._step_1_validate_param(state)

        # 先读历史再保存当前问题，否则历史里会混进用户刚说的这一句。
        history = get_recent_messages(session_id)
        state["history"] = history
        self.logger.info("步骤 2：读取到 %d 条历史消息", len(history))

        message_id = save_chat_message(session_id, "user", original_query)
        self.logger.info("步骤 3：当前问题已保存，message_id=%s", message_id)

        extracted = self._step_4_extract_info(original_query, history)
        state["rewritten_query"] = extracted["rewritten_query"]
        state["item_names"] = extracted["item_names"]

        align_result: dict[str, list[str]] = {}
        if extracted["item_names"]:
            query_results = self._step_5_vectorize_and_query(extracted["item_names"])
            align_result = self._step_6_align_item_names(query_results)
        else:
            self.logger.info("没有提取到商品名，跳过名称检索")

        self._step_7_check_confirmation(state, align_result, history)
        self._step_8_write_history(state, session_id, message_id)
        return state

    def _step_1_validate_param(self, state: QueryGraphState) -> tuple[str, str]:
        """session_id 和 original_query 是节点的输入契约，缺任何一个都无法继续。"""
        session_id = state.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise StateFieldError(
                node_name=self.name,
                field_name="session_id",
                expected_type=str,
            )

        original_query = state.get("original_query")
        if not isinstance(original_query, str) or not original_query.strip():
            raise StateFieldError(
                node_name=self.name,
                field_name="original_query",
                expected_type=str,
            )

        return session_id, original_query

    def _step_4_extract_info(self, query: str, history: list[dict]) -> dict:
        """让文本模型提取商品名并改写问题；模型不可用或返回异常时退回“无商品名 + 原问题”。"""
        fallback = {"item_names": [], "rewritten_query": query}

        config = load_llm_config()
        if not all((config.base_url, config.api_key, config.model)):
            self.logger.warning("文本模型配置不完整，跳过商品名提取")
            return fallback

        history_text = "".join(
            f"{message['role']}: {message['text']}\n" for message in history
        )
        # f-string 里要输出普通大括号，必须写成双大括号。
        prompt = f"""历史会话：
{history_text}
当前用户问题：{query}

请根据历史会话和当前问题，提取用户正在询问的商品名称（item_names）。
1. 如果用户明确提到了商品名称，请提取出来。可能有一个或多个，但不能重复。
2. 如果用户使用了代词（如“这个”“它”），请结合历史会话指代消解，确定商品名称。
3. 如果无法确定商品名称，item_names 返回空列表。
4. 请重新改写用户的问题（rewritten_query），使其成为包含商品名称的独立完整问题。

请直接返回 JSON，格式如下：
{{"item_names": ["商品A", "商品B"], "rewritten_query": "关于商品A和商品B，……"}}
"""

        try:
            model = ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=config.temperature,
                extra_body={"enable_thinking": False},
            )
            response = model.invoke(
                [
                    SystemMessage(
                        content="你是一个专业的客服助手，擅长理解用户意图和提取关键信息。"
                    ),
                    HumanMessage(content=prompt),
                ]
            )
            text = response.text.strip()
            # 模型可能把 JSON 包进代码围栏，只取第一个 { 到最后一个 } 之间的内容。
            result = json.loads(text[text.index("{"): text.rindex("}") + 1])
        except Exception as exc:
            self.logger.warning("商品名提取失败，退回原问题：%s", type(exc).__name__)
            return fallback

        item_names = result.get("item_names")
        if not isinstance(item_names, list):
            item_names = []
        rewritten_query = result.get("rewritten_query")
        if not isinstance(rewritten_query, str) or not rewritten_query.strip():
            rewritten_query = query

        extracted = {
            "item_names": [
                name.strip()
                for name in item_names
                if isinstance(name, str) and name.strip()
            ],
            "rewritten_query": rewritten_query.strip(),
        }
        self.logger.info("步骤 4：提取结果 %s", extracted)
        return extracted

    def _step_5_vectorize_and_query(self, item_names: list[str]) -> list[dict]:
        """把每个提取名称在 kb_item_names 中做 Dense + Sparse 混合检索，返回候选和评分。"""
        collection_name = load_milvus_config().item_name_collection
        if not collection_name:
            raise ConfigurationError(
                "主体名称集合未配置，请检查 "
                "SHOPKEEPER_BRAIN_MILVUS_ITEM_NAME_COLLECTION",
                node_name=self.name,
            )

        client = get_milvus_client()
        embeddings = generate_embeddings(item_names)

        results: list[dict] = []
        for index, extracted_name in enumerate(item_names):
            try:
                reqs = create_hybrid_search_requests(
                    embeddings["dense"][index],
                    embeddings["sparse"][index],
                )
                hits = hybrid_search(
                    client,
                    collection_name,
                    reqs,
                    ranker_weights=(0.8, 0.2),
                    norm_score=True,
                    limit=5,
                    output_fields=["item_name"],
                )
                matches = [
                    {
                        "item_name": hit["entity"]["item_name"],
                        "score": hit["distance"],
                    }
                    for hit in hits[0]
                ]
                self.logger.info("步骤 5：%r 的候选 %s", extracted_name, matches)
                results.append({"extracted_name": extracted_name, "matches": matches})
            except Exception as exc:
                self.logger.error("步骤 5：查询 %r 失败：%s", extracted_name, exc)

        return results

    def _step_6_align_item_names(
            self,
            query_results: list[dict],
    ) -> dict[str, list[str]]:
        """按评分把提取名称对齐成“确认”和“候选”，两个列表都去重并保持评分从高到低的顺序。"""
        confirmed: list[str] = []
        options: list[str] = []

        for result in query_results:
            extracted_name = result["extracted_name"].strip()
            matches = result["matches"]

            high = [m for m in matches if m["score"] > CONFIRM_SCORE]
            if high:
                # 多个都很像时，优先取与提取名完全相同的；没有就取最高分，Milvus 已按分数排好。
                picked = next(
                    (m for m in high if m["item_name"] == extracted_name),
                    high[0],
                )
                confirmed.append(picked["item_name"])
                continue

            options.extend(
                m["item_name"] for m in matches if m["score"] >= CANDIDATE_SCORE
            )

        # 用 dict.fromkeys 去重而不是 set：set 会打乱顺序，追问时取前几个就可能漏掉评分最高的。
        return {
            "confirmed_item_names": list(dict.fromkeys(confirmed)),
            "options": list(dict.fromkeys(options)),
        }

    def _step_7_check_confirmation(
            self,
            state: QueryGraphState,
            align_result: dict[str, list[str]],
            history: list[dict],
    ) -> None:
        """三个分支：已确认继续检索，只有候选就追问，什么都没有就拒答；直接修改 state。"""
        confirmed = align_result.get("confirmed_item_names", [])
        options = align_result.get("options", [])

        if confirmed:
            # 分支 A：历史里还没有商品名的消息补上它，后面的对话就能沿用这个商品。
            ids = [
                str(message["_id"])
                for message in history
                if not message.get("item_names")
            ]
            if ids:
                update_message_item_names(ids, confirmed)
            state["item_names"] = confirmed
            state["answer"] = ""
            return

        state["item_names"] = []
        if options:
            # 分支 B
            options_text = "、".join(options[:CANDIDATE_LIMIT])
            state["answer"] = f"您是想问以下哪个产品：{options_text}？请明确一下型号。"
        else:
            # 分支 C
            state["answer"] = "抱歉，未找到相关产品，请提供准确型号以便我为您查询。"

    def _step_8_write_history(
            self,
            state: QueryGraphState,
            session_id: str,
            message_id: str,
    ) -> None:
        """追问或拒答要作为助手消息入库；再把改写问题和商品名补到第 3 步保存的用户消息上。"""
        if state.get("answer"):
            save_chat_message(
                session_id,
                "assistant",
                state["answer"],
                item_names=state["item_names"],
            )

        save_chat_message(
            session_id,
            "user",
            state["original_query"],
            rewritten_query=state["rewritten_query"],
            item_names=state["item_names"],
            message_id=message_id,
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    session_id = "day09-confirm-demo"
    # 按顺序发送的用户问题；只验证拒答分支时，改成 ["iPhone 15 怎么充电？"]。
    queries = ["RS-12 怎么测电压？", "对，就是这个，怎么测电压？"]

    clear_history(session_id)  # 每次从空会话开始，结果才能重复
    node = NodeItemNameConfirm()
    for query in queries:
        result = node({"session_id": session_id, "original_query": query})
        print("问题：", query)
        print("改写问题：", result["rewritten_query"])
        print("确认商品：", result["item_names"])
        print("直接回答：", result["answer"] or "（空：可以继续检索）")
        print("-" * 30)

    print("会话历史：")
    for message in get_recent_messages(session_id):
        print(message["role"], message["item_names"], message["text"])
```

#### 先看输入、历史和保存顺序

`process()` 前半段就是第 2、3 步：`get_recent_messages()` 取回的是列表，每个元素是 MongoDB 文档转成的字典，包含 `_id`、`role`、`text` 和 `item_names`。拿到历史之后才保存当前问题，`save_chat_message()` 返回的 `message_id` 留到第 8 步，用来更新同一条消息。

`_step_1_validate_param()` 抛出的 `StateFieldError` 沿用第 6 节的做法，字段名和期望类型会出现在异常信息里。`process()` 的两个入参字段缺一个，节点就停止，不继续读历史或调用模型。

#### 再看模型调用和容错

`_step_4_extract_info()` 的客户端写法沿用第 6 节：`ChatOpenAI` 加 `SystemMessage`、`HumanMessage`，用 `response.text` 取正文，不用 `response.content`。第 6 节验收时已经遇到过，`content` 可能是字符串，也可能是内容块列表，`text` 才能统一取出文字。

参考课堂代码打开了 JSON 模式，这里不开：你的网关是否支持 `response_format` 不确定，不支持时每次请求都会失败，节点只能一直退回兜底。改为只在提示词里要求返回 JSON，解析时截取第一个 `{` 到最后一个 `}` 之间的内容，即使模型把 JSON 包进代码围栏，也能解析。

模型的返回属于外部输入，所以提取后还要检查形状：`item_names` 不是列表就当作空，名称去掉空白并丢掉空字符串，`rewritten_query` 为空就用原问题。配置不完整、调用失败、返回无法解析都会走 `fallback`，也就是“没有商品名 + 原问题”，后面自然进入分支 C。这时看到“未找到相关产品”，并不能说明库里没有这个产品，要回头看第 4 步日志里是否出现了“跳过”或“失败”。

#### 然后看检索和评分

`_step_5_vectorize_and_query()` 先一次性给全部提取名称生成向量，再逐个检索。`ranker_weights=(0.8, 0.2)` 让 Dense 占 0.8、Sparse 占 0.2，沿用参考项目的配比。`hits[0]` 是第一个查询向量的结果列表，每个元素有 `entity`（输出字段）和 `distance`（融合后的评分）。

单个名称检索失败只记录错误并继续其他名称。要注意这个取舍：Milvus 或向量模型出故障时，这一步没有任何结果，最终会被判成分支 C 的“未找到相关产品”；日志里出现“步骤 5：查询 …… 失败”时，不能把这次当作分支 C 通过。

`_step_6_align_item_names()` 把评分翻译成确认和候选。去重用 `dict.fromkeys()` 而不是参考项目的 `set()`：Milvus 返回的候选本来按评分从高到低排列，`set` 会打乱它，而追问只取前 3 个，可能把评分最高的漏掉。

#### 最后看分支和历史

第 7 步直接修改 `state`。分支 A 把 `answer` 置为空字符串，路由据此判断可以继续检索；分支 B、C 的 `item_names` 都是空列表，`answer` 是追问或拒答。分支 A 还会把历史里 `item_names` 为空的消息补上确认的商品名：前一轮的追问和用户的短型号这时才知道指的是谁。

第 8 步里，只有 `answer` 有值才保存助手消息；用户消息则一定要更新，补上 `rewritten_query` 和 `item_names`。因为 `save_chat_message()` 更新时不改 `ts`，用户消息仍排在助手回答前面。

学习期入口在同一个会话里连续问两句，第一句应该被追问，第二句靠追问里的完整名称完成确认；打印的会话历史里，三条消息最终都带着确认的商品名。想验证拒答，把 `queries` 改成 `["iPhone 15 怎么充电？"]`。

### 8. 创建六个占位节点

主图要把七个节点都注册进去，其余六个先写成占位：继承 `NodeBase`、覆盖 `name`、返回空结果。前三个并行节点只返回自己的字段。

**文件**：`src/shopkeeper_brain/processor/query_processor/nodes/node_search_embedding.py`

```python
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeSearchEmbedding(NodeBase):
    """基于已确认的商品名和改写后的问题，在 Milvus 中检索 Chunk；本节只占位。"""

    name = "node_search_embedding"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # 三路检索并行执行，各自只返回自己负责的字段，避免同时写同一批键。
        return {"embedding_chunks": []}
```

**文件**：`src/shopkeeper_brain/processor/query_processor/nodes/node_search_embedding_hyde.py`

```python
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeSearchEmbeddingHyde(NodeBase):
    """先让模型生成假设性答案，再用答案做向量检索；本节只占位。"""

    name = "node_search_embedding_hyde"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return {"hyde_embedding_chunks": []}
```

**文件**：`src/shopkeeper_brain/processor/query_processor/nodes/node_web_search_mcp.py`

```python
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeWebSearchMcp(NodeBase):
    """调用外部搜索服务补充互联网信息；本节只占位。"""

    name = "node_web_search_mcp"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return {"web_search_docs": []}
```

**文件**：`src/shopkeeper_brain/processor/query_processor/nodes/node_rrf.py`

```python
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeRrf(NodeBase):
    """把多路召回结果融合排序；本节只占位，状态原样通过。"""

    name = "node_rrf"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return state
```

**文件**：`src/shopkeeper_brain/processor/query_processor/nodes/node_rerank.py`

```python
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeRerank(NodeBase):
    """对融合后的结果做精细重排；本节只占位，状态原样通过。"""

    name = "node_rerank"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return state
```

**文件**：`src/shopkeeper_brain/processor/query_processor/nodes/node_answer_output.py`

```python
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeAnswerOutput(NodeBase):
    """根据检索结果生成最终回答，或直接输出追问与拒答；本节只占位，状态原样通过。"""

    name = "node_answer_output"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return state
```

占位节点不写业务，只让主图能够完整运行；`NodeBase` 已经负责输出“开始”和“完成”日志，所以验证时能直接从日志看出哪些节点被执行。

### 9. 创建查询主图

最后写主图，把七个节点按路由连起来。

**文件**：`src/shopkeeper_brain/processor/query_processor/main_graph.py`

```python
import logging

from langgraph.constants import END
from langgraph.graph import StateGraph

from shopkeeper_brain.processor.query_processor.nodes.node_answer_output import (
    NodeAnswerOutput,
)
from shopkeeper_brain.processor.query_processor.nodes.node_item_name_confirm import (
    NodeItemNameConfirm,
)
from shopkeeper_brain.processor.query_processor.nodes.node_rerank import NodeRerank
from shopkeeper_brain.processor.query_processor.nodes.node_rrf import NodeRrf
from shopkeeper_brain.processor.query_processor.nodes.node_search_embedding import (
    NodeSearchEmbedding,
)
from shopkeeper_brain.processor.query_processor.nodes.node_search_embedding_hyde import (
    NodeSearchEmbeddingHyde,
)
from shopkeeper_brain.processor.query_processor.nodes.node_web_search_mcp import (
    NodeWebSearchMcp,
)
from shopkeeper_brain.processor.query_processor.state import QueryGraphState
from shopkeeper_brain.utils.mongo_history_utils import clear_history

SEARCH_NODES = [
    "node_search_embedding",
    "node_search_embedding_hyde",
    "node_web_search_mcp",
]


class KBQueryWorkflow:
    """知识库查询工作流：注册节点、定义路由，并提供统一的执行入口。"""

    def __init__(self) -> None:
        self.workflow = StateGraph(QueryGraphState)
        self._register_nodes()
        self._setup_routes()
        self._compiled_app = None

    def _register_nodes(self) -> None:
        """图里的节点名直接取节点类的 name，路由里写的字符串必须与它一致。"""
        for node in (
                NodeItemNameConfirm(),
                NodeSearchEmbedding(),
                NodeSearchEmbeddingHyde(),
                NodeWebSearchMcp(),
                NodeRrf(),
                NodeRerank(),
                NodeAnswerOutput(),
        ):
            self.workflow.add_node(node.name, node)

    def _route_after_item_name_confirm(self, state: QueryGraphState) -> str | list[str]:
        """有 answer 说明要追问或拒答，直接输出；否则三路检索并行。"""
        if state.get("answer"):
            return "node_answer_output"
        return SEARCH_NODES

    def _setup_routes(self) -> None:
        """设置入口、条件路由和后续的固定连线。"""
        self.workflow.set_entry_point("node_item_name_confirm")
        self.workflow.add_conditional_edges(
            "node_item_name_confirm",
            self._route_after_item_name_confirm,
            ["node_answer_output", *SEARCH_NODES],
        )

        for node_name in SEARCH_NODES:
            self.workflow.add_edge(node_name, "node_rrf")
        self.workflow.add_edge("node_rrf", "node_rerank")
        self.workflow.add_edge("node_rerank", "node_answer_output")
        self.workflow.add_edge("node_answer_output", END)

    def compile(self):
        """编译一次并缓存。"""
        if self._compiled_app is None:
            self._compiled_app = self.workflow.compile()
        return self._compiled_app

    def run(self, initial_state: QueryGraphState) -> QueryGraphState:
        """同步执行整张图，返回最终状态。"""
        return self.compile().invoke(initial_state)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    # 每个问题用独立会话，互不影响；第一个走拒答分支，第二个走确认分支。
    cases = [
        ("day09-graph-reject", "iPhone 15 怎么充电？"),
        ("day09-graph-confirm", "RS PRO RS-12 数字万用表怎么测电压？"),
    ]

    workflow = KBQueryWorkflow()
    for session_id, query in cases:
        clear_history(session_id)
        final_state = workflow.run({"session_id": session_id, "original_query": query})
        print("问题：", query)
        print("确认商品：", final_state["item_names"])
        print("直接回答：", final_state["answer"] or "（空：已经过三路占位检索）")
        print("-" * 30)
```

`_register_nodes()` 用节点自己的 `name` 注册，避免同一个字符串在两个地方各写一遍。`_route_after_item_name_confirm()` 返回一个字符串表示只走一条边，返回列表表示同时走多条边，LangGraph 会把列表里的三个节点放在同一步并行执行。`add_conditional_edges()` 的第三个参数列出路由可能返回的全部节点，图的结构才完整。三条检索边都指向 `node_rrf`：它们在同一步结束，所以 `node_rrf` 只会执行一次。

`compile()` 缓存编译结果，`run()` 调用 `invoke()` 返回最终状态。参考项目的 `run()` 还支持流式输出，本节用不到，留到真正需要流式的章节再加。

学习期入口依次跑两个问题：第一个与库里的产品明显无关，预期直接拒答；第二个带完整产品名，预期确认后经过三路占位检索。它没有接入任何 HTTP 服务，只是验证主图的路由。

## 三、必做真实验证

### 1. 准备真实服务

下面的操作必须使用真实服务。未运行的操作在你的记录中标为“未验证（未运行）”，不要用依赖安装、编译或模块导入替代真实运行。

准备：

1. 虚拟机保持运行，`my-mongo` 容器状态为 `Up`；Windows 能访问 `192.168.150.120:27017`。
2. 本地 `.env` 有 `SHOPKEEPER_BRAIN_MONGO_URI`（含真实账号密码和 `?authSource=admin`）与 `SHOPKEEPER_BRAIN_MONGO_DB_NAME=kb001`，原来的 Milvus、文本模型和 BGE-M3 配置保持不变。
3. Milvus 可用，`kb_item_names` 仍有第 8 节入库的 1 条记录 `RS PRO RS-12 数字万用表`。可以在 Attu 或第 8 节的验证入口里确认，本节不重新入库。
4. 第 6 节的文本模型配置有效；本地 BGE-M3 位于 `workspace/models/bge-m3`，CPU 推理，第一次加载会比较慢。
5. IDE 使用本工程的 uv 解释器，已经执行过 `uv add pymongo`，能够导入 `pymongo` 和 `shopkeeper_brain`。

这里的数据流是“真实 MongoDB 历史 → 真实文本模型提取 → 真实 BGE-M3 与 Milvus 名称检索 → 三个分支 → 主图路由”。

### 2. 先验证 MongoDB 历史工具

1. 打开 `src/shopkeeper_brain/utils/mongo_history_utils.py`，找到文件末尾的 `if __name__ == "__main__":`。
2. 选择本工程解释器，直接 Run，不需要填写参数。
3. 观察控制台：先按“从旧到新”打印四条消息，`item_names` 都是 `['RS PRO RS-12 数字万用表']`，最后一行是“MongoDB 历史读写：通过”。

入口里的 `assert` 分别在检查：更新第一条消息之后顺序不变；`limit=2` 取到的是最近两条而不是最早两条；批量回填修改了四条。它们全部通过，才说明账号密码、`authSource`、索引和排序都正常。

可选：用 MongoDB Compass 连接同一个地址，在数据库 `kb001` 的 `chat_message` 里能看到 `session_id` 为 `day09-history-check` 的四条文档，`ts` 从小到大依次排列。

### 3. 验证产品确认节点的三个分支

打开 `node_item_name_confirm.py`，找到文件末尾的 `if __name__ == "__main__":`。在第 4 步的“提取结果”日志、第 5 步的“候选”日志和 `_step_7_check_confirmation()` 处可以设断点，观察数据怎样变化。

**第一次运行：先追问，再确认。** 保持默认的两句问题直接 Run。

1. 第一句 `RS-12 怎么测电压？`：第 4 步日志里应提取出 `RS-12` 之类的短名称；第 5 步日志里候选是 `RS PRO RS-12 数字万用表`，评分在 0.6 到 0.85 之间（参考约 0.76）。输出的“确认商品”是 `[]`，“直接回答”是“您是想问以下哪个产品：RS PRO RS-12 数字万用表？请明确一下型号。”这是分支 B。
2. 第二句 `对，就是这个，怎么测电压？`：第 4 步读到的历史里有上一句追问，模型应把“这个”解析成完整名称并改写问题；第 5 步评分应大于 0.85（参考约 0.92）。输出的“确认商品”是 `['RS PRO RS-12 数字万用表']`，“直接回答”是“（空：可以继续检索）”。这是分支 A。
3. 最后打印的会话历史应有三条：用户的第一句、助手的追问、用户的第二句，`item_names` 都是 `['RS PRO RS-12 数字万用表']`。第一句和追问原本是空的，是分支 A 把它们补上的。

如果第二句仍然被追问，看第 4 步日志里的提取名称：模型没有从历史里取到完整名称时，把第二句改成 `RS PRO RS-12 数字万用表怎么测电压？` 再运行一次。

**第二次运行：拒答。** 把 `queries` 改成 `["iPhone 15 怎么充电？"]` 再运行。第 5 步评分应小于 0.6（参考约 0.53），“确认商品”是 `[]`，“直接回答”是“抱歉，未找到相关产品，请提供准确型号以便我为您查询。”会话历史里是用户消息和这条助手消息，用户消息在前。这是分支 C。

如果日志里的评分刚好高于 0.6，例如模型把名称写得更长，就进入了分支 B；换成 `示波器怎么用？` 再试一次。判断分支只看日志里的实际评分和程序输出，不要求措辞与上面完全一致。

三种分支共同的判据：`answer` 有值时 `item_names` 一定为空，`answer` 为空时 `item_names` 一定非空；分支 A 之后历史里的旧消息带上了商品名；用户消息的改写问题已经写进 `rewritten_query`。

### 4. 验证查询主图

1. 打开 `src/shopkeeper_brain/processor/query_processor/main_graph.py`，找到文件末尾的 `if __name__ == "__main__":`。
2. 选择本工程解释器，直接 Run，不需要先运行产品确认节点。
3. 观察日志，第一个问题 `iPhone 15 怎么充电？`：`query.node_item_name_confirm` 开始并完成之后，紧接着是 `query.node_answer_output`，三个检索节点、`node_rrf` 和 `node_rerank` 都不应该出现。输出的“直接回答”是拒答话术。
4. 第二个问题 `RS PRO RS-12 数字万用表怎么测电压？`：产品确认完成后，`node_search_embedding`、`node_search_embedding_hyde`、`node_web_search_mcp` 三个节点都会开始和完成，它们的先后顺序可以交错；随后依次是 `node_rrf`、`node_rerank`、`node_answer_output`。输出的“确认商品”是完整名称，“直接回答”是“（空：已经过三路占位检索）”。

如果第二个问题被追问，看产品确认日志里提取的名称和评分，原因同上一节。两个问题都不应该抛出异常，也不应该出现 LangGraph 的 `InvalidUpdateError`。

### 5. 失败时按数据经过的位置定位

| 看到的现象 | 先看哪里 | 对应原因或下一步 |
| --- | --- | --- |
| 5 秒后报 `ServerSelectionTimeoutError` | 虚拟机、`my-mongo` 状态、`27017` 端口、`.env` 里的地址 | 连不上服务器；不要改成本地地址，也不要重建容器 |
| `Authentication failed` 或 `OperationFailure` | `.env` 的用户名、密码和 `?authSource=admin` | 账号在 `admin` 库；密码以首次初始化 `/mongo-data` 时设置的为准，之后改 compose 里的值不会修改已有用户；特殊字符要 URL 编码 |
| `ConfigurationError: MongoDB 未配置` | 本地 `.env` 和变量名 | 连接还没有开始，先修正配置 |
| 修改 `.env` 后仍使用旧值 | IDE 运行配置里的环境变量 | 系统环境变量优先于 `.env` |
| 历史顺序不对，或总是读到最早的消息 | `get_recent_messages()` 的排序 | 要先倒序取最新再翻转 |
| 追问回答排在用户问题前面 | `save_chat_message()` 的更新分支 | 更新时不应该写 `ts` |
| 日志出现“文本模型配置不完整，跳过商品名提取” | 第 6 节的四个 `LLM` 变量 | 没有发起模型调用，只走了兜底，最后会得到拒答 |
| 日志出现“商品名提取失败，退回原问题” | 日志里的异常类型、接口地址、模型名、网络 | 本次不能算提取成功，也不是分支 C 通过 |
| 日志出现“步骤 5：查询 …… 失败” | Milvus 服务、`kb_item_names`、BGE-M3 模型路径 | 服务故障会被兜底成“未找到相关产品”，不能记为分支 C 通过 |
| 候选总是只有一个产品 | `kb_item_names` 的记录 | 正常：库里目前只有 `RS PRO RS-12 数字万用表` |
| 有 `answer` 却仍进入三路检索，或相反 | `_route_after_item_name_confirm()` 和 `state["answer"]` | 分支 A 要把 `answer` 置为空，B、C 要写入话术 |
| 报 `InvalidUpdateError` | 三个并行检索节点的返回值 | 并行节点只能返回自己的字段，不能返回整份状态 |

排查接口问题时只保留脱敏后的异常类型和现象，不打印连接地址里的密码。正常验证不需要停止外部服务或故意改坏源码。

### 6. 哪些结果可以记录为通过

本节完整通过需要三部分证据：

1. **MongoDB 历史工具**：真实服务上能认证连接，`mongo_history_utils.py` 入口里的 `assert` 全部通过；
2. **产品确认节点**：分支 A、B、C 各在真实评分下出现过一次；分支 A 后历史旧消息带上商品名；答案和商品名不同时出现；
3. **查询主图**：有 `answer` 时直接到 `node_answer_output`，没有 `answer` 时三路占位节点并行执行后汇合，两个问题都没有异常。

如果 MongoDB 不可达，记录“MongoDB 历史读写：失败（或未验证）”，后面两项也无法继续。如果文本模型配置缺失，记录“真实模型提取：跳过”，但这时节点只会得到拒答，不能记为分支 A、B 通过。如果只看到依赖安装成功、Python 编译成功、模块可以导入或主图可以编译，都不能记录为本节完整通过。尚未执行的验证标为“未验证（未运行）”。

完成后保留各文件的 `__main__`，方便手敲后的自测和后续验收。当前只实现产品确认；正文检索、融合重排和答案生成继续留在各自章节。
