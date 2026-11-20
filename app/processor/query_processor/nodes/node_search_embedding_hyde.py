import logging

from langchain_openai import ChatOpenAI

from app.core.llm_config import load_llm_config
from app.core.milvus_config import load_milvus_config
from app.processor.import_processor.exceptions import StateFieldError, ConfigurationError
from app.processor.query_processor.base import NodeBase
from app.processor.query_processor.nodes.node_search_embedding import NodeSearchEmbedding, PER_ROUTE_LIMIT, \
    RESULT_LIMIT
from app.processor.query_processor.state import QueryGraphState
from app.utils.embedding_utils import generate_embeddings
from app.utils.milvus_utils import create_hybrid_search_requests, hybrid_search, get_milvus_client

HYDE_PROMPT = """请基于以下用户查询生成一个简洁的回答范文。
用户查询：{rewritten_query}
要求：
1. 回答要简洁明了，包含核心信息即可
2. 假设你是该领域的专家，提供专业的解释
3. 不要使用“假设”“可能”等不确定的词汇
4. 保持回答与查询主题高度相关
5. 使用中文回答且不超过 300 字
"""


class NodeSearchEmbeddingHyde(NodeBase):
    """先让文本模型写一段假设性答案，再用“问题 + 假设答案”检索 kb_chunks（HyDE）。"""

    name = "node_search_embedding_hyde"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """读取 rewritten_query、item_names；只返回 hyde_embedding_chunks。
               模型或向量库出故障时本路返回空列表，不拖垮另外两路检索。"""
        query, item_names = self._step_1_validate_param(state)

        try:
            hyde_doc = self._step_2_create_hyde_doc(query)
            chunks = self._step_3_search(query, hyde_doc, item_names)
        except Exception as exc:
            self.logger.error("HyDE 检索失败，本路返回空结果：%s: %s", type(exc).__name__, exc)
            return {"hyde_embedding_chunks": []}

        return {"hyde_embedding_chunks": chunks}

    def _step_1_validate_param(self, state: QueryGraphState) -> tuple[str, list[str]]:
        """输入契约与向量检索节点相同：问题和商品名缺一不可，商品名不能为空。"""
        query = state.get("rewritten_query")
        if not isinstance(query, str) or not query.strip():
            raise StateFieldError(node_name=self.name, field_name="rewritten_query", expected_type=str)

        item_names = state.get("item_names")
        if (
                not isinstance(item_names, list)
                or not item_names
                or any(not isinstance(name, str) or not name.strip() for name in item_names)
        ):
            raise StateFieldError(node_name=self.name, field_name="item_names", expected_type=list)

        return query.strip(), item_names

    def _step_2_create_hyde_doc(self, query: str) -> str:
        """让文本模型按问题写一段“范文”；范文不要求事实正确，只负责带出手册里会出现的词。"""
        config = load_llm_config()
        if not all((config.base_url, config.api_key, config.model)):
            raise ConfigurationError("文本模型配置不完整，无法生成假设文档", node_name=self.name)

        model = ChatOpenAI(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=config.temperature,
            extra_body={"enable_thinking": False},
        )

        hyde_doc = model.invoke(HYDE_PROMPT.format(rewritten_query=query)).text.strip()
        self.logger.info("步骤 2：假设文档 %d 字：%s", len(hyde_doc), hyde_doc)
        return hyde_doc

    def _step_3_search(self, query: str, hyde_doc: str, item_names: list[str]) -> list[dict]:
        """把“问题 + 假设文档”当作一段文本向量化，其余与向量检索节点一致。"""
        # 拼上原问题：假设文档可能跑偏，原问题把用户真正的意图留在向量里。
        embeddings = generate_embeddings([f"{query} {hyde_doc}"])

        # 与向量检索节点共用同一个过滤表达式写法，两路的商品范围不会各写各的。
        expr = NodeSearchEmbedding._build_item_filter(item_names)
        self.logger.info("步骤 3：过滤条件 %s", expr)
        reqs = create_hybrid_search_requests(
            embeddings["dense"][0],
            embeddings["sparse"][0],
            limit=PER_ROUTE_LIMIT,
            expr=expr,
        )

        collection_name = load_milvus_config().chunk_collection
        if not collection_name:
            raise ConfigurationError(
                "Chunk 集合未配置，请检查 MILVUS_CHUNK_COLLECTION",
                node_name=self.name,
            )

        hits = hybrid_search(
            get_milvus_client(),
            collection_name,
            reqs,
            ranker_weights=(0.8, 0.2),
            norm_score=True,
            limit=RESULT_LIMIT,
            output_fields=["chunk_id", "content", "item_name"],
        )
        chunks = hits[0]
        self.logger.info("步骤 3：召回 %d 个 Chunk", len(chunks))
        return chunks


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    state = {
        "rewritten_query": "RS PRO RS-12 数字万用表怎么测量交流电压？",
        "item_names": ["RS PRO RS-12 数字万用表"],
    }
    # 同一个问题分别走直接检索和 HyDE 检索，对照两路召回的 Chunk。
    direct = NodeSearchEmbedding()(state)["embedding_chunks"]
    hyde = NodeSearchEmbeddingHyde()(state)["hyde_embedding_chunks"]
    direct_ids = {hit["entity"]["chunk_id"] for hit in direct}

    print("HyDE 召回", len(hyde), "条：")
    for rank, hit in enumerate(hyde, start=1):
        entity = hit["entity"]
        mark = "两路都有" if entity["chunk_id"] in direct_ids else "仅 HyDE"
        content = entity["content"].replace("\n", " ")[:40]
        print(f"  {rank}. 评分 {hit['distance']:.4f}  {mark}  chunk_id={entity['chunk_id']}  {content}")
