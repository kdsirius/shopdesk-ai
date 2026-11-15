import json
import logging
from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from shopkeeper_brain.core.llm_config import load_llm_config
from shopkeeper_brain.processor.import_process.BaseNode import BaseNode
from shopkeeper_brain.processor.import_process.exceptions import StateFieldError
from shopkeeper_brain.processor.import_process.state import ImportGraphState, create_default_state

ITEM_NAME_CHUNK_K = 3
ITEM_NAME_CONTEXT_MAX_CHARS = 2500



class NodeItemNameRecognition(BaseNode):
    """识别整份文档的产品主体，让所有 Chunk 带上同一主体标签。"""
    name = "node_item_name_recognition"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """读取标题和切片，确定主体名称后统一回填；返回原状态对象。"""
        file_title, chunks = self._step_1_get_inputs(state)
        context = self._step_2_build_context(chunks)
        item_name = self._step_3_call_llm(file_title, context)
        self._step_4_update_chunks(state, chunks, item_name)
        self.logger.info("主体字段处理完成：%s", item_name)
        return state

    def _step_1_get_inputs(self, state: ImportGraphState) -> tuple[str, list[dict[str, object]]]:
        """检查文件标题和非空切片列表，缺少上游数据时终止节点。"""

        file_title = state.get('file_title')
        if not isinstance(file_title, str) or not file_title.strip():
            raise StateFieldError(node_name=self.name, field_name='file_title', expected_type=str)

        chunks = state.get('chunks')
        if not isinstance(chunks, list) or not chunks:
            raise StateFieldError(node_name=self.name, field_name='chunks', expected_type=list)

        return file_title, chunks

    def _step_2_build_context(self, chunks: list[dict[str, object]]) -> str:
        """读取文档前部作为识别材料，不修改传入的切片。"""
        parts: list[str] = []
        total_chars = 0

        for index, chunk in enumerate(chunks[:ITEM_NAME_CHUNK_K], start=1):
            title_value = chunk.get("title", "")
            content_value = chunk.get("content", "")
            title = title_value.strip() if isinstance(title_value, str) else ""
            content = content_value.strip() if isinstance(content_value, str) else ""

            piece = f"【切片{index}】\n标题：{title}\n内容：{content}"
            parts.append(piece)
            total_chars += len(piece)

            if total_chars >= ITEM_NAME_CONTEXT_MAX_CHARS:
                break

        # join 还会增加分隔换行，最终截断才能守住字符上限。
        context = "\n\n".join(parts)
        return context[:ITEM_NAME_CONTEXT_MAX_CHARS]

    def _step_3_call_llm(self, file_title: str, context: str) -> str:
        """返回模型识别名称；没有可用结果时以文件标题兜底。"""
        if not context:
            self.logger.warning("识别上下文为空，使用文件标题兜底")
            return file_title
        config = load_llm_config()
        if not all((config.base_url, config.api_key, config.model)):
            self.logger.warning("文本模型配置不完整，使用文件标题兜底")
            return file_title

        prompt = f"""请从以下信息中识别文档的商品名称或产品主体：
        文件名：{file_title}

        文档前部切片：
        {context}

        要求：
        1. 优先返回包含品牌、型号和名称的完整主体名称；
        2. 只返回主体名称，不要解释识别过程；
        3. 如果无法识别，返回空字符串。
        """

        try:
            model = ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=config.temperature,
                extra_body={"enable_thinking": False},
            )
            response = model.invoke([
                SystemMessage(content="你是商品主体识别专家，只输出主体名称。"),
                HumanMessage(content=prompt)
            ])
            item_name = response.text.strip()
            if not item_name:
                self.logger.warning("文本模型返回空内容，使用文件标题兜底")
                return file_title
            self.logger.info("文本模型返回主体名称：%s", item_name)
            return item_name
        except Exception as exc:
            self.logger.warning("文本模型调用失败，使用文件标题兜底：%s", type(exc).__name__)
            return file_title

    def _step_4_update_chunks(self, state: ImportGraphState, chunks: list[dict[str, object]], item_name: str) -> None:
        """给原状态及全部切片补充主体字段，不改变原切片正文。"""
        state["item_name"] = item_name
        for chunk in chunks:
            chunk["item_name"] = item_name
        state["chunks"] = chunks


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    # 改成第 5 节已经生成的真实 JSON，直接在 IDE 运行本文件。
    chunks_path = Path(
        r"E:\dev\python\project-study\shopkeeper-brain\workspace\day03-real-run\万用表RS-12的使用_5gatm6ph\extracted\chunks.json"
    )
    if not chunks_path.is_file():
        raise SystemExit(f"请先确认上一节的真实切片文件：{chunks_path}")

    chunks = json.loads(chunks_path.read_text(encoding='utf-8'))
    if not isinstance(chunks, list) or not chunks:
        raise SystemExit("chunks.json 必须是上一节生成的非空切片列表")

    state = create_default_state(
        file_title=chunks[0]['file_title'],
        chunks=chunks
    )

    original_contents = [chunk['content'] for chunk in chunks]
    node = NodeItemNameRecognition()
    context = node._step_2_build_context(chunks)
    assert 0 < len(context) <= ITEM_NAME_CONTEXT_MAX_CHARS
    print("输入切片文件：", chunks_path)
    print("文件标题：", state["file_title"])
    print("切片总数：", len(chunks))
    print("识别上下文字符数：", len(context))
    print("识别上下文预览：", context[:300])
    result = node(state)

    assert result is state
    assert result["item_name"]
    assert all(
        chunk.get("item_name") == result["item_name"]
        for chunk in result["chunks"]
    )
    assert [chunk["content"] for chunk in result["chunks"]] == original_contents
