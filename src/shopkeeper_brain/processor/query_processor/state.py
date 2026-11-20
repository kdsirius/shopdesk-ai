from typing import TypedDict


class QueryGraphState(TypedDict, total=False):
    """查询流程中所有节点共享的状态；各字段由不同节点逐步写入，所以都不是必填。"""

    # 用户输入
    session_id: str
    message_id: str
    original_query: str

    # 产品确认写入
    rewritten_query: str
    item_names: list[str]
    history: list[dict[str, object]]

    # 三路检索各写各的字段
    embedding_chunks: list[dict[str, object]]
    hyde_embedding_chunks: list[dict[str, object]]
    web_search_docs: list[dict[str, object]]

    # 融合、重排和生成
    rrf_chunks: list[dict[str, object]]
    reranked_docs: list[dict[str, object]]
    prompt: str
    answer: str
    image_urls: list[str]
    is_stream: bool
