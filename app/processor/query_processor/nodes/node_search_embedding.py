import logging

from app.core.milvus_config import load_milvus_config
from app.processor.import_processor.exceptions import StateFieldError, ConfigurationError
from app.processor.query_processor.base import NodeBase
from app.processor.query_processor.state import QueryGraphState
from app.utils.embedding_utils import generate_embeddings
from app.utils.milvus_utils import escape_milvus_string, create_hybrid_search_requests, hybrid_search, \
    get_milvus_client

# 每一路先各取 10 条候选做加权融合，融合后只留前 5 条交给后面的 RRF 与重排。
PER_ROUTE_LIMIT = 10
RESULT_LIMIT = 5


class NodeSearchEmbedding(NodeBase):
    """用改写后的问题，在已确认商品的范围内检索 kb_chunks 的 Dense + Sparse 混合结果。"""
    name = "node_search_embedding"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """读取 rewritten_query、item_names；只返回 embedding_chunks，三路并行检索各写各的字段。"""
        query, item_names = self._step_1_validate_param(state)
        # 过滤表达式和问题向量对应的是同一次检索：Dense、Sparse 两路共用同一个 expr。
        expr = self._build_item_filter(item_names)
        self.logger.info("步骤 2：过滤条件 %s", expr)

        embeddings = generate_embeddings([query])
        reqs = create_hybrid_search_requests(
            embeddings["dense"][0],
            embeddings["sparse"][0],
            limit=PER_ROUTE_LIMIT,
            expr=expr
        )

        collection_name = load_milvus_config().chunk_collection
        if not collection_name.strip():
            raise ConfigurationError(
                "Chunk 集合未配置，请检查 SHOPKEEPER_BRAIN_MILVUS_CHUNK_COLLECTION",
                node_name=self.name,
            )

        hits = hybrid_search(
            get_milvus_client(),
            collection_name,
            reqs,
            ranker_weights=(0.8, 0.2),
            norm_score=True,
            limit=RESULT_LIMIT,
            output_fields=["chunk_id", "content", "item_name"]
        )

        # 外层列表对应查询向量，本节只查一个问题，所以取第 0 个。
        chunks = hits[0]
        self.logger.info("步骤 3：召回 %d 个 Chunk", len(chunks))
        return {"embedding_chunks": chunks}

    def _step_1_validate_param(self, state: QueryGraphState) -> tuple[str, list[str]]:
        """问题和商品名是节点的输入契约；商品名为空时不能退化成全库检索。"""
        query = state.get("rewritten_query")
        if not isinstance(query, str) or not query.strip():
            raise StateFieldError(node_name=self.name, field_name="rewritten_query", expected_type=str)

        item_names = state.get("item_names")
        if (
                not isinstance(item_names, list)
                or not item_names
                or any(not isinstance(name, str) or not name.strip() for name in item_names)
        ):
            raise StateFieldError(node_name=self.name, field_name="item_names", expected_type=list)

        return query.strip(), item_names

    @staticmethod
    def _build_item_filter(item_names: list[str]) -> str:
        """生成 item_name in ["名称1", "名称2"]；名称先转义，带引号的名称也不会破坏表达式。"""
        quoted = ", ".join(f'"{escape_milvus_string(name)}"' for name in item_names)
        return f"item_name in [{quoted}]"


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    query = "RS PRO RS-12 数字万用表怎么测量交流电压？"
    # 第一组是库里真实存在的商品；第二组是不存在的商品，用来观察过滤条件确实在起作用。
    cases = [["RS PRO RS-12 数字万用表"], ["不存在的产品"]]

    node = NodeSearchEmbedding()
    for item_names in cases:
        result = node({"rewritten_query": query, "item_names": item_names})
        chunks = result["embedding_chunks"]
        print("商品范围：", item_names, "→ 召回", len(chunks), "条")
        for rank, hit in enumerate(chunks, start=1):
            entity = hit["entity"]
            content = entity["content"].replace("\n", " ")[:40]
            print(f"  {rank}. 评分 {hit['distance']:.4f}  chunk_id={entity['chunk_id']}  {content}")
        print("-" * 30)
