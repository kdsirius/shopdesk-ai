from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeAnswerOutput(NodeBase):
    """根据检索结果生成最终回答，或直接输出追问与拒答；本节只占位，状态原样通过。"""

    name = "node_answer_output"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return state
