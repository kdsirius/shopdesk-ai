import logging
from typing import Callable

from app.processor.query_processor.main_graph import KBQueryWorkflow

logger = logging.getLogger(__name__)


def run_query(session_id: str, question: str, publish: Callable[[str, dict], None]) -> None:
    state = {"session_id": session_id, "original_query": question, "is_stream": True}
    reranked_count = None
    answer_result = {}

    try:
        for part in KBQueryWorkflow().stream(state):
            if part["type"] == "custom":
                publish("delta", part["data"])
                continue

            for node, changes in part["data"].items():
                publish("progress", {"node": node})
                if node == "node_rerank":
                    reranked_count = len(changes["reranked_docs"])
                elif node == "node_answer_output":
                    answer_result = changes

        publish("complete", {
            "answer": answer_result["answer"],
            "image_urls": answer_result["image_urls"],
            "reranked_count": reranked_count,
        })
    except Exception:
        logger.exception("查询失败，session_id=%s", session_id)
        publish("task_error", {"message": "查询失败，请查看服务端日志。"})
