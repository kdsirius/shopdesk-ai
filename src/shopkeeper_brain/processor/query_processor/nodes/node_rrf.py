from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeRrf(NodeBase):
    """把多路召回结果融合排序；本节只占位，状态原样通过。"""

    name = "node_rrf"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return state
