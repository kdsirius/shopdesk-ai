import json
import logging
import math
from copy import deepcopy
from pathlib import Path

from app.processor.import_processor.BaseNode import BaseNode
from app.processor.import_processor.exceptions import StateFieldError
from app.processor.import_processor.state import ImportGraphState, create_default_state

from app.utils.embedding_utils import generate_embeddings

EMBEDDING_BATCH_SIZE = 3


class NodeBGEEmbedding(BaseNode):
    """把带主体标签的切片转换成供混合检索使用的双向量。"""
    name = "node_bge_embedding"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """全部批次成功后才把带向量的切片列表交回状态。"""
        chunks = self._step_1_validate_input(state)
        output_data = self._step_2_generate_embeddings(chunks)
        state["chunks"] = output_data
        self.logger.info("Chunk 双向量生成完成：%s 条", len(output_data))
        return state

    def _step_1_validate_input(self, state: ImportGraphState) -> list[dict[str, object]]:
        """检查主体与全部正文，在模型推理之前指出输入缺口。"""
        item_name = state.get("item_name")
        if not isinstance(item_name, str) or not item_name.strip():
            raise StateFieldError(node_name=self.name, field_name="item_name", expected_type=str)

        chunks = state.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise StateFieldError(node_name=self.name, field_name="chunks", expected_type=list)

        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                raise StateFieldError(node_name=self.name, field_name=f"chunks[{index}]", expected_type=dict)

            if chunk.get("item_name") != item_name:
                raise StateFieldError(node_name=self.name, field_name=f"chunks[{index}].item_name",
                                      message=f"第 {index + 1} 个 Chunk 的主体与状态不一致，请先完成主体回填")

            content = chunk.get("content")
            if not isinstance(content, str) or not content.strip():
                raise StateFieldError(node_name=self.name, field_name=f"chunks[{index}].content", expected_type=str)

        return chunks

    def _step_2_generate_embeddings(self, chunks: list[dict[str, object]]) -> list[dict[str, object]]:
        """按原顺序分批编码，保留每个切片原有的正文和来源。"""
        output_data: list[dict[str, object]] = []
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start:start + EMBEDDING_BATCH_SIZE]
            texts = [f"{chunk['item_name']}\n{chunk['content']}" for chunk in batch]
            vectors = generate_embeddings(texts)

            for index, chunk in enumerate(batch):
                item = chunk.copy()
                item["dense_vector"] = vectors["dense"][index]
                item["sparse_vector"] = vectors["sparse"][index]
                output_data.append(item)
            self.logger.info("已完成第 %s—%s 个 Chunk", start + 1, start + len(batch))

        return output_data


if __name__ == '__main__':
    from app.processor.import_processor.nodes.node_item_name_recognition import (
        NodeItemNameRecognition,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    # 直接复用第 5 节的真实产物，不重新解析 PDF、处理图片或切片。
    chunks_path = Path(
        r"E:\dev\python\project-study\shopkeeper-brain\workspace\day03-real-run\万用表RS-12的使用_5gatm6ph\extracted\chunks.json"
    )
    if not chunks_path.is_file():
        raise SystemExit(f"找不到真实切片文件：{chunks_path}")
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    if not isinstance(chunks, list) or not chunks:
        raise SystemExit("输入必须是第 5 节的非空 Chunk 列表")

    # 这是第 6 节已确认的真实名称，原 JSON 中没有这个字段。
    confirmed_item_name = "RS PRO RS-12 数字万用表"
    state = create_default_state(
        file_title=chunks[0]["file_title"],
        chunks=chunks,
    )
    recognition = NodeItemNameRecognition()
    recognition._step_4_update_chunks(state, chunks, confirmed_item_name)
    dense, sparse = recognition._step_5_generate_vectors(state["item_name"])
    state["item_name_dense_vector"] = dense
    state["item_name_sparse_vector"] = sparse
    original_chunks = deepcopy(state["chunks"])

    print("真实输入：", chunks_path)
    print("复用的主体名称：", state["item_name"])
    print("主体 Dense 维度：", len(dense))
    print("主体 Sparse 非零特征数：", len(sparse))
    result = NodeBGEEmbedding()(state)

    assert result is state
    assert len(dense) == 1024 and sparse
    assert len(result["chunks"]) == len(original_chunks)
    for before, after in zip(original_chunks, result["chunks"], strict=True):
        original_fields = {
            key: value
            for key, value in after.items()
            if key not in ("dense_vector", "sparse_vector")
        }
        assert original_fields == before
        vector = after["dense_vector"]
        weights = after["sparse_vector"]
        assert len(vector) == 1024 and all(math.isfinite(x) for x in vector)
        assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, abs_tol=1e-3)
        assert weights and all(
            isinstance(key, int) and key >= 0 and math.isfinite(value)
            for key, value in weights.items()
        )

    project_root = Path(__file__).resolve().parents[4]
    output_path = project_root / "workspace/day07-real-run/state_vector.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    first_chunk = result["chunks"][0]
    print("完成的 Chunk 数：", len(result["chunks"]))
    print("首块 Dense 前 5 项：", first_chunk["dense_vector"][:5])
    print("首块 Sparse 前 5 项：", list(first_chunk["sparse_vector"].items())[:5])
    print("主体与全部 Chunk 双向量、原字段保留：通过")
    print("新的状态备份：", output_path)
