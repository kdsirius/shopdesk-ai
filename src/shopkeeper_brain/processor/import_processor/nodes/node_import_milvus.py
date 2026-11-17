import json
import logging
import math
from pathlib import Path

from pymilvus import MilvusClient, DataType

from shopkeeper_brain.core.milvus_config import MilvusConfig, load_milvus_config
from shopkeeper_brain.processor.import_processor.BaseNode import BaseNode
from shopkeeper_brain.processor.import_processor.exceptions import StateFieldError, ValidationError, ConfigurationError, \
    ImportProcessError, MilvusError
from shopkeeper_brain.processor.import_processor.nodes.node_item_name_recognition import NodeItemNameRecognition
from shopkeeper_brain.processor.import_processor.state import ImportGraphState
from shopkeeper_brain.utils.milvus_utils import restore_sparse_vector, get_milvus_client, escape_milvus_string

DENSE_VECTOR_DIM = 1024
VARCHAR_MAX_LENGTH = 65535


class NodeImportMilvus(BaseNode):
    """把带双向量的 Chunk 幂等写入 Milvus。"""
    name = "node_import_milvus"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """校验、清理、批量插入，并在成功后回填 Chunk 主键。"""
        file_title, chunks = self._step_1_validate_input(state)
        config = load_milvus_config()
        client = self._step_2_prepare_collection(config)
        self._step_3_clean_old_data(client, config, file_title)
        updated_chunks = self._step_4_insert_data(client, config, chunks)
        state["chunks"] = updated_chunks
        self.logger.info("Chunk 入库完成：%s 条", len(updated_chunks))
        return state

    def _step_1_validate_input(self, state: ImportGraphState) -> tuple[str, list[dict[str, object]]]:
        """校验全部 Chunk，并创建不会污染原状态的待插入副本。"""
        file_title = state.get("file_title")
        if not isinstance(file_title, str) or not file_title.strip():
            raise StateFieldError(node_name=self.name, field_name="file_title", expected_type=str)

        item_name = state.get("item_name")
        if not isinstance(item_name, str) or not item_name.strip():
            raise StateFieldError(node_name=self.name, field_name="item_name", expected_type=str)

        chunks = state.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise StateFieldError(node_name=self.name, field_name="chunks", expected_type=list)

        normalized_chunks: list[dict[str, object]] = []
        for index, chunk in enumerate(chunks):
            field_prefix = f"chunks[{index}]"
            if not isinstance(chunk, dict):
                raise ValidationError(message=f"{field_prefix} 必须是字典", node_name=self.name)
            if chunk.get("file_title") != file_title:
                raise ValidationError(message=f"{field_prefix}.file_title 与状态不一致", node_name=self.name)
            if chunk.get("item_name") != item_name:
                raise ValidationError(message=f"{field_prefix}.item_name 与状态不一致", node_name=self.name)

            content = chunk.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValidationError(message=f"{field_prefix}.content 必须是非空文本", node_name=self.name)

            for field_name in ("title", "parent_title"):
                if not isinstance(chunk.get(field_name, ""), str):
                    raise ValidationError(message=f"{field_prefix}.{field_name} 必须是文本", node_name=self.name)

            dense_vector = chunk.get("dense_vector")
            if (
                    not isinstance(dense_vector, list)
                    or len(dense_vector) != DENSE_VECTOR_DIM
                    or any(isinstance(value, bool)
                           or not isinstance(value, (int, float))
                           or not math.isfinite(float(value))
                           for value in dense_vector)):
                raise ValidationError(
                    message=(f"{field_prefix}.dense_vector 必须是有限数值组成的 {DENSE_VECTOR_DIM} 维列表"),
                    node_name=self.name)

            sparse_vector = restore_sparse_vector(
                chunk.get("sparse_vector"),
                f"{field_prefix}.sparse_vector",
            )
            normalized_chunk = chunk.copy()
            normalized_chunk["dense_vector"] = [
                float(value) for value in dense_vector
            ]
            normalized_chunk["sparse_vector"] = sparse_vector
            normalized_chunk["part"] = 0
            normalized_chunks.append(normalized_chunk)

        return file_title, normalized_chunks

    def _step_2_prepare_collection(self, config: MilvusConfig) -> MilvusClient:
        """连接 Milvus，并在缺少 Chunk 集合时创建它。"""
        if not config.chunk_collection:
            raise ConfigurationError(
                "Chunk 集合未配置，请检查 SHOPKEEPER_BRAIN_MILVUS_CHUNK_COLLECTION",
                node_name=self.name
            )

        try:
            client = get_milvus_client()
            if not client.has_collection(config.chunk_collection):
                self._create_chunk_collection(client, config.chunk_collection)
        except ImportProcessError:
            raise
        except Exception as exc:
            raise MilvusError(message="Chunk 集合准备失败", node_name=self.name, cause=exc) from exc
        return client

    def _create_chunk_collection(self, client, collection_name: str) -> None:
        """创建 Chunk 字段和 Dense/Sparse 索引。"""
        schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
        schema.add_field(
            field_name="chunk_id",
            datatype=DataType.INT64,
            is_primary=True,
            auto_id=True,
        )
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=VARCHAR_MAX_LENGTH,
        )
        schema.add_field(
            field_name="title",
            datatype=DataType.VARCHAR,
            max_length=VARCHAR_MAX_LENGTH,
        )
        schema.add_field(
            field_name="parent_title",
            datatype=DataType.VARCHAR,
            max_length=VARCHAR_MAX_LENGTH,
        )
        schema.add_field(
            field_name="part",
            datatype=DataType.INT8,
        )
        schema.add_field(
            field_name="file_title",
            datatype=DataType.VARCHAR,
            max_length=VARCHAR_MAX_LENGTH,
        )
        schema.add_field(
            field_name="item_name",
            datatype=DataType.VARCHAR,
            max_length=VARCHAR_MAX_LENGTH,
        )
        schema.add_field(
            field_name="dense_vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=DENSE_VECTOR_DIM,
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
            index_name="sparse_inverted_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="IP",
            params={
                "inverted_index_algo": "DAAT_MAXSCORE",
                "normalize": True,
                "quantization": "none",
            },
        )
        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )

    def _step_3_clean_old_data(self, client, config: MilvusConfig, file_title: str, ) -> None:
        """只删除当前文档的旧 Chunk，保留其他文档。"""
        safe_file_title = escape_milvus_string(file_title)
        try:
            client.delete(collection_name=config.chunk_collection, filter=f'file_title == "{safe_file_title}"')
        except Exception as exc:
            raise MilvusError(message="Chunk 旧数据清理失败", node_name=self.name, cause=exc) from exc

    def _step_4_insert_data(self, client, config: MilvusConfig, chunks: list[dict[str, object]]) \
            -> list[dict[str, object]]:
        """映射 Schema、批量插入，并按返回顺序回填自增主键。"""
        data_to_insert = [
            {
                "content": chunk["content"],
                "title": chunk.get("title", ""),
                "parent_title": chunk.get("parent_title", ""),
                "part": chunk["part"],
                "file_title": chunk["file_title"],
                "item_name": chunk["item_name"],
                "dense_vector": chunk["dense_vector"],
                "sparse_vector": chunk["sparse_vector"],
            }
            for chunk in chunks
        ]

        try:
            result = client.insert(collection_name=config.chunk_collection, data=data_to_insert, )
        except Exception as exc:
            raise MilvusError(message="Chunk 批量写入 Milvus 失败", node_name=self.name, cause=exc, ) from exc

        inserted_ids = result.get("ids", [])
        if result.get("insert_count") != len(chunks) or len(inserted_ids) != len(chunks):
            raise MilvusError(
                message="Chunk 写入成功响应中的数量不正确：" f"期望 {len(chunks)}，实际 {len(inserted_ids)}",
                node_name=self.name
            )

        updated_chunks: list[dict[str, object]] = []
        for chunk, inserted_id in zip(chunks, inserted_ids, strict=True):
            updated_chunk = chunk.copy()
            updated_chunk["chunk_id"] = int(inserted_id)
            updated_chunks.append(updated_chunk)
        return updated_chunks


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    project_root = Path(__file__).resolve().parents[5]
    state_path = project_root / "workspace/day07-real-run/state_vector.json"
    if not state_path.is_file():
        raise SystemExit(f"找不到第 7 节真实状态备份：{state_path}")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not state.get("chunks"):
        raise SystemExit("state_vector.json 必须是带非空 chunks 的状态对象")

    item_node = NodeItemNameRecognition()
    item_node._step_6_save_to_milvus(
        state["file_title"],
        state["item_name"],
        state["item_name_dense_vector"],
        state["item_name_sparse_vector"],
    )
    result = NodeImportMilvus()(state)

    config = load_milvus_config()
    client = get_milvus_client()
    client.flush(collection_name=config.item_name_collection)
    client.flush(collection_name=config.chunk_collection)
    safe_file_title = escape_milvus_string(result["file_title"])
    item_rows = client.query(
        collection_name=config.item_name_collection,
        filter=f'file_title == "{safe_file_title}"',
        output_fields=["pk", "file_title", "item_name"],
    )
    chunk_rows = client.query(
        collection_name=config.chunk_collection,
        filter=f'file_title == "{safe_file_title}"',
        output_fields=["chunk_id", "file_title", "item_name", "part"],
    )

    assert len(item_rows) == 1
    assert len(chunk_rows) == len(result["chunks"]) == 21
    assert all(
        chunk.get("chunk_id") is not None
        for chunk in result["chunks"]
    )
    assert all(
        isinstance(key, int)
        for key in result["chunks"][0]["sparse_vector"]
    )

    print("主体集合当前文档记录数：", len(item_rows))
    print("Chunk 集合当前文档记录数：", len(chunk_rows))
    print("Chunk 主键回填数：", len(result["chunks"]))
    print("主体与 Chunk 真实入库：通过")
