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
                if url.startswith(("http://", "https://")) and IMAGE_SUFFIX.search(
                        re.split(r"[?#]", url, maxsplit=1)[0]):
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
