import logging
from uuid import uuid4

from langgraph.constants import END
from langgraph.graph import StateGraph

from shopkeeper_brain.processor.query_processor.nodes.node_answer_output import (
    NodeAnswerOutput,
)
from shopkeeper_brain.processor.query_processor.nodes.node_item_name_confirm import (
    NodeItemNameConfirm,
)
from shopkeeper_brain.processor.query_processor.nodes.node_rerank import NodeRerank
from shopkeeper_brain.processor.query_processor.nodes.node_rrf import NodeRrf
from shopkeeper_brain.processor.query_processor.nodes.node_search_embedding import (
    NodeSearchEmbedding,
)
from shopkeeper_brain.processor.query_processor.nodes.node_search_embedding_hyde import (
    NodeSearchEmbeddingHyde,
)
from shopkeeper_brain.processor.query_processor.nodes.node_web_search_mcp import (
    NodeWebSearchMcp,
)
from shopkeeper_brain.processor.query_processor.state import QueryGraphState
from shopkeeper_brain.utils.mongo_history_utils import clear_history

SEARCH_NODES = [
    "node_search_embedding",
    "node_search_embedding_hyde",
    "node_web_search_mcp",
]


class KBQueryWorkflow:
    """知识库查询工作流：注册节点、定义路由，并提供统一的执行入口。"""

    def __init__(self) -> None:
        self.workflow = StateGraph(QueryGraphState)
        self._register_nodes()
        self._setup_routes()
        self._compiled_app = None

    def _register_nodes(self) -> None:
        """图里的节点名直接取节点类的 name，路由里写的字符串必须与它一致。"""
        for node in (
                NodeItemNameConfirm(),
                NodeSearchEmbedding(),
                NodeSearchEmbeddingHyde(),
                NodeWebSearchMcp(),
                NodeRrf(),
                NodeRerank(),
                NodeAnswerOutput(),
        ):
            self.workflow.add_node(node.name, node)

    def _route_after_item_name_confirm(self, state: QueryGraphState) -> str | list[str]:
        """有 answer 说明要追问或拒答，直接输出；否则三路检索并行。"""
        if state.get("answer"):
            return "node_answer_output"
        return SEARCH_NODES

    def _setup_routes(self) -> None:
        """设置入口、条件路由和后续的固定连线。"""
        self.workflow.set_entry_point("node_item_name_confirm")
        self.workflow.add_conditional_edges(
            "node_item_name_confirm",
            self._route_after_item_name_confirm,
            ["node_answer_output", *SEARCH_NODES],
        )

        for node_name in SEARCH_NODES:
            self.workflow.add_edge(node_name, "node_rrf")
        self.workflow.add_edge("node_rrf", "node_rerank")
        self.workflow.add_edge("node_rerank", "node_answer_output")
        self.workflow.add_edge("node_answer_output", END)

    def compile(self):
        """编译一次并缓存。"""
        if self._compiled_app is None:
            self._compiled_app = self.workflow.compile()
        return self._compiled_app

    def run(self, initial_state: QueryGraphState) -> QueryGraphState:
        """同步执行整张图，返回最终状态。"""
        return self.compile().invoke(initial_state)

    def stream(self, initial_state: QueryGraphState):
        """给后台任务读取完成节点的更新和生成中的文本增量。"""
        return self.compile().stream(initial_state, stream_mode=["updates", "custom"], version="v2")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    session_id = str(uuid4())
    cases = [
        (session_id, "RS-12 怎么测电压？"),
        (session_id, "是 RS PRO RS-12 数字万用表，怎么测交流电压？"),
        (str(uuid4()), "iPhone 15 怎么充电？"),
    ]
    workflow = KBQueryWorkflow()
    for current_session, query in cases:
        final_state = workflow.run({"session_id": current_session, "original_query": query})
        print("会话", current_session, "问题", query)
        print("确认商品", final_state["item_names"])
        print(final_state["answer"])
        print("重排条数", len(final_state.get("reranked_docs") or []))
        print("配图", final_state["image_urls"])
