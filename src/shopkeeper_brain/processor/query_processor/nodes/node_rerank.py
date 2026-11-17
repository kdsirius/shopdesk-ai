from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeRerank(NodeBase):
    """对融合后的结果做精细重排；本节只占位，状态原样通过。"""

    name = "node_rerank"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return state
