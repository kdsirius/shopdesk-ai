import logging

from app.processor.query_processor.base import NodeBase
from app.processor.query_processor.state import QueryGraphState

# 平滑常数：k 越大，名次靠前的优势越小；60 是 RRF 的通用取值。
RRF_K = 60
# 参与融合的检索路和权重。联网搜索不参与：它没有 chunk_id，交给后面的重排处理。
ROUTE_WEIGHTS = (
    ("embedding_chunks", 1.0),
    ("hyde_embedding_chunks", 1.0),
)


class NodeRrf(NodeBase):
    """把向量检索和 HyDE 两路的结果按名次融合成一份排序（Reciprocal Rank Fusion）。"""

    name = "node_rrf"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """读取 embedding_chunks、hyde_embedding_chunks；只返回 rrf_chunks。
              某一路字段缺失或为空，视为这一路没有结果，不报错。"""
        routes = [
            (self._step_1_extract_entities(state.get(field)), weight)
            for field, weight in ROUTE_WEIGHTS
        ]
        merged = self._step_2_rrf_merge(routes)
        for entity, score in merged:
            self.logger.info("步骤 2：chunk_id=%s RRF 得分 %.6f", entity["chunk_id"], score)

        self.logger.info("步骤 2：融合得到 %d 个 Chunk", len(merged))

        return {"rrf_chunks": [entity for entity, _ in merged]}

    @staticmethod
    def _step_1_extract_entities(hits: list[dict] | None) -> list[dict]:
        """检索结果每项是 {chunk_id, distance, entity}；融合只看名次，所以只取出 entity。"""
        entities = []
        for hit in hits or []:
            entity = hit.get("entity") if isinstance(hit, dict) else None
            if isinstance(entity, dict) and entity.get("chunk_id") is not None:
                entities.append(entity)

        return entities

    @staticmethod
    def _step_2_rrf_merge(routes: list[tuple[list[dict], float]]) -> list[tuple[dict, float]]:
        """每个 Chunk 的得分 = 各路的 权重 / (k + 名次) 之和，返回按得分降序的 (entity, 得分)。"""
        scores: dict = {}
        entities: dict = {}
        for route_entities, weight in routes:
            for rank, entity in enumerate(route_entities, start=1):
                chunk_id = entity["chunk_id"]
                scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (RRF_K + rank)
                # 同一个 Chunk 两路都命中时，保留先遇到的那份。
                entities.setdefault(chunk_id, entity)

        # sorted 是稳定排序：得分相同的 Chunk 保持先出现的顺序。
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [(entities[chunk_id], score) for chunk_id, score in ranked]

if __name__ == "__main__":
    # 两路检索只有学习期入口用得到，放在这里导入，节点本身不依赖检索节点。
    from app.processor.query_processor.nodes.node_search_embedding import NodeSearchEmbedding
    from app.processor.query_processor.nodes.node_search_embedding_hyde import NodeSearchEmbeddingHyde

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    state = {
        "rewritten_query": "RS PRO RS-12 数字万用表怎么测量交流电压？",
        "item_names": ["RS PRO RS-12 数字万用表"],
    }
    # 先真实跑两路检索，再把它们的结果交给融合节点。
    state.update(NodeSearchEmbedding()(state))
    state.update(NodeSearchEmbeddingHyde()(state))

    def ranks(field: str) -> dict:
        """chunk_id → 在这一路里的名次（从 1 开始）。"""
        return {hit["entity"]["chunk_id"]: rank for rank, hit in enumerate(state[field], start=1)}

    vector_ranks, hyde_ranks = ranks("embedding_chunks"), ranks("hyde_embedding_chunks")
    result = NodeRrf()(state)

    print("RRF 融合结果：")
    for position, chunk in enumerate(result["rrf_chunks"], start=1):
        chunk_id = chunk["chunk_id"]
        print(
            f"  {position}. chunk_id={chunk_id}  向量检索第 {vector_ranks.get(chunk_id, '-')} 名"
            f"  HyDE 第 {hyde_ranks.get(chunk_id, '-')} 名  {chunk['content'].replace(chr(10), ' ')[:30]}"
        )