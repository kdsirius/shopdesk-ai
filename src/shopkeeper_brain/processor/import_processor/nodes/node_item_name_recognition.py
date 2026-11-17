import json
import logging
from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pymilvus import MilvusClient, DataType

from shopkeeper_brain.core.llm_config import load_llm_config
from shopkeeper_brain.core.milvus_config import load_milvus_config
from shopkeeper_brain.processor.import_processor.BaseNode import BaseNode
from shopkeeper_brain.processor.import_processor.exceptions import StateFieldError, ConfigurationError, ValidationError, \
    ImportProcessError, MilvusError
from shopkeeper_brain.processor.import_processor.state import ImportGraphState, create_default_state
from shopkeeper_brain.utils.embedding_utils import generate_embeddings
from shopkeeper_brain.utils.milvus_utils import (
    escape_milvus_string,
    get_milvus_client,
    restore_sparse_vector
)

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
        dense_vector, sparse_vector = self._step_5_generate_vectors(item_name)
        state["item_name_dense_vector"] = dense_vector
        state["item_name_sparse_vector"] = sparse_vector
        self._step_6_save_to_milvus(file_title, item_name, dense_vector, sparse_vector, )
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

    def _step_5_generate_vectors(self, item_name: str) -> tuple[list[float], dict[int, float]]:
        """单独编码产品名称，供产品确认所需的名称数据使用。"""
        vectors = generate_embeddings([item_name])
        return vectors["dense"][0], vectors["sparse"][0]

    def _step_6_save_to_milvus(self, file_title: str, item_name: str, dense_vector: list[float],
                               sparse_vector: dict[int, float]) -> None:
        """按文件标题幂等保存一条主体名称记录。"""
        config = load_milvus_config()
        if not config.item_name_collection:
            raise ConfigurationError(
                "主体名称集合未配置，请检查 "
                "SHOPKEEPER_BRAIN_MILVUS_ITEM_NAME_COLLECTION",
                node_name=self.name,
            )
        if not isinstance(file_title, str) or not file_title.strip():
            raise StateFieldError(node_name=self.name, field_name="file_title", expected_type=str, )
        if not isinstance(item_name, str) or not item_name.strip():
            raise StateFieldError(node_name=self.name, field_name="item_name", expected_type=str, )
        if not isinstance(dense_vector, list) or len(dense_vector) != 1024:
            raise ValidationError(message="主体名称 Dense 向量必须是 1024 维列表", node_name=self.name, )

        restored_sparse = restore_sparse_vector(sparse_vector, "item_name_sparse_vector")
        try:
            client = get_milvus_client()
            if not client.has_collection(config.item_name_collection):
                self._create_item_name_collection(client, config.item_name_collection)
            safe_file_title = escape_milvus_string(file_title)
            client.delete(collection_name=config.item_name_collection, filter=f'file_title == "{safe_file_title}"')

            result = client.insert(
                collection_name=config.item_name_collection,
                data=[{
                    "file_title": file_title,
                    "item_name": item_name,
                    "dense_vector": dense_vector,
                    "sparse_vector": restored_sparse
                }]
            )
        except ImportProcessError:
            raise
        except Exception as exc:
            raise MilvusError(message="主体名称写入 Milvus 失败", node_name=self.name, cause=exc) from exc
        inserted_ids = result.get("ids", [])
        if result.get("insert_count") != 1 or len(inserted_ids) != 1:
            raise MilvusError(message="主体名称写入 Milvus 后返回的主键数量不正确", node_name=self.name)

    def _create_item_name_collection(self, client: MilvusClient, collection_name: str) -> None:
        """创建主体名称集合及 Dense/Sparse 两类索引。"""
        schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field(
            field_name="pk",
            datatype=DataType.INT64,
            is_primary=True,
            auto_id=True,
        )
        schema.add_field(
            field_name="file_title",
            datatype=DataType.VARCHAR,
            max_length=65535,
        )
        schema.add_field(
            field_name="item_name",
            datatype=DataType.VARCHAR,
            max_length=65535,
        )
        schema.add_field(
            field_name="dense_vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=1024,
        )
        schema.add_field(
            field_name="sparse_vector",
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        index_params.add_index(
            field_name="sparse_vector",
            index_name="sparse_vector_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
            params={
                "inverted_index_algo": "DAAT_MAXSCORE",
                "normalize": True,
                "quantization": "none",
            }
        )

        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params
        )


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
