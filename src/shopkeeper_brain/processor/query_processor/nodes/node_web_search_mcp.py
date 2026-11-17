from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeWebSearchMcp(NodeBase):
    """调用外部搜索服务补充互联网信息；本节只占位。"""

    name = "node_web_search_mcp"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        return {"web_search_docs": []}