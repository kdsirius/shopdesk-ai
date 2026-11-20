# 第 16 节：答案输出与项目收敛

> 上一节的查询页已经能看到检索进度。本节让它直接显示追问、拒答或依据手册生成的回答，刷新后还能读回这轮的正文和配图。对应资料见 [day16 答案节点流程](../../reference/掌教智库/4.视频/day16/答案节点流程梳理.md)和[当天代码](../../reference/掌教智库/4.视频/day16/knowledge_base.zip)。

## 一、业务流程与设计原因

### 1. 答案节点为什么有两种输入

问「RS-12 怎么测电压？」时，产品确认可能只找到候选商品。这时 `NodeItemNameConfirm` 已经把「您是想问以下哪个产品……」填到 `answer`，也已经用 `session_id` 保存了一条助手消息。问库里没有的商品时，拒答走同一条短路。两次写入会让刷新后的页面出现重复回复，所以 `NodeAnswerOutput` 读到已有 `answer` 就原样输出，流式模式下把整句作为一段增量发出。

用户接着给出完整型号后，确认节点把 `answer` 留空。三路检索经 RRF、Rerank 后，`reranked_docs` 留下按相关性排列的少量资料。资料里的 `content` 才是供模型作答的正文。`source`、`chunk_id`、`url`、`title` 和有值的 `score` 给正文标明出处。用确认过的商品名和 `rewritten_query` 把「怎么测」补成独立的问题，再附上近期对话，模型才能结合本轮手册和追问前的语境回答。

```mermaid
flowchart LR
    A["NodeItemNameConfirm"] -->|已有 answer| D["NodeAnswerOutput"]
    A -->|answer 为空| B["三路检索与 NodeRrf"]
    B --> C["NodeRerank → reranked_docs"]
    C --> D
    D -->|生成后写入一条助手消息| M["MongoDB chat_message"]
    D -->|custom 与 updates| S["run_query"]
    S -->|progress / delta / complete| P["chat.html"]
    M -->|GET /history/{session_id}| P
```

图从产品确认开始。上方直接把已有 `answer` 交给输出节点，下方先找到手册材料，再生成并写入助手答复。输出节点把生成中的正文交给 `run_query`，浏览器可边收边显示。刷新页面时，浏览器用原来的 `session_id` 重新读取 MongoDB。

### 2. 参考资料和图片怎样进入答案

先按重排顺序放完整的资料段，再用剩余空间放历史。课堂给这两部分分配 12,000 个字符，`len()` 还要算上拼接时的换行符。商品名、问题和模板文字另行填入，所以这个数是资料与历史的字符预算。如果没有任何资料可用，节点给出资料不足的提示。资料有内容但无法支持某个细节时，提示词要求模型说明缺少依据。

查「交流电压怎么测」时，可能有一段正文带有手册里的插图。遍历实际纳入提示词的资料，从本地 Chunk 的 Markdown 图片语法取链接；联网结果的 URL 路径有图片后缀时才列为配图，是否能加载由浏览器验证。这个 `image_urls` 列表随答案存入历史，页面实时显示和刷新显示用同一批链接。模型专注回答问题，配图由程序根据资料确定。

### 3. 正文怎样进入第 15 节的 SSE

第 15 节的 `updates` 在节点完成后才给服务一个状态更新。如果只读这类事件，浏览器得等完整个模型调用才看到字。答案节点用 LangGraph 的 `custom` 通道在生成过程中发送 `delta`，服务继续把 `updates` 转成 `progress`。每次成功的运行在历史写完后发一次 `complete`，带上完整的 `answer`、`image_urls` 和重排条数。课堂里 `final` 提供最后一包正文和图片，这个职责在本工程由已有的 `complete` 承担。

`session_id` 对应一段来回问答，`run_id` 对应一次提问的 SSE 队列。如果模型途中报错，已经显示的增量只是临时内容。查询服务走 `task_error`，页面关闭本次流，历史里不会把半截正文当成完整回复。

## 二、手敲步骤

### 1. 补答案状态和历史字段

最终结果需要同时送到查询服务和 MongoDB。在 [state.py](../../src/shopkeeper_brain/processor/query_processor/state.py) 的 `QueryGraphState` 中，紧跟 `answer: str` 增加一行，保留现有的 `is_stream`。

```python
    image_urls: list[str]
```

在 [mongo_history_utils.py](../../src/shopkeeper_brain/utils/mongo_history_utils.py) 中，给 `save_chat_message()` 的 `message_id` 参数后面追加一个可选参数。

```python
        image_urls: list[str] | None = None,
```

同一个函数里，找到 `document = {...}`，在字典结束后、`if message_id:` 之前增加这两行。

```python
    if image_urls is not None:
        document["image_urls"] = image_urls
```

用户消息的旧调用可以继续省略这个参数。新答案用 `[]` 表示这轮没有配图，旧记录也可能没有这个键。当前历史 API 已经把记录字段随 JSON 返回，新增字段可以直接读到。[历史路由](../../src/shopkeeper_brain/api/business.py#L84)

### 2. 实现 `NodeAnswerOutput`

当前 [node_answer_output.py](../../src/shopkeeper_brain/processor/query_processor/nodes/node_answer_output.py) 只有占位类，用下面的完整文件替换它。节点检查已有答案之后才准备模型。新的答案生成完才调用 `save_chat_message()`，让成功结束时拿到的正文和存下来的正文一致。

**文件**：`src/shopkeeper_brain/processor/query_processor/nodes/node_answer_output.py`

```python
import re

from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer

from shopkeeper_brain.core.llm_config import load_llm_config
from shopkeeper_brain.processor.import_processor.exceptions import ConfigurationError
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState
from shopkeeper_brain.utils.mongo_history_utils import save_chat_message

MAX_CONTEXT_CHARS = 12_000
MARKDOWN_IMAGE = re.compile(r"!\[[^\]\n]*\]\((https?://(?:[^()\s]|\([^()\s]*\))+)\)")
IMAGE_SUFFIX = re.compile(r"\.(?:png|jpe?g|gif|webp|bmp|svg)$", re.IGNORECASE)

ANSWER_PROMPT = """你是产品手册助手。根据参考资料回答用户的问题。
资料不足以支持的步骤或参数，请明确说明无法从现有资料确认。
引用说明时标出对应的资料编号。

【参考资料】
{context}

【历史对话】
{history}

【确认商品】
{item_names}

【用户问题】
{question}
"""


class NodeAnswerOutput(NodeBase):
    """输出已有回复，或用重排文档生成并保存一条新回复。"""

    name = "node_answer_output"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        write = get_stream_writer() if state.get("is_stream") else None
        existing = state.get("answer")
        if existing:
            if write is not None:
                write({"delta": existing})
            return {"answer": existing, "image_urls": []}

        prompt, included_docs = self._build_prompt(state)
        if included_docs:
            config = load_llm_config()
            if not all((config.base_url, config.api_key, config.model)):
                raise ConfigurationError("答案生成的文本模型配置不完整", node_name=self.name)
            model = ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=config.temperature,
                extra_body={"enable_thinking": False},
            )
            if write is None:
                answer = model.invoke(prompt).text
            else:
                parts = []
                for chunk in model.stream(prompt):
                    delta = chunk.text
                    if delta:
                        parts.append(delta)
                        write({"delta": delta})
                answer = "".join(parts)
            if not answer.strip():
                raise ValueError("文本模型没有返回答案正文")
        else:
            answer = "目前没有足够的参考资料回答这个问题。"
            if write is not None:
                write({"delta": answer})

        image_urls = self._extract_image_urls(included_docs)
        save_chat_message(
            session_id=state["session_id"],
            role="assistant",
            text=answer,
            item_names=state.get("item_names"),
            image_urls=image_urls,
        )
        return {"prompt": prompt, "answer": answer, "image_urls": image_urls}

    @staticmethod
    def _build_prompt(state: QueryGraphState) -> tuple[str, list[dict]]:
        remaining = MAX_CONTEXT_CHARS
        entries = []
        included_docs = []
        for index, doc in enumerate(state.get("reranked_docs") or [], start=1):
            content = (doc.get("content") or "").strip()
            if not content:
                continue
            tags = [f"[{index}]"]
            for field in ("source", "chunk_id", "url", "title"):
                value = doc.get(field)
                if value is not None and value != "":
                    tags.append(f"[{field}={value}]")
            score = doc.get("score")
            if score is not None:
                tags.append(f"[score={score:.4f}]")
            entry = " ".join(tags) + "\n" + content
            size = len(entry) + (2 if entries else 0)
            if size > remaining:
                break
            entries.append(entry)
            included_docs.append(doc)
            remaining -= size

        labels = {"user": "用户", "assistant": "助手"}
        history_lines = []
        for message in state.get("history") or []:
            label = labels.get(message.get("role"))
            text = message.get("text")
            if not label or not text:
                continue
            line = f"{label}：{text}"
            size = len(line) + (1 if history_lines else 0)
            if size > remaining:
                break
            history_lines.append(line)
            remaining -= size

        prompt = ANSWER_PROMPT.format(
            context="\n\n".join(entries) or "无参考资料",
            history="\n".join(history_lines) or "暂无历史对话",
            item_names="、".join(state.get("item_names") or []) or "无指定商品",
            question=state.get("rewritten_query") or state.get("original_query", ""),
        )
        return prompt, included_docs

    @staticmethod
    def _extract_image_urls(docs: list[dict]) -> list[str]:
        images = []
        for doc in docs:
            if doc.get("source") == "local":
                images.extend(MARKDOWN_IMAGE.findall(doc["content"]))
            elif doc.get("source") == "web":
                url = (doc.get("url") or "").strip()
                if url.startswith(("http://", "https://")) and IMAGE_SUFFIX.search(re.split(r"[?#]", url, maxsplit=1)[0]):
                    images.append(url)
        return list(dict.fromkeys(images))


if __name__ == "__main__":
    import json
    import logging
    from pathlib import Path
    from uuid import uuid4

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    docs_path = Path("workspace/day16-reranked-docs.json")
    state = {
        "session_id": str(uuid4()),
        "original_query": "怎么测量交流电压？",
        "rewritten_query": "RS PRO RS-12 数字万用表怎么测量交流电压？",
        "item_names": ["RS PRO RS-12 数字万用表"],
        "reranked_docs": json.loads(docs_path.read_text(encoding="utf-8")),
    }
    result = NodeAnswerOutput()(state)
    print("会话", state["session_id"])
    print(result["answer"])
    print("配图", result["image_urls"])
```

`write` 是取当前图运行的推送函数。Web 路径调用 `.stream()`，从每个 `chunk.text` 拿到正文片段。空片段略过，有内容的片段保留原空格和换行；最后 `join()` 的结果就是这一轮发出的所有文字。IDE 同步路径直接从 `invoke()` 的消息对象读取 `.text`。两种方式都沿用已有查询节点的文本模型配置和关闭思考输出参数，IDE 调试时可以在 `save_chat_message()` 前查看完整的 `answer`。

`_build_prompt()` 同时返回提示词和 `included_docs`。后者记录实际纳入的资料，截断在预算外的段落不会混入配图。`score is not None` 保留有效的 `0.0`，也能处理重排降级时的空分数。对于图片，`findall()` 只返回括号里的 URL，`dict.fromkeys()` 按出现顺序去重。

### 3. 把节点更新和正文增量接到查询服务

在 [main_graph.py](../../src/shopkeeper_brain/processor/query_processor/main_graph.py) 中，替换 `KBQueryWorkflow.stream()`。`run()` 和已有的图连线可以直接使用。

```python
    def stream(self, initial_state: QueryGraphState):
        """给后台任务读取完成节点的更新和生成中的文本增量。"""
        return self.compile().stream(initial_state, stream_mode=["updates", "custom"], version="v2")
```

开启两个模式后，`part["type"]` 告诉服务该怎么解释 `part["data"]`。`updates` 的数据仍按节点名组织，`custom` 的数据是答案节点交出的 `{"delta": ...}`。

同一个文件的导入区加上 `from uuid import uuid4`，删掉旧演示专用的 `clear_history` 导入。把文件末尾的 `__main__` 替换为下面的三轮演示，便于在 IDE 对照 `final_state` 和历史。

```python
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    session_id = str(uuid4())
    cases = [
        (session_id, "RS-12 怎么测电压？"),
        (session_id, "是 RS PRO RS-12 数字万用表，怎么测交流电压？"),
        (str(uuid4()), "iPhone 15 怎么充电？"),
    ]
    workflow = KBQueryWorkflow()
    for current_session, query in cases:
        final_state = workflow.run({"session_id": current_session, "original_query": query})
        print("会话", current_session, "问题", query)
        print("确认商品", final_state["item_names"])
        print(final_state["answer"])
        print("重排条数", len(final_state.get("reranked_docs") or []))
        print("配图", final_state["image_urls"])
```

在 [query_service.py](../../src/shopkeeper_brain/services/query_service.py) 替换 `run_query()`。它把正文增量交给 API 提供的 `publish()`，工作流全部完成后再发一次终态。

```python
def run_query(session_id: str, question: str, publish: Callable[[str, dict], None]) -> None:
    state = {"session_id": session_id, "original_query": question, "is_stream": True}
    reranked_count = None
    answer_result = {}

    try:
        for part in KBQueryWorkflow().stream(state):
            if part["type"] == "custom":
                publish("delta", part["data"])
                continue

            for node, changes in part["data"].items():
                publish("progress", {"node": node})
                if node == "node_rerank":
                    reranked_count = len(changes["reranked_docs"])
                elif node == "node_answer_output":
                    answer_result = changes

        publish("complete", {
            "answer": answer_result["answer"],
            "image_urls": answer_result["image_urls"],
            "reranked_count": reranked_count,
        })
    except Exception:
        logger.exception("查询失败，session_id=%s", session_id)
        publish("task_error", {"message": "查询失败，请查看服务端日志。"})
```

原有 [business.py](../../src/shopkeeper_brain/api/business.py#L54) 已经把任意事件名和数据放进 `run_id` 对应的队列，碰到 `complete` 或 `task_error` 才结束，所以 API 接线继续使用这一份实现。答案节点的 `progress` 在返回状态后出现，这时浏览器可能已经收到了正文增量。

### 4. 在查询页显示本轮答案和历史配图

打开 [chat.html](../../src/shopkeeper_brain/front/chat.html)。在 `id="query-progress"` 的 `<pre>` 后面、会话历史标题之前加上结果的位置。

```html
    <h2>本轮回答</h2>
    <pre id="answer" style="white-space: pre-wrap;"></pre>
    <div id="answer-images"></div>
```

在脚本中取得 `progress` 元素的那行后面追加两个变量。在 `sessionStorage.setItem(...)` 后、`loadHistory()` 前追加 `renderImages()`。

```javascript
        const answer = document.getElementById("answer");
        const answerImages = document.getElementById("answer-images");
```

```javascript
        function renderImages(container, urls) {
            container.replaceChildren(...(urls ?? []).map(url => {
                const image = document.createElement("img");
                image.src = url;
                image.alt = "参考图片";
                image.style.maxWidth = "min(100%, 360px)";
                return image;
            }));
        }
```

在 `loadHistory()` 的 `items.map(...)` 中，找到 `return line;`，在它之前追加下方代码。旧历史没有 `image_urls` 时，`renderImages()` 用空列表处理。

```javascript
                    const images = document.createElement("div");
                    renderImages(images, item.image_urls);
                    line.append(images);
```

在表单提交事件中，找到 `button.disabled = true;`，紧跟着清空上一轮的正文和图片。保留后面的进度初始化和请求代码。

```javascript
            answer.textContent = "";
            answerImages.replaceChildren();
```

在同一个提交事件中，把原来的 `complete`、`task_error` 和 `source.onerror` 段替换成下面的四个处理器。其前面的 `progress` 保留。

```javascript
                source.addEventListener("delta", (event) => {
                    answer.textContent += JSON.parse(event.data).delta;
                });
                source.addEventListener("complete", (event) => {
                    const result = JSON.parse(event.data);
                    answer.textContent = result.answer;
                    renderImages(answerImages, result.image_urls);
                    const detail = result.reranked_count === null
                        ? "未进入检索分支"
                        : `重排保留 ${result.reranked_count} 条资料`;
                    finish(`查询完成，${detail}。`);
                });
                source.addEventListener("task_error", (event) => {
                    answer.textContent = "";
                    finish(JSON.parse(event.data).message);
                });
                source.onerror = () => {
                    answer.textContent = "";
                    finish("进度连接中断。");
                };
```

`delta` 只追加新文字，`complete` 用服务端最终正文替换当前内容，再挂载图片。沿用 `finish()` 关闭 `EventSource`、刷新历史、恢复发送按钮。正文通过 `textContent` 显示，图片则用独立的 `<img>` 元素。

## 三、必做真实验证

下列操作按你的 IDE 和本地环境执行前，状态均为 **未验证（未运行）**。

### 1. 用真实重排资料单独运行答案节点

1. 在 PyCharm 选择本工程 uv 解释器，把运行配置的工作目录设为仓库根目录。确认本地 BGE-M3、文本模型、Tavily 和百炼配置可用，Milvus 选择已有真实 RS-12 资料的集合。给 `SHOPKEEPER_BRAIN_MONGO_DB_NAME` 指定本节专用的实验库，例如 `study_d16_history`。各次验证产生的用户与助手记录都写入该库。
2. 打开 [node_rerank.py](../../src/shopkeeper_brain/processor/query_processor/nodes/node_rerank.py#L105)，在学习期入口的 `result = NodeRerank()(state)` 下一行打断点，点击 Debug。停住后看看 `result["reranked_docs"]`，确认能找到交流电压测量的手册内容，也能看到有值的重排分数。在 PyCharm 的 Evaluate Expression 切换到代码片段模式，执行下面三行把真实结果保存到练习文件。

   ```python
   import json
   from pathlib import Path
   Path("workspace/day16-reranked-docs.json").write_text(json.dumps(result["reranked_docs"], ensure_ascii=False), encoding="utf-8")
   ```

3. 打开 [node_answer_output.py](../../src/shopkeeper_brain/processor/query_processor/nodes/node_answer_output.py)，在 `prompt, included_docs = self._build_prompt(state)` 下一行和 `save_chat_message()` 处打断点，点击 Debug。核对第一处的 `prompt` 包含确认商品、改写后的问题及按原顺序排列的资料。第二处的 `answer` 应能指出手册里的档位和表笔插孔。在这个问题中可对照真实手册的「交流电压测量」切片。
4. 在 MongoDB 客户端打开实验库的 `chat_message`，按控制台的 `session_id` 查找。这次单跑答案节点会新增一条助手消息，`text` 和 `image_urls` 应分别等于返回值里的 `answer` 和 `image_urls`。若模型返回了文字但没有手册依据，看 `included_docs` 是否选入了正确段落。若有答案却无法写入，核对实验库名与 `save_chat_message()` 的异常位置。

### 2. 用查询主图走完追问、确认和拒答

1. 打开 [main_graph.py](../../src/shopkeeper_brain/processor/query_processor/main_graph.py)，直接运行学习期入口。前两轮用同一个会话，最后一轮用另一个新会话。控制台应分别出现候选追问、基于 RS-12 手册的回答、找不到相关产品的拒答。
2. 看日志与 `final_state`。追问和拒答应在产品确认后直达答案节点，助手正文与早先的 `answer` 一致。完整型号问题应该执行三路检索、RRF 和 Rerank，最后的状态里有非空答案。若短型号这轮进入检索或拒答，先 Debug 产品确认的评分和候选项，使用实际只达到候选阈值的称呼再次验证；可以尝试「万用表怎么测电压？」。重排异常降级时可以核对本地 `score=None` 的资料仍被正常消费，真实重排成功要另看打分日志。
3. 在 MongoDB 按两个会话分别查看，预期一段会话有两轮、另一段有一轮。检查每轮都按「用户 → 助手」出现，追问与拒答各保存一次。若出现连续两条相同的助手回复，检查已有 `answer` 的分支是否在生成和保存前就返回。

### 3. 在浏览器核对 SSE、图片和刷新后的历史

1. 在 PyCharm 运行 [api/main.py](../../src/shopkeeper_brain/api/main.py) 的 `__main__`，通过状态页进入「查询手册」。打开浏览器开发者工具的 Network 面板，提问「RS PRO RS-12 数字万用表怎么测交流电压，表笔插在哪里？」。
2. 点开 `/stream/{run_id}` 的 EventStream。先观察检索节点的 `progress`，再观察答案正文的 `delta` 逐段到达，最后应有一次 `complete`。把增量拼起来应等于 `complete.answer`。页面显示最后的重排条数，连接关闭，发送按钮恢复。如果只在最后看到全文，沿 `chunk.text`、`custom`、`publish("delta", ...)` 依次检查。
3. 展开 `complete` 中的 `image_urls`，与实际纳入的手册切片对照，确认链接去重、浏览器能加载。若问题没有取回带图的切片，可直接问 RS-12「控制与端口分别在哪里？」并观察对应切片。刷新原标签，通过 `/history/{session_id}` 和 MongoDB 对照最后一条助手的正文与图片，确保两次页面显示来自同一条历史。看到最终图片但刷新后消失时，先看历史响应里有没有 `image_urls`，再查页面 `loadHistory()`。
4. 在原标签再发送一轮，确认 `session_id` 一致、`run_id` 更新。另开独立标签问库里没有的 iPhone，确认拒答也会作为正文显示，刷新后只读回自己的历史。最后从状态页打开「导入手册」，确认原业务入口可访问。

退出条件是同步入口能用手册资料回答，整图的追问和拒答各只有一条助手记录，Web 正文从增量到历史能逐字对上，资料配图能随历史读回。缺少所需服务或没有选中含图资料时，对应项记为跳过或未运行。已经执行但正文、配图或历史对不上时，按该项失败处理。
