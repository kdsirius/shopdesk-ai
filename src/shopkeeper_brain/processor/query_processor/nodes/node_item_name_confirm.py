import json
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from shopkeeper_brain.core.llm_config import load_llm_config
from shopkeeper_brain.core.milvus_config import load_milvus_config
from shopkeeper_brain.processor.import_processor.exceptions import StateFieldError, ConfigurationError
from shopkeeper_brain.processor.query_processor.base import NodeBase
from shopkeeper_brain.processor.query_processor.state import QueryGraphState
from shopkeeper_brain.utils.embedding_utils import generate_embeddings
from shopkeeper_brain.utils.milvus_utils import get_milvus_client, create_hybrid_search_requests, hybrid_search
from shopkeeper_brain.utils.mongo_history_utils import get_recent_messages, save_chat_message, \
    update_message_item_names, clear_history

CONFIRM_SCORE = 0.85
CANDIDATE_SCORE = 0.6
CANDIDATE_LIMIT = 3


class NodeItemNameConfirm(NodeBase):
    """确认用户问的是哪个产品；无法确认时直接生成追问或拒答。"""
    name = "node_item_name_confirm"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """读取 session_id、original_query；写入 history、rewritten_query、item_names，
               需要追问或拒答时写入 answer。"""
        session_id, original_query = self._step_1_validate_param(state)

        # 先读历史再保存当前问题，否则历史里会混进用户刚说的这一句。
        history = get_recent_messages(session_id)
        state["history"] = history
        self.logger.info("步骤 2：读取到 %d 条历史消息", len(history))

        message_id = save_chat_message(session_id=session_id, role="user", text=original_query)
        self.logger.info("步骤 3：当前问题已保存，message_id=%s", message_id)

        extracted = self._step_4_extract_info(original_query, history)
        state["rewritten_query"] = extracted["rewritten_query"]
        state["item_names"] = extracted["item_names"]

        align_result: dict[str, list[str]] = {}
        if extracted["item_names"]:
            query_results = self._step_5_vectorize_and_query(extracted["item_names"])
            align_result = self._step_6_align_item_names(query_results)
        else:
            self.logger.info("没有提取到商品名，跳过名称检索")

        self._step_7_check_confirmation(state, align_result, history)
        self._step_8_write_history(state, session_id, message_id)
        return state

    def _step_1_validate_param(self, state: QueryGraphState) -> tuple[str, str]:
        """session_id 和 original_query 是节点的输入契约，缺任何一个都无法继续。"""
        session_id = state.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            raise StateFieldError(node_name=self.name, field_name="session_id", expected_type=str, )

        original_query = state.get("original_query")
        if not isinstance(original_query, str) or not original_query.strip():
            raise StateFieldError(node_name=self.name, field_name="original_query", expected_type=str, )

        return session_id, original_query

    def _step_4_extract_info(self, query: str, history: list[dict]) -> dict:
        """让文本模型提取商品名并改写问题；模型不可用或返回异常时退回“无商品名 + 原问题”。"""
        fallback = {"item_names": [], "rewritten_query": query}

        config = load_llm_config()
        if not all((config.base_url, config.api_key, config.model)):
            self.logger.warning("文本模型配置不完整，跳过商品名提取")
            return fallback

        history_text = "".join(
            f"{message['role']}: {message['text']}\n" for message in history
        )

        # f-string 里要输出普通大括号，必须写成双大括号。
        prompt = f"""历史会话：
{history_text}
当前用户问题：{query}

请根据历史会话和当前问题，提取用户正在询问的商品名称（item_names）。
1. 如果用户明确提到了商品名称，请提取出来。可能有一个或多个，但不能重复。
2. 如果用户使用了代词（如“这个”“它”），请结合历史会话指代消解，确定商品名称。
3. 如果无法确定商品名称，item_names 返回空列表。
4. 请重新改写用户的问题（rewritten_query），使其成为包含商品名称的独立完整问题。

请直接返回 JSON，格式如下：
{{"item_names": ["商品A", "商品B"], "rewritten_query": "关于商品A和商品B，……"}}
"""

        try:
            model = ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=config.temperature,
                extra_body={"enable_thinking": False},
            )

            response = model.invoke(
                [
                    SystemMessage(
                        content="你是一个专业的客服助手，擅长理解用户意图和提取关键信息。"
                    ),
                    HumanMessage(content=prompt),
                ]
            )
            text = response.text.strip()
            # 模型可能把 JSON 包进代码围栏，只取第一个 { 到最后一个 } 之间的内容。
            result = json.loads(text[text.index("{"):text.rindex("}") + 1])
        except Exception as exc:
            self.logger.warning("商品名提取失败，退回原问题：%s", type(exc).__name__)
            return fallback

        item_names = result.get("item_names")
        if not isinstance(item_names, list):
            item_names = []
        rewritten_query = result.get("rewritten_query")
        if not isinstance(rewritten_query, str) or not rewritten_query.strip():
            rewritten_query = query

        extracted = {
            "item_names": [
                name.strip()
                for name in item_names
                if isinstance(name, str) and name.strip()
            ],
            "rewritten_query": rewritten_query.strip(),
        }

        self.logger.info("步骤 4：提取结果 %s", extracted)
        return extracted

    def _step_5_vectorize_and_query(self, item_names: list[str]) -> list[dict]:
        """把每个提取名称在 kb_item_names 中做 Dense + Sparse 混合检索，返回候选和评分。"""
        collection_name = load_milvus_config().item_name_collection
        if not collection_name:
            raise ConfigurationError(
                "主体名称集合未配置，请检查 "
                "SHOPKEEPER_BRAIN_MILVUS_ITEM_NAME_COLLECTION",
                node_name=self.name,
            )

        client = get_milvus_client()
        embeddings = generate_embeddings(item_names)

        results: list[dict] = []
        for index, extracted_name in enumerate(item_names):
            try:
                reqs = create_hybrid_search_requests(
                    embeddings["dense"][index],
                    embeddings["sparse"][index]
                )
                hits = hybrid_search(
                    client,
                    collection_name,
                    reqs,
                    ranker_weights=(0.8, 0.2),
                    norm_score=True,
                    limit=5,
                    output_fields=["item_name"]
                )
                matches = [
                    {
                        "item_name": hit["entity"]["item_name"],
                        "score": hit["distance"],
                    }
                    for hit in hits[0]
                ]
                self.logger.info("步骤 5：%r 的候选 %s", extracted_name, matches)
                results.append({"extracted_name": extracted_name, "matches": matches})
            except Exception as exc:
                self.logger.error("步骤 5：查询 %r 失败：%s", extracted_name, exc)

        return results

    def _step_6_align_item_names(self, query_results: list[dict], ) -> dict[str, list[str]]:
        """按评分把提取名称对齐成“确认”和“候选”，两个列表都去重并保持评分从高到低的顺序。"""
        confirmed: list[str] = []
        options: list[str] = []

        for result in query_results:
            matches = result["matches"]

            high = [m for m in matches if m["score"] > CONFIRM_SCORE]
            if high:
                # 评分高于 0.85 的都确认：同一产品可能在名称集合里有几种写法，只留一个会让正文检索漏掉另一半 Chunk。
                confirmed.extend(m["item_name"] for m in high)
                continue

            options.extend(
                m["item_name"] for m in matches if m["score"] >= CANDIDATE_SCORE
            )
        # 用 dict.fromkeys 去重而不是 set：set 会打乱顺序，追问时取前几个就可能漏掉评分最高的。
        return {
            "confirmed_item_names": list(dict.fromkeys(confirmed)),
            "options": list(dict.fromkeys(options))
        }

    def _step_7_check_confirmation(
            self,
            state: QueryGraphState,
            align_result: dict[str, list[str]],
            history: list[dict],
    ) -> None:
        """三个分支：已确认继续检索，只有候选就追问，什么都没有就拒答；直接修改 state。"""
        confirmed = align_result.get("confirmed_item_names", [])
        options = align_result.get("options", [])

        if confirmed:
            # 分支 A：历史里还没有商品名的消息补上它，后面的对话就能沿用这个商品。
            ids = [str(message["_id"]) for message in history if not message.get("item_names")]

            if ids:
                update_message_item_names(ids, confirmed)
            state["item_names"] = confirmed
            state["answer"] = ""
            return

        state["item_names"] = []
        if options:
            # 分支 B
            option_text = "、".join(options[:CANDIDATE_LIMIT])
            state["answer"] = f"您是想问以下哪个产品：{option_text}？请明确一下型号。"
        else:
            # 分支 C
            state["answer"] = "抱歉，未找到相关产品，请提供准确型号以便我为您查询。"

    def _step_8_write_history(
            self,
            state: QueryGraphState,
            session_id: str,
            message_id: str,
    ) -> None:
        """追问或拒答要作为助手消息入库；再把改写问题和商品名补到第 3 步保存的用户消息上。"""
        if state.get("answer"):
            save_chat_message(
                session_id,
                "assistant",
                state["answer"],
                item_names=state["item_names"]
            )

        save_chat_message(
            session_id,
            "user",
            state["original_query"],
            rewritten_query=state["rewritten_query"],
            item_names=state["item_names"],
            message_id=message_id
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    session_id = "day09-confirm-demo"
    # 按顺序发送的用户问题；只验证拒答分支时，改成 ["iPhone 15 怎么充电？"]。
    queries = ["RS-12 怎么测电压？", "对，就是这个，怎么测电压？"]
    # queries = ["iPhone 15 怎么充电？"]

    clear_history(session_id)  # 每次从空会话开始，结果才能重复
    node = NodeItemNameConfirm()
    for query in queries:
        result = node({"session_id": session_id, "original_query": query})
        print("问题：", query)
        print("改写问题：", result["rewritten_query"])
        print("确认商品：", result["item_names"])
        print("直接回答：", result["answer"] or "（空：可以继续检索）")
        print("-" * 30)

    print("会话历史：")
    for message in get_recent_messages(session_id):
        print(message["role"], message["item_names"], message["text"])
