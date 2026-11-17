from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeSearchEmbeddingHyde(NodeBase):
    """先让模型生成假设性答案，再用答案做向量检索；本节只占位。"""

    name = "node_search_embedding_hyde"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return {"hyde_embedding_chunks": []}