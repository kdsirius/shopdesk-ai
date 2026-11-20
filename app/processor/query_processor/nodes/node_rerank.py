import logging

from app.core.exceptions import StateFieldError
from app.processor.query_processor.base import NodeBase
from app.processor.query_processor.state import QueryGraphState
from app.utils.rerank_utils import rerank_documents

# 动态 TopK 的上下限：至少留 3 条，最多留 10 条。
RERANK_MIN_TOP_K = 3
RERANK_MAX_TOP_K = 10
# 断崖阈值：相邻两条的分差达到 0.5（高分区间），或下降比例达到 25%（低分区间），就在这里截断。
RERANK_GAP_ABS = 0.5
RERANK_GAP_RATIO = 0.25


class NodeRerank(NodeBase):
    """把本地融合结果和联网结果放在一起，用重排模型逐条打分，再按分数断崖动态截取。"""
    name = "node_rerank"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """读取 rewritten_query、rrf_chunks、web_search_docs；只返回 reranked_docs。
               后两个字段缺失或为空视为没有这一类文档；重排服务出故障时降级为本地融合顺序。"""
        query = state.get("rewritten_query")
        if not isinstance(query, str) or not query.strip():
            raise StateFieldError(node_name=self.name, field_name="rewritten_query", expected_type=str)

        docs = self._step_1_merge_docs(state)
        self.logger.info("步骤 1：待重排文档 %d 条", len(docs))
        if not docs:
            return {"reranked_docs": []}

        scored_docs = self._step_2_rerank(query.strip(), docs)
        reranked_docs = self._step_3_cliff_cutoff(scored_docs)
        self.logger.info("步骤 3：截取后保留 %d 条", len(reranked_docs))
        return {"reranked_docs": reranked_docs}

    @staticmethod
    def _step_1_merge_docs(state: QueryGraphState) -> list[dict]:
        """本地 Chunk 和联网结果字段不同，统一成 {content, title, chunk_id, url, source}；没有正文的丢弃。"""
        docs = []
        for chunk in state.get('rrf_chunks') or []:
            content = (chunk.get("content") or "").strip()
            if content:
                docs.append({
                    "content": content,
                    # Chunk 里没有标题字段，用所属商品名代替。
                    "title": chunk.get("item_name") or "",
                    "chunk_id": chunk.get("chunk_id"),
                    "url": None,
                    "source": "local"
                })

        for page in state.get("web_search_docs") or []:
            content = (page.get("snippet") or "").strip()
            if content:
                docs.append({
                    "content": content,
                    "title": page.get("title") or "",
                    "chunk_id": None,
                    "url": page.get("url"),
                    "source": "web"
                })

        return docs

    def _step_2_rerank(self, query: str, docs: list[dict]) -> list[dict]:
        """调用重排模型给每条文档打分，按分数降序返回。"""
        try:
            scores = rerank_documents(query, [doc["content"] for doc in docs])
        except Exception as exc:
            # 重排失败时联网结果没有任何把关，不能直接交给答案生成；
            # 只保留本地结果，顺序沿用 RRF 的融合顺序，分数记为 None。
            self.logger.error("重排失败，降级为本地融合顺序：%s: %s", type(exc).__name__, exc)
            return [{**doc, "score": None} for doc in docs if doc["source"] == "local"]

        scored_docs = [{**doc, "score": score} for doc, score in zip(docs, scores)]
        return sorted(scored_docs, key=lambda doc: doc["score"], reverse=True)

    def _step_3_cliff_cutoff(self, ranked_docs: list[dict]) -> list[dict]:
        """断崖检测：从第 MIN_TOP_K 条起，相邻两条分数骤降就在此截断，最多保留 MAX_TOP_K 条。"""
        upper_bound = min(RERANK_MAX_TOP_K, len(ranked_docs))
        lower_bound = min(RERANK_MIN_TOP_K, upper_bound)

        cutoff = upper_bound

        for index in range(lower_bound - 1, upper_bound - 1):
            current = ranked_docs[index]["score"]
            following = ranked_docs[index + 1]["score"]
            if current is None or following is None:
                continue

            abs_gap = current - following
            # 1e-6 防止当前分数为 0 时除零。
            rel_gap = abs_gap / (abs(current) + 1e-6)
            if abs_gap >= RERANK_GAP_ABS or rel_gap >= RERANK_GAP_RATIO:
                cutoff = index + 1
                self.logger.info(
                    "步骤 3：断崖在第 %d 条之后，绝对差 %.4f，相对差 %.4f", cutoff, abs_gap, rel_gap
                )
                break

        return ranked_docs[:cutoff]


if __name__ == "__main__":
    # 检索和融合节点只有学习期入口用得到，放在这里导入。
    from app.processor.query_processor.nodes.node_rrf import NodeRrf
    from app.processor.query_processor.nodes.node_search_embedding import NodeSearchEmbedding
    from app.processor.query_processor.nodes.node_search_embedding_hyde import NodeSearchEmbeddingHyde
    from app.processor.query_processor.nodes.node_web_search_mcp import NodeWebSearchMcp

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    state = {
        "rewritten_query": "RS PRO RS-12 数字万用表怎么测量交流电压？",
        "item_names": ["RS PRO RS-12 数字万用表"],
    }
    # 依次真实跑完三路检索和融合，再交给重排。
    for node in (NodeSearchEmbedding(), NodeSearchEmbeddingHyde(), NodeWebSearchMcp(), NodeRrf()):
        state.update(node(state))

    result = NodeRerank()(state)
    print("重排后保留", len(result["reranked_docs"]), "条：")
    for rank, doc in enumerate(result["reranked_docs"], start=1):
        score = "无" if doc["score"] is None else f"{doc['score']:.4f}"
        print(
            f"  {rank}. 分数 {score}  [{doc['source']}]  {doc['title'][:20]}  {doc['content'].replace(chr(10), ' ')[:30]}")
