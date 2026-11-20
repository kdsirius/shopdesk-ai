import asyncio
import json
import logging

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.core.tavily_config import load_tavily_config
from app.processor.import_processor.exceptions import StateFieldError, ConfigurationError
from app.processor.query_processor.base import NodeBase
from app.processor.query_processor.state import QueryGraphState

SEARCH_TOOL = "tavily_search"
MAX_RESULTS = 5
REQUEST_TIMEOUT_SECONDS = 30
# Tavily 的 content 可能是整页商品参数表或视频字幕，每条只留开头一段交给后面的重排。
SNIPPET_MAX_CHARS = 500


class NodeWebSearchMcp(NodeBase):
    """通过 Tavily 的远程 MCP 服务联网搜索，补充知识库里没有的信息。"""

    name = "node_web_search_mcp"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """读取 rewritten_query；只返回 web_search_docs。
               联网失败时本路返回空列表，不拖垮另外两路检索。"""
        query = state.get("rewritten_query")
        if not isinstance(query, str) or not query.strip():
            raise StateFieldError(node_name=self.name, field_name="rewritten_query", expected_type=str)
        try:
            # 图里的同步节点在线程池线程中执行，线程里没有事件循环，可以直接 asyncio.run。
            pages = asyncio.run(self._step_2_call_mcp(query.strip()))
        except Exception as exc:
            # MCP 客户端在任务组里运行，真正的错误包在 ExceptionGroup 里，先剥到最里面一层再记日志。
            while isinstance(exc, BaseExceptionGroup):
                exc = exc.exceptions[0]
            self.logger.error("联网搜索失败，本路返回空结果：%s: %s", type(exc).__name__, exc)
            return {"web_search_docs": []}
        docs = self._step_3_format_docs(pages)
        self.logger.info("步骤 3：搜索返回 %d 条，保留 %d 条", len(pages), len(docs))
        return {"web_search_docs": docs}

    async def _step_2_call_mcp(self, query: str) -> list:
        """连接 Tavily MCP，调用 tavily_search，返回结果列表。"""
        config = load_tavily_config()
        api_key = config.api_key.get_secret_value()
        if not api_key:
            raise ConfigurationError(
                "Tavily 密钥未配置，请检查 TAVILY_API_KEY",
                node_name=self.name,
            )

        # 密钥放在请求头里，不拼进地址，日志里的地址就不会带密钥。
        async with httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=REQUEST_TIMEOUT_SECONDS,
        ) as http_client:
            async with Client(streamable_http_client(config.mcp_url, http_client=http_client)) as client:
                result = await client.call_tool(
                    SEARCH_TOOL,
                    {"query": query, "max_results": MAX_RESULTS},
                )

        if result.is_error:
            raise RuntimeError(f"MCP 工具返回错误：{result.content}")
        # 工具把结果序列化成 JSON 文本放在第一个内容块里。
        payload = json.loads(result.content[0].text)
        # 密钥无效等错误不会让 is_error 变 True，而是返回 {"error": ..., "status": 401}，
        # 没有 results 字段就必须当成失败，否则会被误当成“没有搜到结果”。
        if "results" not in payload:
            raise RuntimeError(
                f"Tavily 返回错误：{payload.get('status')} {payload.get('detail') or payload.get('error')}"
            )

        return payload["results"]

    @staticmethod
    def _step_3_format_docs(pages: list) -> list[dict]:
        """统一成 {title, url, snippet}；去首尾空白，没有正文的结果丢弃。"""
        docs = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            snippet = (page.get("content") or "").strip()
            if not snippet:
                continue

            docs.append({
                "title": (page.get("title") or "").strip(),
                "url": (page.get("url") or "").strip(),
                "snippet": snippet[:SNIPPET_MAX_CHARS]
            })
        return docs


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    result = NodeWebSearchMcp()({"rewritten_query": "RS PRO RS-12 数字万用表怎么测量交流电压？"})
    docs = result["web_search_docs"]
    print("联网搜索返回", len(docs), "条：")
    for rank, doc in enumerate(docs, start=1):
        print(f"  {rank}. {doc['title'][:40]}")
        print(f"     {doc['url']}")
        print(f"     {doc['snippet'].replace(chr(10), ' ')[:60]}")
