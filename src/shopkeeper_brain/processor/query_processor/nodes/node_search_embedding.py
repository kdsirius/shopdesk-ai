from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeSearchEmbedding(NodeBase):
    """基于已确认的商品名和改写后的问题，在 Milvus 中检索 Chunk；本节只占位。"""

    name = "node_search_embedding"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # 三路检索并行执行，各自只返回自己负责的字段，避免同时写同一批键。
        return {"embedding_chunks": []}
