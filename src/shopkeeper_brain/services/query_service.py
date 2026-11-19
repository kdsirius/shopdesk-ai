import logging
from typing import Callable

from shopkeeper_brain.processor.query_processor.main_graph import KBQueryWorkflow

logger = logging.getLogger(__name__)


def run_query(session_id: str, question: str, publish: Callable[[str, dict], None]) -> None:
    state = {"session_id": session_id, "original_query": question}
    reranked_count = None

    try:
        for update in KBQueryWorkflow().stream(state):
            for node, changes in update["data"].items():
                publish("progress", {"node": node})
                if node == "node_rerank":
                    reranked_count = len(changes["reranked_docs"])
        publish("complete", {"reranked_count": reranked_count})
    except Exception:
        logger.exception("查询失败，session_id=%s", session_id)
        publish("task_error", {"message": "查询失败，请查看服务端日志。"})
